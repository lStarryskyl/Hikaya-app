"""Staff video generation: queue locally, persist provider requests, poll, store media."""

import asyncio
import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import gateway, jobs, photos
from app.auth import require_roles
from app.config import get_settings
from app.db import get_session, get_sessionmaker
from app.errors import INTERNAL_PREFIX, UserFacingError
from app.handlers import handler
from app.models import Job, Role, Story, TextLayer, User, VideoGeneration
from app.providers.video import FreeVideoRead, configurations, provider
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
    }


@router.get("/config")
async def config(user: User = Depends(staff)) -> dict:
    return {
        "enabled": get_settings().enable_ai_video,
        "default_provider": get_settings().video_provider,
        "providers": configurations(),
    }


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
    selected = next((item for item in configurations() if item["id"] == body.provider), None)
    if not selected or not selected["available"] or body.model not in selected["models"]:
        raise HTTPException(422, "Choose an available provider and supported model.")
    story = await session.get(Story, body.story_id)
    if not story:
        raise HTTPException(404, "Story not found.")
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
    images = await photos.slideshow_images(session, story)
    if not images and body.provider != "fake":
        raise HTTPException(422, "Add a story photo before generating an AI video.")
    generation_id = uuid.uuid4()
    payload = {
        "model": body.model,
        "prompt": prompt,
        "aspect_ratio": body.aspect_ratio if selected.get("supports_aspect", True) else "source",
        "seed": body.seed if selected.get("supports_seed", True) else 0,
    }
    image_hash = ""
    image_key = None
    if images:
        storage = get_storage()
        if not storage.exists(images[0]):
            raise HTTPException(422, "The story photo is missing. Choose another photo.")
        image_bytes = await asyncio.to_thread(storage.path(images[0]).read_bytes)
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        image_key = f"stories/{story.id}/videos/{generation_id}/input.webp"
    digest = hashlib.sha256(
        json.dumps([str(story.id), body.provider, payload, image_hash], sort_keys=True).encode()
    ).hexdigest()
    existing = (
        await session.execute(select(VideoGeneration).where(VideoGeneration.input_hash == digest))
    ).scalar_one_or_none()
    if existing:
        return await output(session, existing)
    if image_key:
        await asyncio.to_thread(get_storage().write_bytes, image_key, image_bytes)
    try:
        job = await jobs.enqueue(
            session,
            "generate_video",
            {"generation_id": str(generation_id)},
            idempotency_key=f"video:{digest}",
            max_attempts=1,
            commit=False,
        )
        generation = VideoGeneration(
            id=generation_id,
            story_id=story.id,
            actor_id=user.id,
            provider=body.provider,
            payload=payload,
            image_key=image_key,
            input_hash=digest,
            job_id=job.id,
        )
        session.add(generation)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        get_storage().delete_tree(f"stories/{story.id}/videos/{generation_id}")
        raise HTTPException(409, "This video was already queued. Refresh the job list.") from None
    return await output(session, generation)


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
        media_type="video/webm" if generation.provider == "fake" else "video/mp4",
        headers={"Cache-Control": "private, no-store"},
    )


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
        extension = ".webm" if name == "fake" else ".mp4"

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
