"""Staff video generation: queue locally, persist provider requests, poll, store media."""

import asyncio
import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import gateway, jobs, narrated_video, photos
from app.auth import require_roles
from app.config import get_settings
from app.db import get_session, get_sessionmaker
from app.errors import INTERNAL_PREFIX, UserFacingError
from app.handlers import handler
from app.models import Job, Role, Story, TextLayer, User, VideoGeneration
from app.providers.video import FreeVideoRead, clip_extension, configurations, provider
from app.storage import get_storage

router = APIRouter(prefix="/staff/videos", tags=["videos"])
staff = require_roles(Role.REVIEWER, Role.ADMIN)


class VideoIn(BaseModel):
    story_id: uuid.UUID
    provider: str = Field(default="fake", max_length=30)
    model: str = Field(default="demo", max_length=150)
    prompt: str = Field(
        default="A slow, respectful cinematic view of this heritage place.", max_length=1000
    )
    aspect_ratio: str = Field(default="16:9", pattern=r"^(16:9|9:16)$")
    seed: int = Field(default=42, ge=0, le=2147483647)
    # "narrated": shots planned from the story's soundtrack, joined, voiced and subtitled.
    mode: Literal["clip", "narrated"] = "clip"
    soundtrack: Literal["narration", "recording"] = "narration"
    subtitles: bool = True
    # The voice of a narrated video: the soundtrack (ElevenLabs narration or the recording)
    # or Omni's own generated audio; NARRATED_VIDEO_AUDIO when not given.
    audio: Literal["soundtrack", "omni"] | None = None


async def output(session: AsyncSession, generation: VideoGeneration) -> dict:
    job = await session.get(Job, generation.job_id)
    error = job.error if job else "Video job unavailable."
    if error and error.startswith(INTERNAL_PREFIX):
        error = "Video generation failed. Please try again or use the slideshow."
    return {
        "id": str(generation.id),
        "story_id": str(generation.story_id),
        "provider": generation.provider,
        "model": generation.payload["model"],
        "prompt": generation.payload["prompt"],
        "status": job.status if job else "failed",
        "progress": generation.progress,
        "error": error,
        "demo": generation.provider == "fake",
        "video_url": f"/api/v1/staff/videos/{generation.id}/media" if generation.file_key else None,
        "mode": generation.payload.get("mode", "clip"),
        "shots": len(generation.shots),
        "seconds": generation.payload.get("seconds"),
        "retryable": narrated_video.retryable(generation, job),
        "needs_confirmation": narrated_video.needs_confirmation(generation, job),
        "shot": narrated_video.current_shot(generation),
        "audio": generation.payload.get("audio") if generation.shots else None,
        # The refined shot script, once written (the fake writer's echo of the words is not).
        "script": (
            generation.script
            if generation.script and generation.script.get("provider") != "fake"
            else None
        ),
    }


@router.get("/config")
async def config(user: User = Depends(staff)) -> dict:
    return {
        "enabled": get_settings().enable_ai_video,
        "default_provider": get_settings().video_provider,
        "providers": configurations(),
        "narrated_max_seconds": get_settings().narrated_video_max_seconds,
        "narrated_audio": get_settings().narrated_video_audio,
        "script_provider": get_settings().script_provider,
    }


def _choose(body: VideoIn) -> dict:
    selected = next((item for item in configurations() if item["id"] == body.provider), None)
    if not selected or not selected["available"] or body.model not in selected["models"]:
        raise HTTPException(422, "Choose an available provider and supported model.")
    return selected


async def _story_or_404(session: AsyncSession, story_id: uuid.UUID) -> Story:
    story = await session.get(Story, story_id)
    if not story:
        raise HTTPException(404, "Story not found.")
    return story


async def _story_photo(
    session: AsyncSession, story: Story, provider_name: str
) -> tuple[bytes | None, str]:
    """The story's first photo (the video's opening frame) and its hash. Only the offline
    demo can do without one."""
    images = await photos.slideshow_images(session, story)
    if not images:
        if provider_name != "fake":
            raise HTTPException(422, "Add a story photo before generating an AI video.")
        return None, ""
    storage = get_storage()
    if not storage.exists(images[0]):
        raise HTTPException(422, "The story photo is missing. Choose another photo.")
    data = await asyncio.to_thread(storage.path(images[0]).read_bytes)
    return data, hashlib.sha256(data).hexdigest()


def _digest(*parts) -> str:
    """A request's identity: the same input reuses the existing video and its cache."""
    return hashlib.sha256(json.dumps(list(parts), sort_keys=True).encode()).hexdigest()


async def _existing(session: AsyncSession, digest: str) -> VideoGeneration | None:
    return (
        await session.execute(select(VideoGeneration).where(VideoGeneration.input_hash == digest))
    ).scalar_one_or_none()


