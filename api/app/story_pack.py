"""Story packs: a published story with what its page shows, kept in the repository.

    python -m app.story_pack export <story id> <name> [root]   # root: api/seed/stories
    python -m app.story_pack import [--refresh] [root]

Export writes <root>/<name>/story.json and the media its page shows: the recording, the
narration, the slideshow, its photos and the video shown on the page. Never the uploaded
original or a voice sample, and never a story read in a cloned voice.

Import runs on every start after the demo seed (when SEED_DEMO_DATA is on): each pack whose
story is not there yet is added as it was, with no provider called and nothing paid for.
A story already there keeps the changes made in the app; --refresh replaces it.
"""

import argparse
import asyncio
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import media, narrated_video, photos, places, stories
from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.models import (
    Asset,
    AssetKind,
    Job,
    JobStatus,
    Narration,
    Place,
    PlacePhoto,
    Story,
    StoryPhoto,
    StoryStatus,
    TextLayer,
    User,
    VideoGeneration,
)
from app.seed_demo import NO_PASSWORD, storyteller_email
from app.storage import get_storage

log = logging.getLogger("hikaya.story_pack")

FORMAT = 1
DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "seed" / "stories"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
EXTENSIONS = {
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}
STORY_FIELDS = (
    "title",
    "category",
    "place_name",
    "place_slug",
    "latitude",
    "longitude",
    "original_language",
    "duration_ms",
    "tags",
    "narration_source",
    "consent_version",
)
SHOT_FIELDS = ("start_ms", "end_ms", "seconds", "lines", "prompt")
# Only these are files of the pack; anything else in its folder is left alone.
PACK_FILE = re.compile(
    r"^(story\.json|recording\.\w+|narration\.\w+|slideshow\.\w+|video\.\w+|photo-\d\d\.webp)$"
)


class PackError(Exception):
    """A story that cannot be exported, or a pack that cannot be read."""


def _extension(content_type: str) -> str:
    try:
        return EXTENSIONS[content_type.split(";")[0].strip()]
    except KeyError:
        raise PackError(f"No file type for {content_type}.") from None


def _when(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# --- export ---


async def export_story(
    sessionmaker: async_sessionmaker[AsyncSession], story_id: uuid.UUID, folder: Path
) -> Path:
    """Write the story's pack into `folder` (replacing an earlier pack there)."""
    if not NAME.match(folder.name):
        raise PackError("Name the pack with lowercase letters, digits and dashes.")
    storage = get_storage()
    files: dict[str, str] = {}  # pack file name -> storage key
    async with sessionmaker() as session:
        story = await session.get(Story, story_id)
        if story is None or story.status != StoryStatus.PUBLISHED:
            raise PackError("Only a published story can be exported.")
        narration = await session.get(Narration, story.id)
        video = await stories.shown_video(session, story)
        if (narration and narration.voice_clone_id) or (
            video and video.payload.get("voice_clone_id")
        ):
            raise PackError(
                "A story read in a cloned voice is not exported: revoking the voice must "
                "remove every copy of it."
            )
        author = await session.get(User, story.author_id)
        assets = await stories._audio_assets(session, story.id)
        layers = (
            await session.execute(
                select(TextLayer).where(TextLayer.story_id == story.id).order_by(TextLayer.kind)
            )
        ).scalars()
        data: dict = {
            "format": FORMAT,
            "story": {
                "id": str(story.id),
                **{field: getattr(story, field) for field in STORY_FIELDS},
                "consented_at": _when(story.consented_at),
                "published_at": _when(story.published_at),
            },
            "storyteller": {"id": str(author.id), "display_name": author.display_name},
            "layers": [
                {
                    "kind": layer.kind,
                    "language": layer.language,
                    "edited": layer.edited,
                    "segments": layer.segments,
                }
                for layer in layers
            ],
            "recording": None,
            "narration": None,
            "slideshow": None,
            "photos": [],
            "video": None,
        }

        if playable := assets.get(AssetKind.AUDIO):
            name = f"recording{_extension(playable.content_type)}"
            files[name] = playable.storage_key
            data["recording"] = {"file": name, "content_type": playable.content_type}
        if narration and (sound := await session.get(Asset, narration.asset_id)):
            name = f"narration{_extension(sound.content_type)}"
            files[name] = sound.storage_key
            data["narration"] = {
                "file": name,
                "content_type": sound.content_type,
                **{
                    field: getattr(narration, field)
                    for field in (
                        "provider",
                        "voice",
                        "language",
                        "source",
                        "timing",
                        "segments",
                        "input_hash",
                    )
                },
            }
        if slideshow := await media.slideshow_of(session, story.id):
            name = f"slideshow{_extension(slideshow.content_type)}"
            files[name] = slideshow.storage_key
            data["slideshow"] = {"file": name, "content_type": slideshow.content_type}
        for row in await photos._rows(session, [story.id]):
            if row.place_photo_slug:
                data["photos"].append({"gallery": row.place_photo_slug})
            else:
                name = f"photo-{sum(1 for p in data['photos'] if 'file' in p) + 1:02d}.webp"
                files[name] = photos._upload_key(row.id, story.id, max(row.widths))
                data["photos"].append({"file": name})
        if video:
            payload = {k: v for k, v in video.payload.items() if k != "audio_key"}
            files["video.mp4"] = video.file_key
            data["video"] = {
                "id": str(video.id),
                "file": "video.mp4",
                "provider": video.provider,
                "input_hash": video.input_hash,
                "payload": payload,
                # What each shot was made from; never provider request ids or file paths.
                "shots": [
                    {key: shot[key] for key in SHOT_FIELDS if key in shot} for shot in video.shots
                ],
                "script": video.script,
            }

    missing = [key for key in files.values() if not storage.exists(key)]
    if missing:
        raise PackError(f"Files are missing from the media store: {', '.join(missing)}")
    if folder.exists():
        if not (folder / "story.json").is_file():
            raise PackError(f"{folder} exists and is not a story pack.")
        for old in folder.iterdir():
            if old.is_file() and PACK_FILE.match(old.name):
                old.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    for name, key in files.items():
        (folder / name).write_bytes(storage.path(key).read_bytes())
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    (folder / "story.json").write_text(text, encoding="utf-8")
    return folder


# --- import ---


async def import_packs(
    sessionmaker: async_sessionmaker[AsyncSession],
    root: Path = DEFAULT_ROOT,
    *,
    refresh: bool = False,
) -> list[uuid.UUID]:
    """Add each pack under `root` whose story is not there yet (every one with `refresh`).
    Returns the stories added."""
    added: list[uuid.UUID] = []
    if not root.is_dir():
        return added
    for folder in sorted(p for p in root.iterdir() if (p / "story.json").is_file()):
        async with sessionmaker() as session:
            story_id = await _import(session, folder, refresh)
        if story_id:
            added.append(story_id)
            log.info("Story pack %s imported.", folder.name)
    return added


async def _storyteller(session: AsyncSession, data: dict) -> User:
    """The storyteller's account here: the same one when it exists, else one that cannot
    sign in, like the seeded storytellers."""
    user_id = uuid.UUID(data["id"])
    user = await session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            email=storyteller_email(f"pack-{user_id.hex[:12]}"),
            display_name=data["display_name"],
            password_hash=NO_PASSWORD,
        )
        session.add(user)
        await session.flush()
    return user


