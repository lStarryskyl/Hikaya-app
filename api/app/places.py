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


class NotAnImage(Exception):
    pass


FFMPEG_TIMEOUT_SECONDS = 120


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), FFMPEG_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        return -1, b"", b"timed out"
    return process.returncode, out, err


async def image_size(source: Path) -> tuple[int, int]:
    """(width, height) from the image header, without decoding the picture."""
    demuxer = image_demuxer(source)
    if demuxer is None:
        raise NotAnImage(f"{source.name} is not a PNG, JPEG or WebP image")
    code, out, _ = await _run(
        "ffprobe", "-v", "error", "-protocol_whitelist", "file", "-f", demuxer,
        "-select_streams", "v:0", "-show_entries", "stream=width,height",
        "-of", "csv=p=0", str(source),
    )  # fmt: skip
    try:
        width, height = (int(n) for n in out.decode().strip().split(",")[:2])
    except ValueError:
        raise NotAnImage(f"{source.name} has no readable size") from None
    if code != 0 or width <= 0 or height <= 0:
        raise NotAnImage(f"{source.name} has no readable size")
    return width, height


async def convert(source: Path, slug: str, storage: LocalStorage) -> list[int]:
    """Place photo: write a WebP for every width not converted yet. Returns the widths."""
    return await convert_image(source, lambda width: photo_key(slug, width), storage)


async def convert_image(source: Path, key_for, storage: LocalStorage) -> list[int]:
    """Write `source` as WebP at every width (skipping files that exist) under key_for(width).

    The demuxer comes from the file's content, so FFmpeg never guesses a format, and only
    the file protocol is allowed. Raises NotAnImage for anything but PNG, JPEG or WebP.
    """
    demuxer = image_demuxer(source)
    if demuxer is None:
        raise NotAnImage(f"{source.name} is not a PNG, JPEG or WebP image")
    for width in WIDTHS:
        target = storage.path(key_for(width))
        if target.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        code, _, err = await _run(
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-protocol_whitelist", "file", "-f", demuxer, "-i", str(source),
            "-vf", f"scale='min({width},iw)':-2", "-c:v", "libwebp", "-quality", "78",
            str(target),
        )  # fmt: skip
        if code != 0:
            target.unlink(missing_ok=True)
            raise NotAnImage(f"could not convert {source.name}: {err.decode()[-300:]}")
    return list(WIDTHS)


async def slug_for_name(session: AsyncSession, name: str) -> str | None:
    if not name:
        return None
    return (
        await session.execute(select(Place.slug).where(func.lower(Place.name) == name.lower()))
    ).scalar_one_or_none()


async def place_covers_for(session: AsyncSession, stories: list[Story]) -> dict:
    """story id -> place photo cover (the story's chosen one, else its place's), two queries."""
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
