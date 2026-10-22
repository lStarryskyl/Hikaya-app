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


# Read by content, not by name: several catalogue photos are JPEGs saved as .png.
_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png_pipe"),
    (b"\xff\xd8\xff", "jpeg_pipe"),
)


def image_demuxer(path: Path) -> str | None:
    """The FFmpeg demuxer for this image's real format, or None if it is not PNG/JPEG/WebP."""
    head = path.read_bytes()[:12]
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp_pipe"
    return next((demuxer for magic, demuxer in _IMAGE_MAGIC if head.startswith(magic)), None)


async def convert(source: Path, slug: str, storage: LocalStorage) -> list[int]:
    """Write a WebP for every width that does not exist yet. Returns the widths available."""
    demuxer = image_demuxer(source)
    if demuxer is None:
        raise RuntimeError(f"{source.name} is not a PNG, JPEG or WebP image")
    for width in WIDTHS:
        target = storage.path(photo_key(slug, width))
        if target.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-protocol_whitelist", "file", "-f", demuxer, "-i", str(source),
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


async def covers_for(session: AsyncSession, stories: list[Story]) -> dict:
    """story id -> cover photo (the story's own, else its place's, else None), in two queries."""
    place_slugs = {s.place_slug for s in stories if s.cover_photo_slug is None and s.place_slug}
    place_covers = dict(
        (
            await session.execute(
                select(Place.slug, Place.cover_photo_slug).where(Place.slug.in_(place_slugs))
            )
        ).all()
    ) if place_slugs else {}  # fmt: skip
    wanted = {s.id: s.cover_photo_slug or place_covers.get(s.place_slug) for s in stories}
    slugs = {slug for slug in wanted.values() if slug}
    photos = {
        p.slug: p
        for p in (
            await session.execute(select(PlacePhoto).where(PlacePhoto.slug.in_(slugs)))
        ).scalars()
    } if slugs else {}  # fmt: skip
    return {story_id: photos.get(slug) for story_id, slug in wanted.items()}


async def cover_out(session: AsyncSession, story: Story) -> PhotoOut | None:
    cover = (await covers_for(session, [story]))[story.id]
    return photo_out(cover) if cover else None


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
