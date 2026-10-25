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


@handler("generate_video")
async def generate_job(payload: dict) -> dict:
    async with get_sessionmaker()() as session:
        generation = await find_generation(session, uuid.UUID(payload["generation_id"]))
        adapter = provider(generation.provider)
        if generation.file_key:
            return {"file_key": generation.file_key}
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
            if generation.image_key:
                data = await asyncio.to_thread(get_storage().path(generation.image_key).read_bytes)
                arguments["image_url"] = "data:image/webp;base64," + base64.b64encode(data).decode()
            generation.submitted = True
            generation.progress = "Submitting to provider"
            await session.commit()
            try:
                generation.provider_request = await gateway.call(
                    "video_submit",
                    adapter,
                    (generation.input_hash,),
                    6,
                    lambda: adapter.submit(arguments),
                    charge_on_failure=True,
                )
                await session.commit()
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                raise UserFacingError(
                    "Video submission could not be confirmed. "
                    "Check the provider before trying again."
                ) from exc
        free = FreeVideoRead(adapter.name)
        # Stay below the worker's stale-job threshold. Unfinished remote jobs keep their ID.
        until = datetime.now(UTC) + timedelta(seconds=480)
        poll_number = 0
        while datetime.now(UTC) < until:
            poll_number += 1
            try:
                result = await gateway.call(
                    "video_status",
                    free,
                    (str(generation.id), str(datetime.now(UTC).timestamp()), str(poll_number)),
                    0,
                    lambda: adapter.poll(generation.provider_request),
                )
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                raise UserFacingError(
                    "Video status is unavailable. "
                    "The provider request was saved; do not submit it again."
                ) from exc
            generation.progress = (
                "Rendering video" if result["status"] == "running" else "Waiting for provider"
            )
            await session.commit()
            if result["status"] == "done":

                async def download(url: str = result["video_url"]) -> tuple[dict, bytes]:
                    return {}, await adapter.download(url)

                _, cache_file = await gateway.call_file(
                    "video_result",
                    free,
                    (generation.input_hash,),
                    0,
                    download,
                    ".webm" if generation.provider == "fake" else ".mp4",
                )
                target = f"stories/{generation.story_id}/videos/{generation.id}/result" + (
                    ".webm" if generation.provider == "fake" else ".mp4"
                )
                await asyncio.to_thread(get_storage().copy, cache_file, target)
                generation.file_key = target
                generation.progress = "Video ready"
                await session.commit()
                return {"file_key": target}
            await asyncio.sleep(get_settings().video_poll_seconds)
        raise UserFacingError(
            "The provider is still processing. Its request ID was saved for staff follow-up."
        )