def _write(folder: Path, name: str, key: str) -> int:
    source = folder / name
    if source.parent != folder or not source.is_file():
        raise PackError(f"{folder.name}: {name} is missing.")
    get_storage().write_bytes(key, source.read_bytes())
    return get_storage().size(key)


async def _forget(session: AsyncSession, story: Story) -> None:
    """Delete the story here, its rows and then its files, before the pack's come in (they
    may be written at the same paths)."""
    keys = [
        a.storage_key
        for a in (await session.execute(select(Asset).where(Asset.story_id == story.id))).scalars()
    ]
    for row in await photos._rows(session, [story.id]):
        keys += [photos._upload_key(row.id, story.id, w) for w in row.widths or []]
    videos = await session.execute(
        select(VideoGeneration).where(VideoGeneration.story_id == story.id)
    )
    for v in videos.scalars():
        keys += [v.file_key, v.image_key, v.payload.get("audio_key")]
    await session.delete(story)
    # Committed on its own: the story comes back with the same id, as a new row.
    await session.commit()
    get_storage().delete(*[key for key in keys if key])


async def _import(session: AsyncSession, folder: Path, refresh: bool) -> uuid.UUID | None:
    try:
        data = json.loads((folder / "story.json").read_text(encoding="utf-8"))
    except ValueError as exc:
        raise PackError(f"{folder.name}: story.json is not readable ({exc}).") from None
    if data.get("format") != FORMAT:
        raise PackError(f"{folder.name}: unknown pack format {data.get('format')!r}.")
    fields = data["story"]
    story_id = uuid.UUID(fields["id"])
    existing = await session.get(Story, story_id)
    if existing is not None and not refresh:
        return None
    if existing is not None:
        await _forget(session, existing)

    storage = get_storage()
    author = await _storyteller(session, data["storyteller"])
    story = Story(
        id=story_id,
        author_id=author.id,
        status=StoryStatus.PUBLISHED.value,
        **{field: fields.get(field) for field in STORY_FIELDS if fields.get(field) is not None},
        consented_at=datetime.fromisoformat(fields["consented_at"])
        if fields.get("consented_at")
        else None,
        published_at=datetime.fromisoformat(fields["published_at"])
        if fields.get("published_at")
        else datetime.now(UTC),
    )
    if story.place_slug and await session.get(Place, story.place_slug) is None:
        story.place_slug = None  # a place this copy does not have
    session.add(story)
    await session.flush()
    for layer in data["layers"]:
        session.add(TextLayer(story_id=story.id, **layer))

    def asset(kind: str, name: str, content_type: str, key: str) -> Asset:
        row = Asset(
            story_id=story.id,
            kind=kind,
            storage_key=key,
            content_type=content_type,
            size_bytes=_write(folder, name, key),
        )
        session.add(row)
        return row

    token = uuid.uuid4().hex
    if recording := data.get("recording"):
        ext = Path(recording["file"]).suffix
        # The pack carries only the recording the page plays; it also stands as its original.
        for kind, key in (
            (AssetKind.AUDIO, f"stories/{story.id}/{token}{ext}"),
            (AssetKind.ORIGINAL_AUDIO, f"stories/{story.id}/{token}-original{ext}"),
        ):
            asset(kind.value, recording["file"], recording["content_type"], key)
    if narration := data.get("narration"):
        ext = Path(narration["file"]).suffix
        sound = asset(
            AssetKind.NARRATION.value,
            narration["file"],
            narration["content_type"],
            f"stories/{story.id}/narration/{token}{ext}",
        )
        await session.flush()
        session.add(
            Narration(
                story_id=story.id,
                asset_id=sound.id,
                **{k: v for k, v in narration.items() if k not in ("file", "content_type")},
            )
        )
    if slideshow := data.get("slideshow"):
        ext = Path(slideshow["file"]).suffix
        asset(
            AssetKind.SLIDESHOW.value,
            slideshow["file"],
            slideshow["content_type"],
            f"stories/{story.id}/slideshow/{token}{ext}",
        )

    for position, photo in enumerate(data.get("photos", [])):
        if slug := photo.get("gallery"):
            if await session.get(PlacePhoto, slug) is not None:
                session.add(StoryPhoto(story_id=story.id, position=position, place_photo_slug=slug))
            continue
        photo_id = uuid.uuid4()
        source = f"stories/{story.id}/photos/{photo_id.hex}/pack.webp"
        _write(folder, photo["file"], source)
        try:
            widths = await places.convert_image(
                storage.path(source),
                lambda w, photo_id=photo_id: photos._upload_key(photo_id, story.id, w),
                storage,
            )
        except places.NotAnImage:
            raise PackError(f"{folder.name}: {photo['file']} is not a photo.") from None
        finally:
            storage.delete(source)
        session.add(StoryPhoto(id=photo_id, story_id=story.id, position=position, widths=widths))

    if video := data.get("video"):
        generation_id = uuid.UUID(video["id"])
        file_key = f"stories/{story.id}/videos/{generation_id}/result.mp4"
        _write(folder, video["file"], file_key)
        # The finished job the video was made by (kept when the story was deleted).
        idempotency_key = f"{narrated_video.KIND}:{video['input_hash']}"
        job = (
            await session.execute(select(Job).where(Job.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if job is None:
            job = Job(kind=narrated_video.KIND, idempotency_key=idempotency_key)
            session.add(job)
        job.payload = {"generation_id": str(generation_id)}
        job.status, job.error = JobStatus.DONE, None
        job.finished_at = datetime.now(UTC)
        job.result = {"imported": folder.name}
        await session.flush()
        session.add(
            VideoGeneration(
                id=generation_id,
                story_id=story.id,
                actor_id=author.id,
                provider=video["provider"],
                payload=video["payload"],
                input_hash=video["input_hash"],
                submitted=True,
                file_key=file_key,
                shots=video.get("shots") or [],
                script=video.get("script"),
                progress="Video ready",
                job_id=job.id,
            )
        )
        await session.flush()
        story.featured_video_id = generation_id

    await session.commit()
    return story.id


# --- command line ---


async def _run(args: argparse.Namespace) -> None:
    sessionmaker = get_sessionmaker()
    try:
        if args.command == "export":
            folder = await export_story(
                sessionmaker, uuid.UUID(args.story_id), Path(args.root) / args.name
            )
            log.info("Story pack written to %s.", folder)
        elif not get_settings().seed_demo_data:
            log.info("SEED_DEMO_DATA is off; no story packs loaded.")
        else:
            added = await import_packs(sessionmaker, Path(args.root), refresh=args.refresh)
            log.info("Story packs ready: %d added.", len(added))
    finally:
        await dispose_engine()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="python -m app.story_pack")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="write a published story's pack")
    export.add_argument("story_id")
    export.add_argument("name", help="the pack's folder: lowercase letters, digits and dashes")
    export.add_argument("root", nargs="?", default=str(DEFAULT_ROOT))
    load = commands.add_parser("import", help="add the packs whose stories are not here yet")
    load.add_argument("--refresh", action="store_true", help="replace stories already here")
    load.add_argument("root", nargs="?", default=str(DEFAULT_ROOT))
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
