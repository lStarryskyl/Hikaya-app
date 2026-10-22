"""Places and their photo galleries: WebP conversion, public URLs, and story covers."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Place, PlacePhoto, Story
from app.storage import LocalStorage, get_storage

WIDTHS = (480, 960, 1600)
SOURCE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

media_router = APIRouter(tags=["media"])


class PhotoOut(BaseModel):
    slug: str
    caption: str
    # width -> URL, e.g. {"480": "/media/places/petra-treasury/480.webp"}
    urls: dict[str, str]


def photo_key(slug: str, width: int) -> str:
    return f"places/{slug}/{width}.webp"


def photo_out(photo: PlacePhoto) -> PhotoOut:
    return PhotoOut(
        slug=photo.slug,
        caption=photo.caption,
        urls={str(w): f"/media/places/{photo.slug}/{w}.webp" for w in photo.widths},
    )


def find_source(folder: Path, slug: str) -> Path | None:
    return next(
        (folder / f"{slug}{s}" for s in SOURCE_SUFFIXES if (folder / f"{slug}{s}").is_file()),
        None,
    )


async def convert(source: Path, slug: str, storage: LocalStorage) -> list[int]:
    """Write a WebP for every width that does not exist yet. Returns the widths available."""
    for width in WIDTHS:
        target = storage.path(photo_key(slug, width))
        if target.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
            "-vf", f"scale='min({width},iw)':-2", "-c:v", "libwebp", "-quality", "78",
            str(target),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )  # fmt: skip
        _, err = await process.communicate()
        if process.returncode != 0:
            target.unlink(missing_ok=True)
            raise RuntimeError(f"could not convert {source.name}: {err.decode()[-300:]}")
    return list(WIDTHS)


async def slug_for_name(session: AsyncSession, name: str) -> str | None:
    if not name:
        return None
    return (
        await session.execute(select(Place.slug).where(func.lower(Place.name) == name.lower()))
    ).scalar_one_or_none()


async def cover_for(session: AsyncSession, story: Story) -> PlacePhoto | None:
    """The story's own cover photo, else its place's cover, else none."""
    slug = story.cover_photo_slug
    if slug is None and story.place_slug:
        place = await session.get(Place, story.place_slug)
        slug = place.cover_photo_slug if place else None
    return await session.get(PlacePhoto, slug) if slug else None


@media_router.get("/media/places/{slug}/{width}.webp", include_in_schema=False)
async def serve_place_photo(slug: str, width: int) -> FileResponse:
    storage = get_storage()
    if width not in WIDTHS:
        raise HTTPException(404, "Not found.")
    try:
        path = storage.path(photo_key(slug, width))
    except ValueError:
        raise HTTPException(404, "Not found.") from None
    if not path.is_file():
        raise HTTPException(404, "Not found.")
    # Public reference photos: safe to cache for a day.
    return FileResponse(
        path, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"}
    )