async def _ensure_room(provider_name: str, estimate: Decimal) -> None:
    """Refuse (422) work whose estimate would pass a spending cap now; reserves nothing."""
    budget = provider(provider_name).budget
    if not budget or estimate <= 0:
        return
    try:
        await gateway.check_room(budget, estimate)
    except gateway.SpendingLimit as exc:
        raise HTTPException(
            422,
            f"This video (about {estimate:.2f} USD) would pass the {exc.which} spending limit, "
            "so nothing was queued.",
        ) from None


async def _record(
    session: AsyncSession, generation: VideoGeneration, kind: str, job_payload: dict, key: str
) -> dict:
    """Queue the video's first job and store the video in one transaction."""
    try:
        job = await jobs.enqueue(
            session, kind, job_payload, idempotency_key=key, max_attempts=1, commit=False
        )
        generation.job_id = job.id
        session.add(generation)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        get_storage().delete_tree(f"stories/{generation.story_id}/videos/{generation.id}")
        raise HTTPException(409, "This video was already queued. Refresh the job list.") from None
    return await output(session, generation)


def _audio(body: VideoIn) -> str:
    return body.audio or get_settings().narrated_video_audio


async def _narrated_plan(
    session: AsyncSession, body: VideoIn, selected: dict
) -> tuple[Story, narrated_video.StoryPlan]:
    """The plan for a narrated video, refused (422) when it cannot be made or would not fit
    the spending budget. Reads the database only; no provider is called."""
    if not selected.get("max_shot_seconds"):
        raise HTTPException(
            422,
            "This provider makes fixed-length clips and is not offered for narrated videos; "
            "choose Gemini Omni Flash.",
        )
    story = await _story_or_404(session, body.story_id)
    try:
        plan = await narrated_video.plan_story(
            session, story, body.provider, body.soundtrack, _audio(body)
        )
    except UserFacingError as exc:
        raise HTTPException(422, str(exc)) from None
    await _ensure_room(body.provider, plan.estimate)
    return story, plan


@router.post("/plan")
async def preview_plan(
    body: VideoIn, user: User = Depends(staff), session: AsyncSession = Depends(get_session)
) -> dict:
    """What a narrated video would be (shots, length, lines covered, estimated cost) before
    anything is queued or paid for."""
    _, plan = await _narrated_plan(session, body, _choose(body))
    return plan.summary()


async def _generate_narrated(
    session: AsyncSession, body: VideoIn, selected: dict, user: User
) -> dict:
    story, plan = await _narrated_plan(session, body, selected)
    image_bytes, image_hash = await _story_photo(session, story, body.provider)
    storage = get_storage()
    sound = await asyncio.to_thread(storage.path(plan.soundtrack_key).read_bytes)
    direction = body.prompt.strip()
    audio = _audio(body)
    shots = narrated_video.new_shots(plan, story.title, story.place_name, direction, audio)
    payload = {
        "mode": "narrated",
        "model": body.model,
        "prompt": direction,
        "aspect_ratio": body.aspect_ratio if selected.get("supports_aspect", True) else "16:9",
        "seed": body.seed if selected.get("supports_seed", True) else 0,
        "soundtrack": body.soundtrack,
        "subtitles": body.subtitles,
        "audio": audio,
        "language": plan.language,
        "rtl": plan.rtl,
        "lines": narrated_video.payload_lines(plan),
        "lines_total": plan.lines_total,
        "seconds": plan.seconds,
        # So revoking the voice that read the soundtrack also removes this video.
        "voice_clone_id": str(plan.voice_clone_id) if plan.voice_clone_id else None,
    }
    # The shots' prompts carry the title, place and words, so a change to any of them is a
    # new request.
    digest = _digest(
        str(story.id),
        body.provider,
        payload,
        image_hash,
        hashlib.sha256(sound).hexdigest(),
        [shot["prompt"] for shot in shots],
    )
    if existing := await _existing(session, digest):
        return await output(session, existing)
    generation_id = uuid.uuid4()
    folder = f"stories/{story.id}/videos/{generation_id}"
    image_key = f"{folder}/input.webp" if image_bytes is not None else None
    if image_key:
        await asyncio.to_thread(storage.write_bytes, image_key, image_bytes)
    # The soundtrack is copied for the joining step; revoking its voice removes it too.
    payload["audio_key"] = f"{folder}/soundtrack.mp3"
    await asyncio.to_thread(storage.write_bytes, payload["audio_key"], sound)
    generation = VideoGeneration(
        id=generation_id,
        story_id=story.id,
        actor_id=user.id,
        provider=body.provider,
        payload=payload,
        image_key=image_key,
        input_hash=digest,
        shots=shots,
    )
    return await _record(
        session,
        generation,
        narrated_video.KIND,
        {
            "generation_id": str(generation_id),
            "deadline": narrated_video.deadline_for(len(shots)).isoformat(),
        },
        f"{narrated_video.KIND}:{digest}",
    )


