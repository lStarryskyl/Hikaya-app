"""Narration and the slideshow, made in the worker once a story is published.

Both are pipeline steps with an input hash, so republishing after an edit re-runs only what
the edit changed: narration when the text it reads (or its source choice) changed, the
slideshow when the photos or the recording changed. A story is published without waiting for
either; the player shows what exists.

Narration timings come from the voice provider's alignment data when it offers them (the
whole text in one call). Otherwise each line is spoken on its own, measured, and joined.
Every spoken piece is cached as a file by a hash of its input, so nothing is paid for twice.
"""

import asyncio
import json
import shutil
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audio, gateway, photos
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import UserFacingError
from app.handlers import handler
from app.models import Asset, AssetKind, Narration, PipelineStep, Story
from app.pipeline import POLISHED, STALE, TARGET_LAYER, get_layer, is_current, queue_step, step_hash
from app.providers import TextToSpeech, text_to_speech
from app.storage import get_storage

NARRATE, SLIDESHOW = "narrate", "slideshow"
SOURCES = ("polished", "msa")
MP3, MP4 = "audio/mpeg", "video/mp4"

# The slideshow: 720p at 25 frames a second, each photo held for an equal share of the
# recording with a slow zoom or pan and a short fade. Bump RENDER_VERSION when the look
# changes, so published slideshows are rendered again.
RENDER_VERSION = "1"
WIDTH, HEIGHT, FPS = 1280, 720, 25
FADE_SECONDS = 0.6
RENDER_TIMEOUT_SECONDS = 900


def source_layer(story: Story) -> str:
    """The text layer the narration reads. An MSA story's polished text is already MSA."""
    if story.narration_source == "msa" and story.original_language != "msa":
        return TARGET_LAYER["msa"]
    return POLISHED


def source_step(story: Story) -> str:
    return "translate_msa" if source_layer(story) != POLISHED else "polish"


async def queue(session: AsyncSession, story: Story) -> None:
    """Queue narration and the slideshow for a story being published, in the caller's
    transaction. A step whose input has not changed is left as it is."""
    await _queue_narration(session, story)
    await _queue_slideshow(session, story)


async def _queue_narration(session: AsyncSession, story: Story) -> None:
    layer = await get_layer(session, story.id, source_layer(story))
    if layer is None:
        return
    texts = [s["text"] for s in layer.segments]
    input_hash = step_hash(
        NARRATE,
        get_settings().tts_provider,
        story.narration_source,
        layer.language,
        json.dumps(texts, ensure_ascii=False),
    )
    await queue_step(
        session,
        story.id,
        NARRATE,
        NARRATE,
        input_hash,
        source=story.narration_source,
        language=layer.language,
        texts=texts,
    )


async def _queue_slideshow(session: AsyncSession, story: Story) -> None:
    images = await photos.slideshow_images(session, story)
    recording = await session.get(PipelineStep, (story.id, "transcribe"))
    audio_asset = (
        await session.execute(
            select(Asset).where(Asset.story_id == story.id, Asset.kind == AssetKind.AUDIO)
        )
    ).scalar_one_or_none()
    if not images or recording is None or audio_asset is None:
        return
    # The transcription hash changes with the recording, so it stands in for the audio.
    input_hash = step_hash(SLIDESHOW, RENDER_VERSION, recording.input_hash, json.dumps(images))
    await queue_step(
        session,
        story.id,
        SLIDESHOW,
        SLIDESHOW,
        input_hash,
        images=images,
        audio=audio_asset.storage_key,
        duration_ms=story.duration_ms or 0,
    )


# --- shared ---


async def _ffmpeg(*args: str, timeout: int = RENDER_TIMEOUT_SECONDS) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file", *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    try:
        _, err = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("FFmpeg timed out") from None
    if process.returncode != 0:
        # Internal detail: the job keeps it, the member sees a generic message.
        raise RuntimeError(f"FFmpeg failed: {err.decode(errors='replace')[-500:]}")


async def _replace_asset(
    session: AsyncSession, story_id: uuid.UUID, kind: AssetKind, key: str, content_type: str
) -> tuple[Asset, list[str]]:
    """Add the new file's asset and drop the old ones; returns the old keys to delete."""
    old = list(
        (
            await session.execute(
                select(Asset).where(Asset.story_id == story_id, Asset.kind == kind)
            )
        ).scalars()
    )
    asset = Asset(
        story_id=story_id,
        kind=kind.value,
        storage_key=key,
        content_type=content_type,
        size_bytes=get_storage().size(key),
    )
    session.add(asset)
    for row in old:
        await session.delete(row)
    await session.flush()
    return asset, [row.storage_key for row in old]


def _new_key(story_id: uuid.UUID, kind: str, extension: str) -> str:
    return f"stories/{story_id}/{kind}/{uuid.uuid4().hex}{extension}"


# --- narration ---


async def _speak(
    tts: TextToSpeech, texts: list[str], language: str, voice: str
) -> tuple[Path, list | None]:
    """Speak through the gateway; returns the cached MP3 and the provider's line timings."""
    parts = (language, voice, json.dumps(texts, ensure_ascii=False))
    file_key = gateway.file_key_for("speak", tts, parts, ".mp3")
    storage = get_storage()

    async def run() -> dict:
        speech = await tts.speak(texts, language, voice)
        path = storage.path(file_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, speech.audio)
        return {"lines": [list(line) for line in speech.lines] if speech.lines else None}

    result = await gateway.call(
        "speak", tts, parts, sum(len(t) for t in texts), run, file_key=file_key
    )
    return storage.path(file_key), result["lines"]


