"""A story's photos: uploads (stored as WebP at three widths) and picks from place galleries.

Photos are ordered; the first is the story's cover. Without photos, the cover falls back to
the story's chosen place photo, then its place's cover.
"""

import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import places
from app.auth import current_user_optional
from app.config import get_settings
from app.db import get_session
from app.models import PlacePhoto, Story, StoryPhoto, StoryStatus, User
from app.places import WIDTHS, PhotoOut
from app.storage import LocalStorage, TooLarge, get_storage
from app.visibility import can_view

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}

media_router = APIRouter(tags=["media"])


class StoryPhotoOut(BaseModel):
    id: uuid.UUID
    source: Literal["upload", "gallery"]
    photo: PhotoOut


class PhotoLimit(Exception):
    """A photo request broke a rule (or named a missing photo): HTTP status + plain message.

    An app-wide exception handler turns it into the response, so routes just let it rise."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def _upload_key(photo_id: uuid.UUID, story_id: uuid.UUID, width: int) -> str:
    return f"stories/{story_id}/photos/{photo_id.hex}/{width}.webp"


def _out(row: StoryPhoto, place_photo: PlacePhoto | None) -> StoryPhotoOut:
    if row.place_photo_slug and place_photo is not None:
        return StoryPhotoOut(id=row.id, source="gallery", photo=places.photo_out(place_photo))
    urls = {str(w): f"/media/story-photos/{row.id}/{w}.webp" for w in row.widths or []}
    return StoryPhotoOut(
        id=row.id, source="upload", photo=PhotoOut(slug=str(row.id), caption="", urls=urls)
    )


async def _rows(session: AsyncSession, story_ids: list[uuid.UUID]) -> list[StoryPhoto]:
    return list(
        (
            await session.execute(
                select(StoryPhoto)
                .where(StoryPhoto.story_id.in_(story_ids))
                .order_by(StoryPhoto.story_id, StoryPhoto.position)
            )
        ).scalars()
    )


async def _place_photos(session: AsyncSession, rows: list[StoryPhoto]) -> dict[str, PlacePhoto]:
    slugs = {r.place_photo_slug for r in rows if r.place_photo_slug}
    if not slugs:
        return {}
    found = await session.execute(select(PlacePhoto).where(PlacePhoto.slug.in_(slugs)))
    return {p.slug: p for p in found.scalars()}


async def list_for(session: AsyncSession, story_id: uuid.UUID) -> list[StoryPhotoOut]:
    rows = await _rows(session, [story_id])
    gallery = await _place_photos(session, rows)
    return [_out(r, gallery.get(r.place_photo_slug or "")) for r in rows]


async def covers_for(
    session: AsyncSession, stories: list[Story]
) -> dict[uuid.UUID, PhotoOut | None]:
    """story id -> PhotoOut | None: the first story photo, else the place photo fallback."""
    rows = await _rows(session, [s.id for s in stories])
    first: dict[uuid.UUID, StoryPhoto] = {}
    for row in rows:
        first.setdefault(row.story_id, row)
    gallery = await _place_photos(session, list(first.values()))
    without = [s for s in stories if s.id not in first]
    fallback = await places.place_covers_for(session, without) if without else {}
    out = {}
    for story in stories:
        if story.id in first:
            row = first[story.id]
            out[story.id] = _out(row, gallery.get(row.place_photo_slug or "")).photo
        else:
            photo = fallback.get(story.id)
            out[story.id] = places.photo_out(photo) if photo else None
    return out


async def cover_out(session: AsyncSession, story: Story) -> PhotoOut | None:
    return (await covers_for(session, [story]))[story.id]


async def _check_room(session: AsyncSession, story: Story) -> int:
    """The next position, or PhotoLimit when the story is full.

    Locks the story row until the caller commits, so two additions at once cannot take the
    same position or both squeeze under the limit."""
    await session.execute(select(Story.id).where(Story.id == story.id).with_for_update())
    count = len(await _rows(session, [story.id]))
    limit = get_settings().max_photos_per_story
    if count >= limit:
        raise PhotoLimit(409, f"A story can have up to {limit} photos.")
    return count


async def add_upload(
    session: AsyncSession, story: Story, upload: UploadFile, storage: LocalStorage
) -> StoryPhotoOut:
    if (upload.content_type or "").split(";")[0].strip().lower() not in IMAGE_TYPES:
        raise PhotoLimit(415, "Add a photo in PNG, JPEG or WebP format.")
    position = await _check_room(session, story)
    settings = get_settings()
    photo_id = uuid.uuid4()
    original_key = f"stories/{story.id}/photos/{photo_id.hex}/original"
    try:
        await storage.save_upload(
            original_key, upload, int(settings.max_photo_upload_mb * 1024 * 1024)
        )
    except TooLarge:
        raise PhotoLimit(
            413, f"Photos can be up to {settings.max_photo_upload_mb:g} MB each."
        ) from None
    try:
        width, height = await places.image_size(storage.path(original_key))
        if width * height > settings.max_photo_megapixels * 1_000_000:
            raise PhotoLimit(
                422, f"Photos can be up to {settings.max_photo_megapixels:g} megapixels."
            )
        widths = await places.convert_image(
            storage.path(original_key),
            lambda w: _upload_key(photo_id, story.id, w),
            storage,
        )
        row = StoryPhoto(id=photo_id, story_id=story.id, position=position, widths=widths)
        session.add(row)
        await session.commit()
    except places.NotAnImage:
        _delete_files(storage, photo_id, story.id)
        raise PhotoLimit(422, "That file is not a readable photo.") from None
    except BaseException:
        # Nothing may stay on disk without a row pointing at it.
        _delete_files(storage, photo_id, story.id)
        raise
    finally:
        storage.delete(original_key)  # only the WebP copies are kept
    return _out(row, None)


async def add_gallery_pick(session: AsyncSession, story: Story, slug: str) -> StoryPhotoOut:
    photo = await session.get(PlacePhoto, slug)
    if photo is None:
        raise PhotoLimit(404, "No such gallery photo.")
    position = await _check_room(session, story)
    if any(r.place_photo_slug == slug for r in await _rows(session, [story.id])):
        raise PhotoLimit(409, "That photo is already in your story.")
    row = StoryPhoto(story_id=story.id, position=position, place_photo_slug=slug)
    session.add(row)
    await session.commit()
    return _out(row, photo)


def _delete_files(storage: LocalStorage, photo_id: uuid.UUID, story_id: uuid.UUID) -> None:
    storage.delete(*(_upload_key(photo_id, story_id, w) for w in WIDTHS))


async def remove(
    session: AsyncSession, story: Story, photo_id: uuid.UUID, storage: LocalStorage
) -> None:
    row = await session.get(StoryPhoto, photo_id)
    if row is None or row.story_id != story.id:
        raise PhotoLimit(404, "No such photo.")
    await session.delete(row)
    await _renumber(session, story.id, exclude=photo_id)
    await session.commit()
    if row.place_photo_slug is None:  # never delete a shared gallery photo
        _delete_files(storage, row.id, story.id)


async def _renumber(
    session: AsyncSession, story_id: uuid.UUID, exclude: uuid.UUID | None = None
) -> None:
    rows = [r for r in await _rows(session, [story_id]) if r.id != exclude]
    for i, r in enumerate(rows):
        r.position = i


async def reorder(session: AsyncSession, story: Story, ids: list[uuid.UUID]) -> None:
    rows = await _rows(session, [story.id])
    if sorted(ids) != sorted(r.id for r in rows) or len(set(ids)) != len(ids):
        raise PhotoLimit(422, "List every photo of the story exactly once.")
    by_id = {r.id: r for r in rows}
    for i, photo_id in enumerate(ids):
        by_id[photo_id].position = i
    await session.commit()


@media_router.get("/media/story-photos/{photo_id}/{width}.webp", include_in_schema=False)
async def serve_story_photo(
    photo_id: str,
    width: int,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> FileResponse:
    try:
        row = await session.get(StoryPhoto, uuid.UUID(photo_id))
    except ValueError:
        row = None
    story = await session.get(Story, row.story_id) if row else None
    if row is None or story is None or width not in (row.widths or []) or not can_view(story, user):
        raise HTTPException(404, "Not found.")
    path: Path = storage.path(_upload_key(row.id, story.id, width))
    if not path.is_file():
        raise HTTPException(404, "Not found.")
    cache = "no-cache" if story.status == StoryStatus.PUBLISHED else "private, no-store"
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": cache})


async def photo_limit_response(_request: Request, exc: PhotoLimit) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=exc.status)