@router.get("")
async def list_videos(
    user: User = Depends(staff), session: AsyncSession = Depends(get_session)
) -> list:
    rows = (
        await session.execute(
            select(VideoGeneration).order_by(VideoGeneration.created_at.desc()).limit(50)
        )
    ).scalars()
    return [await output(session, row) for row in rows]


@router.post("", status_code=202)
async def generate(
    body: VideoIn, user: User = Depends(staff), session: AsyncSession = Depends(get_session)
) -> dict:
    if not get_settings().enable_ai_video:
        raise HTTPException(503, "AI video generation is disabled for this demo.")
    selected = _choose(body)
    if body.mode == "narrated":
        return await _generate_narrated(session, body, selected, user)
    story = await _story_or_404(session, body.story_id)
    layer = (
        await session.execute(
            select(TextLayer).where(TextLayer.story_id == story.id, TextLayer.kind == "polished")
        )
    ).scalar_one_or_none()
    words = " ".join(segment["text"] for segment in layer.segments)[:1500] if layer else ""
    prompt = (
        f"Heritage story: {story.title}. Place: {story.place_name}. {words}\n"
        f"Visual direction: {body.prompt.strip()}"
    )
    image_bytes, image_hash = await _story_photo(session, story, body.provider)
    payload = {
        "model": body.model,
        "prompt": prompt,
        "aspect_ratio": body.aspect_ratio if selected.get("supports_aspect", True) else "source",
        "seed": body.seed if selected.get("supports_seed", True) else 0,
    }
    digest = _digest(str(story.id), body.provider, payload, image_hash)
    if existing := await _existing(session, digest):
        return await output(session, existing)
    generation_id = uuid.uuid4()
    image_key = None
    if image_bytes is not None:
        image_key = f"stories/{story.id}/videos/{generation_id}/input.webp"
        await asyncio.to_thread(get_storage().write_bytes, image_key, image_bytes)
    generation = VideoGeneration(
        id=generation_id,
        story_id=story.id,
        actor_id=user.id,
        provider=body.provider,
        payload=payload,
        image_key=image_key,
        input_hash=digest,
    )
    return await _record(
        session,
        generation,
        "generate_video",
        {"generation_id": str(generation_id)},
        f"video:{digest}",
    )


async def find_generation(session: AsyncSession, generation_id: uuid.UUID) -> VideoGeneration:
    result = await session.get(VideoGeneration, generation_id)
    if not result:
        raise HTTPException(404, "Video job not found.")
    return result