async def _join(pieces: list[Path], target: Path) -> None:
    """One MP3 of the pieces in order, encoded like every other recording."""
    target.parent.mkdir(parents=True, exist_ok=True)
    inputs = [arg for piece in pieces for arg in ("-f", "mp3", "-i", str(piece))]
    labels = "".join(f"[{i}:a]" for i in range(len(pieces)))
    await _ffmpeg(
        *inputs,
        "-filter_complex", f"{labels}concat=n={len(pieces)}:v=0:a=1[a]", "-map", "[a]",
        "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "96k", str(target),
    )  # fmt: skip


@handler(NARRATE)
async def narrate(payload: dict) -> dict:
    story_id = uuid.UUID(payload["story_id"])
    async with get_sessionmaker()() as session:
        if not await is_current(session, payload):
            return STALE
    texts, language = payload["texts"], payload["language"]
    tts = text_to_speech()
    voice = tts.voice_for(language)
    storage = get_storage()
    key = _new_key(story_id, "narration", ".mp3")
    target = storage.path(key)

    if tts.aligns:
        spoken, lines = await _speak(tts, texts, language, voice)
        if lines is None or len(lines) != len(texts):
            raise UserFacingError("The voice service returned timings that do not match the text.")
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        # A copy, so deleting the story never removes a cached result.
        await asyncio.to_thread(shutil.copyfile, spoken, target)
        timing = "alignment"
    else:
        pieces, lines, at = [], [], 0
        for text in texts:
            piece, _ = await _speak(tts, [text], language, voice)
            length = await audio.duration_ms(piece)
            pieces.append(piece)
            lines.append((at, at + length))
            at += length
        await _join(pieces, target)
        timing = "per_segment"

    segments = [
        {"start_ms": int(start), "end_ms": int(end), "text": text}
        for (start, end), text in zip(lines, texts, strict=True)
    ]
    async with get_sessionmaker()() as session:
        if not await is_current(session, payload, lock=True):
            storage.delete(key)
            return STALE
        asset, old_keys = await _replace_asset(session, story_id, AssetKind.NARRATION, key, MP3)
        row = await session.get(Narration, story_id)
        if row is None:
            row = Narration(story_id=story_id)
            session.add(row)
        row.asset_id, row.provider, row.voice = asset.id, tts.name, voice
        row.language, row.source, row.timing = language, payload["source"], timing
        row.segments = segments
        await session.commit()
    await asyncio.to_thread(storage.delete, *old_keys)
    return {"segments": len(segments), "timing": timing}


# --- slideshow ---

# Zoom in, zoom out, pan right, pan left; z is the zoom, x and y the visible window's corner.
_MOTIONS = (
    ("1+0.15*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("1.15-0.15*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("1.12", "(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),
    ("1.12", "(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)"),
)


def slideshow_filters(count: int, seconds: float) -> tuple[str, int]:
    """The FFmpeg filter graph for `count` photos sharing `seconds`, and frames per photo."""
    frames = max(1, round(seconds * FPS / count))
    hold = frames / FPS
    fade = min(FADE_SECONDS, hold / 3)
    chains = []
    for i in range(count):
        z, x, y = (part.format(n=frames) for part in _MOTIONS[i % len(_MOTIONS)])
        chains.append(
            f"[{i}:v]scale={WIDTH * 3 // 2}:{HEIGHT * 3 // 2}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH * 3 // 2}:{HEIGHT * 3 // 2},setsar=1,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"fade=t=in:st=0:d={fade:.2f},fade=t=out:st={hold - fade:.2f}:d={fade:.2f}[v{i}]"
        )
    joined = "".join(f"[v{i}]" for i in range(count))
    chains.append(f"{joined}concat=n={count}:v=1:a=0,format=yuv420p[v]")
    return ";".join(chains), frames


@handler(SLIDESHOW)
async def slideshow(payload: dict) -> dict:
    story_id = uuid.UUID(payload["story_id"])
    async with get_sessionmaker()() as session:
        if not await is_current(session, payload):
            return STALE
    storage = get_storage()
    images = [storage.path(k) for k in payload["images"] if storage.exists(k)]
    recording = storage.path(payload["audio"])
    if not images or not recording.is_file():
        raise UserFacingError("The photos or the recording for the slideshow are missing.")
    seconds = (payload["duration_ms"] or await audio.duration_ms(recording)) / 1000
    graph, _ = slideshow_filters(len(images), seconds)
    key = _new_key(story_id, "slideshow", ".mp4")
    target = storage.path(key)
    await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
    inputs = [arg for image in images for arg in ("-f", "webp_pipe", "-i", str(image))]
    # Render to a scratch name first, so a half-written file is never served.
    with tempfile.TemporaryDirectory(dir=target.parent) as scratch:
        partial = Path(scratch) / "render.mp4"
        await _ffmpeg(
            *inputs, "-f", "mp3", "-i", str(recording),
            "-filter_complex", graph, "-map", "[v]", "-map", f"{len(images)}:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
            str(partial),
        )  # fmt: skip
        await asyncio.to_thread(partial.replace, target)

    async with get_sessionmaker()() as session:
        if not await is_current(session, payload, lock=True):
            storage.delete(key)
            return STALE
        _, old_keys = await _replace_asset(session, story_id, AssetKind.SLIDESHOW, key, MP4)
        await session.commit()
    await asyncio.to_thread(storage.delete, *old_keys)
    return {"photos": len(images), "seconds": round(seconds, 1)}


async def narration_for(
    session: AsyncSession, story_id: uuid.UUID
) -> tuple[Narration, Asset] | None:
    row = await session.get(Narration, story_id)
    if row is None:
        return None
    asset = await session.get(Asset, row.asset_id)
    return (row, asset) if asset is not None else None