@router.get("/{generation_id}")
async def read_video(
    generation_id: uuid.UUID,
    user: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await output(session, await find_generation(session, generation_id))


@router.get("/{generation_id}/media")
async def video_media(
    generation_id: uuid.UUID,
    user: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    generation = await find_generation(session, generation_id)
    if not generation.file_key or not get_storage().exists(generation.file_key):
        raise HTTPException(404, "The video is not ready.")
    return FileResponse(
        get_storage().path(generation.file_key),
        # A narrated video is always a joined MP4, whichever provider made its shots.
        media_type="video/webm" if generation.file_key.endswith(".webm") else "video/mp4",
        headers={"Cache-Control": "private, no-store"},
    )


class RetryIn(BaseModel):
    # Submit an uncertain shot again: the provider may already have accepted (and billed) it.
    confirm_resubmit: bool = False


@router.post("/{generation_id}/retry", status_code=202)
async def retry_video(
    generation_id: uuid.UUID,
    body: RetryIn | None = None,
    user: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Go on with a failed narrated video from where it stopped."""
    generation = await find_generation(session, generation_id)
    job = await session.get(Job, generation.job_id) if generation.job_id else None
    confirm = bool(body and body.confirm_resubmit)
    if not (
        narrated_video.retryable(generation, job)
        or (confirm and narrated_video.needs_confirmation(generation, job))
    ):
        raise HTTPException(
            409,
            "This video cannot be retried as it is: it is not a failed narrated video, or a "
            "shot's submission was never confirmed and must be confirmed before it is sent "
            "again (it may be billed twice).",
        )
    shots, estimate = narrated_video.retry_plan(generation, confirm)
    await _ensure_room(generation.provider, estimate)
    await narrated_video.queue_retry(session, generation, shots)
    await session.commit()
    return await output(session, generation)


# Checking on a submitted video is its own short job: each check asks the provider once and,
# while the video is still rendering, queues the next check a few seconds later. The worker
# is never held while a provider renders, and no database connection is held during a call.
POLL_KIND = "poll_video"


@handler("generate_video")
async def generate_job(payload: dict) -> dict:
    generation_id = uuid.UUID(payload["generation_id"])
    async with get_sessionmaker()() as session:
        generation = await find_generation(session, generation_id)
        if generation.file_key:
            return {"file_key": generation.file_key}
        deadline = _deadline(generation.created_at)
        if not generation.provider_request:
            settings = get_settings()
            if not settings.enable_ai_video or (
                generation.provider != "fake" and not settings.live_ai_enabled
            ):
                raise UserFacingError("AI video generation is disabled for this demo.")
            if generation.submitted:
                raise UserFacingError(
                    "A video submission needs manual provider confirmation before retrying."
                )
            arguments = {**generation.payload, "request_id": generation.input_hash[:26]}
            image_key, input_hash = generation.image_key, generation.input_hash
            adapter = provider(generation.provider)
            generation.submitted = True
            generation.progress = "Submitting to provider"
            await session.commit()
            if image_key:
                data = await asyncio.to_thread(get_storage().path(image_key).read_bytes)
                arguments["image_url"] = "data:image/webp;base64," + base64.b64encode(data).decode()
            try:
                request = await gateway.call(
                    "video_submit",
                    adapter,
                    (input_hash,),
                    6,
                    lambda: adapter.submit(arguments),
                    charge_on_failure=True,
                )
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                raise UserFacingError(
                    "Video submission could not be confirmed. "
                    "Check the provider before trying again."
                ) from exc
            generation.provider_request = request
            generation.progress = "Waiting for provider"
            await session.commit()
    return await _check(generation_id, 1, deadline)


@handler(POLL_KIND)
async def poll_job(payload: dict) -> dict:
    return await _check(
        uuid.UUID(payload["generation_id"]),
        int(payload["number"]),
        datetime.fromisoformat(payload["deadline"]),
    )


def _deadline(queued_at: datetime) -> datetime:
    """Checks stop this long after the video was queued, however often a job is retried."""
    return queued_at + timedelta(seconds=get_settings().video_max_wait_seconds)


async def _check(generation_id: uuid.UUID, number: int, deadline: datetime) -> dict:
    """Ask the provider once. Ready: store the video. Still rendering: queue the next check,
    or give up once the maximum wait has passed (the request ID is kept for follow-up)."""
    async with get_sessionmaker()() as session:
        generation = await find_generation(session, generation_id)
        if generation.file_key:
            return {"file_key": generation.file_key}
        name, request, input_hash = (
            generation.provider,
            generation.provider_request,
            generation.input_hash,
        )
        story_id = generation.story_id
    adapter = provider(name)
    try:
        # A status check costs nothing and its answer changes, so it is neither charged nor
        # cached; only the finished video is.
        result = await adapter.poll(request)
        status = result["status"]
    except (httpx.HTTPError, ValueError, KeyError):
        status, result = "unavailable", {}

    if status == "done":
        free = FreeVideoRead(name)
        extension = clip_extension(name)

        async def download(url: str = result.get("video_url", "")) -> tuple[dict, bytes]:
            return {}, await adapter.download(url)

        try:
            _, cache_key = await gateway.call_file(
                "video_result", free, (input_hash,), 0, download, extension
            )
        except (httpx.HTTPError, UserFacingError, ValueError, KeyError):
            # The video is ready but did not arrive: fetch it again on the next check.
            status = "unavailable"
    if status == "done":
        target = f"stories/{story_id}/videos/{generation_id}/result{extension}"
        await asyncio.to_thread(get_storage().copy, cache_key, target)
        async with get_sessionmaker()() as session:
            generation = await find_generation(session, generation_id)
            generation.file_key = target
            generation.progress = "Video ready"
            await session.commit()
        return {"file_key": target, "checks": number}

    if datetime.now(UTC) >= deadline:
        raise UserFacingError(
            "The provider is still processing. Its request ID was saved for staff follow-up."
        )
    async with get_sessionmaker()() as session:
        generation = await find_generation(session, generation_id)
        generation.progress = {
            "running": "Rendering video",
            "unavailable": "Provider status unavailable; checking again",
        }.get(status, "Waiting for provider")
        job = await jobs.enqueue(
            session,
            POLL_KIND,
            {
                "generation_id": str(generation_id),
                "number": number + 1,
                "deadline": deadline.isoformat(),
            },
            # Each job queues at most one next check, keyed by itself, so a retried
            # submission starts a fresh chain instead of landing on an old finished check.
            idempotency_key=f"{POLL_KIND}:{generation_id}:{gateway.CURRENT_JOB.get()}",
            # A failed check is not retried: the next one is already the retry.
            max_attempts=1,
            run_after=datetime.now(UTC) + timedelta(seconds=get_settings().video_poll_seconds),
            commit=False,
        )
        generation.job_id = job.id  # the page follows the latest check
        await session.commit()
    return {"status": status, "check": number}
