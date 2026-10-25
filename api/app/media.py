"""Narration and the slideshow, made in the worker from a submitted story's finished text.

Narration is queued on submit, alongside the moderation check, so reviewers hear held
stories too; nothing is spent on drafts. The slideshow carries the narration, so it is queued
when the narration it needs is ready. Both are pipeline steps with an input hash, so a
resubmission re-runs only what changed: narration when the text it reads (or the source
choice) changed, the slideshow when the narration or the photos changed. A story is
published without waiting for either; the player shows what exists.

Narration timings come from the voice provider's alignment data when it offers them (the
whole text in one call). Otherwise each line is spoken on its own, measured, and joined.
Every spoken piece is cached as a file by a hash of its input, so nothing is paid for twice.
"""

import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audio, gateway, photos
from app.assets import asset_of
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import UserFacingError
from app.handlers import handler
from app.models import (
    Asset,
    AssetKind,
    Narration,
    NarrationSource,
    NarrationTiming,
    PipelineStep,
    ProviderCacheEntry,
    Story,
    VoiceClone,
)
from app.pipeline import (
    MEDIA_STEPS,
    POLISHED,
    PRODUCED_BY,
    STALE,
    TARGET_LAYER,
    get_layer,
    is_current,
    queue_step,
    step_hash,
)
from app.providers import TextToSpeech, text_to_speech
from app.storage import get_storage, partial_key

NARRATE, SLIDESHOW = MEDIA_STEPS
MP3, MP4 = "audio/mpeg", "video/mp4"

# The slideshow: 720p at 25 frames a second, each photo held for an equal share of the
# narration with a slow zoom or pan and a short fade. Bump RENDER_VERSION when the look
# changes, so existing slideshows are rendered again.
RENDER_VERSION = "1"
WIDTH, HEIGHT, FPS = 1280, 720, 25
FADE_SECONDS = 0.6
RENDER_TIMEOUT_SECONDS = 900


def source_layer(story: Story) -> str:
    """The text layer the narration reads. An MSA story's polished text is already MSA."""
    if story.narration_source == NarrationSource.MSA and story.original_language != "msa":
        return TARGET_LAYER["msa"]
    return POLISHED


def source_step(story: Story) -> str:
    """The step that makes the text the narration reads."""
    return PRODUCED_BY[source_layer(story)]


async def queue(session: AsyncSession, story: Story) -> None:
    """Queue narration, and the slideshow if its narration is ready, in the caller's
    transaction. A step whose input has not changed is left as it is."""
    await _queue_narration(session, story)
    await _queue_slideshow(session, story)


async def _queue_narration(session: AsyncSession, story: Story) -> None:
    layer = await get_layer(session, story.id, source_layer(story))
    if layer is None:
        return
    texts = [s["text"] for s in layer.segments]
    clone = None
    if story.narrator_voice_id:
        from app.providers.voices import unavailable_reason
        from app.voices import ready_voice  # voices imports this module

        # A cloned voice chosen by staff, while it is ready, not revoked, and usable by the
        # current narration provider (an ElevenLabs voice means nothing to Azure).
        if unavailable_reason() is None:
            clone = await ready_voice(session, story.narrator_voice_id)
    input_hash = step_hash(
        NARRATE,
        get_settings().tts_provider,
        story.narration_source,
        layer.language,
        json.dumps(texts, ensure_ascii=False),
        str(clone.id) if clone else "default",
    )
    await queue_step(
        session,
        story.id,
        step=NARRATE,
        kind=NARRATE,
        input_hash=input_hash,
        source=story.narration_source,
        language=layer.language,
        texts=texts,
        voice=clone.provider_voice_id if clone else None,
        voice_clone_id=str(clone.id) if clone else None,
    )


async def _queue_slideshow(session: AsyncSession, story: Story) -> None:
    """Queued only when the narration it carries is the current one; otherwise the narration
    queues it when it is done."""
    narration = await session.get(Narration, story.id)
    narrate = await session.get(PipelineStep, (story.id, NARRATE))
    if narration is None or narrate is None or narration.input_hash != narrate.input_hash:
        return
    images = await photos.slideshow_images(session, story)
    sound = await session.get(Asset, narration.asset_id)
    if not images or sound is None:
        return
    input_hash = step_hash(SLIDESHOW, RENDER_VERSION, narration.input_hash, json.dumps(images))
    await queue_step(
        session,
        story.id,
        step=SLIDESHOW,
        kind=SLIDESHOW,
        input_hash=input_hash,
        images=images,
    )


# --- shared ---


def _inputs(fmt: str, paths: list[Path]) -> list[str]:
    """FFmpeg input arguments: each input names its format and may only read local files."""
    return [
        arg for path in paths for arg in ("-protocol_whitelist", "file", "-f", fmt, "-i", str(path))
    ]


async def _ffmpeg(*args: str, timeout: int = RENDER_TIMEOUT_SECONDS) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-nostdin", "-v", "error", "-y", *args,
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


async def _render(key: str, *args: str) -> None:
    """Run FFmpeg into a partial file and move it to `key` only when it succeeded, so a
    half-written file is never served or left behind."""
    storage = get_storage()
    partial = partial_key(key)
    target = await asyncio.to_thread(storage.prepare, partial)
    try:
        await _ffmpeg(*args, str(target))
        await asyncio.to_thread(storage.move, partial, key)
    finally:
        await asyncio.to_thread(storage.delete, partial)


async def _save_asset(
    session: AsyncSession, story_id: uuid.UUID, kind: AssetKind, key: str, content_type: str
) -> Asset:
    asset = Asset(
        story_id=story_id,
        kind=kind.value,
        storage_key=key,
        content_type=content_type,
        size_bytes=get_storage().size(key),
    )
    session.add(asset)
    await session.flush()
    return asset


async def _drop_assets(
    session: AsyncSession, story_id: uuid.UUID, kind: AssetKind, keep: Asset
) -> list[str]:
    """Delete the story's other assets of this kind; returns their keys, to delete the files
    once the transaction has committed."""
    old = (
        await session.execute(
            select(Asset).where(Asset.story_id == story_id, Asset.kind == kind, Asset.id != keep.id)
        )
    ).scalars()
    keys = []
    for row in old:
        keys.append(row.storage_key)
        await session.delete(row)
    return keys


async def _discard(story_id: uuid.UUID, key: str) -> dict:
    """A result that is no longer wanted: its file goes, and so does the story's folder if the
    story was deleted while the job ran."""
    storage = get_storage()
    await asyncio.to_thread(storage.delete, key)
    async with get_sessionmaker()() as session:
        if await session.get(Story, story_id) is None:
            await asyncio.to_thread(storage.delete_tree, f"stories/{story_id}")
    return STALE


def _new_key(story_id: uuid.UUID, kind: str, extension: str) -> str:
    return f"stories/{story_id}/{kind}/{uuid.uuid4().hex}{extension}"


# --- narration ---


async def _speak(
    tts: TextToSpeech, texts: list[str], language: str, voice: str
) -> tuple[str, list | None]:
    """Speak through the gateway; returns the cached MP3's key and the provider's timings."""

    async def run() -> tuple[dict, bytes]:
        speech = await tts.speak(texts, language, voice)
        lines = [list(line) for line in speech.lines] if speech.lines else None
        # The voice is kept with the result, so revoking a cloned voice can find its speech.
        return {"lines": lines, "voice": voice}, speech.audio

    parts = (language, voice, json.dumps(texts, ensure_ascii=False))
    result, key = await gateway.call_file(
        "speak", tts, parts, sum(len(t) for t in texts), run, ".mp3"
    )
    return key, result["lines"]


@handler(NARRATE)
async def narrate(payload: dict) -> dict:
    story_id = uuid.UUID(payload["story_id"])
    clone_id = uuid.UUID(payload["voice_clone_id"]) if payload.get("voice_clone_id") else None
    async with get_sessionmaker()() as session:
        if not await is_current(session, payload):
            return STALE
        if clone_id is not None:
            clone = await session.get(VoiceClone, clone_id)
            if clone is None or clone.revoked_at is not None:
                return STALE  # never pay to speak in a revoked voice
    texts, language = payload["texts"], payload["language"]
    tts = text_to_speech()
    voice = payload.get("voice") or tts.voice_for(language)
    storage = get_storage()
    key = _new_key(story_id, "narration", ".mp3")

    if tts.aligns:
        spoken, lines = await _speak(tts, texts, language, voice)
        if lines is None or len(lines) != len(texts):
            raise UserFacingError("The voice service returned timings that do not match the text.")
        # A copy, so deleting the story never removes a cached result.
        await asyncio.to_thread(storage.copy, spoken, key)
        timing = NarrationTiming.ALIGNMENT
    else:
        pieces, lines, at = [], [], 0
        for text in texts:
            piece_key, _ = await _speak(tts, [text], language, voice)
            piece = storage.path(piece_key)
            length = await audio.duration_ms(piece)
            pieces.append(piece)
            lines.append((at, at + length))
            at += length
        labels = "".join(f"[{i}:a]" for i in range(len(pieces)))
        await _render(
            key, *_inputs("mp3", pieces),
            "-filter_complex", f"{labels}concat=n={len(pieces)}:v=0:a=1[a]", "-map", "[a]",
            "-ac", "1", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "96k", "-f", "mp3",
        )  # fmt: skip
        timing = NarrationTiming.PER_SEGMENT

    segments = [
        {"start_ms": int(start), "end_ms": int(end), "text": text}
        for (start, end), text in zip(lines, texts, strict=True)
    ]
    async with get_sessionmaker()() as session:
        if not await is_current(session, payload, lock=True):
            return await _discard(story_id, key)
        if clone_id is not None:
            clone = await session.get(VoiceClone, clone_id, with_for_update=True)
            if clone is None or clone.revoked_at is not None:
                # Revoked while this ran: the speech just cached in that voice goes too.
                purged = await purge_speech(session, voice)
                await session.commit()
                await asyncio.to_thread(storage.delete, *purged)
                return await _discard(story_id, key)
        story = await session.get(Story, story_id)
        asset = await _save_asset(session, story_id, AssetKind.NARRATION, key, MP3)
        row = await session.get(Narration, story_id)
        if row is None:
            row = Narration(story_id=story_id)
            session.add(row)
        row.asset_id, row.provider, row.voice = asset.id, tts.name, voice
        row.language, row.source, row.timing = language, payload["source"], timing.value
        row.segments, row.input_hash = segments, payload["input_hash"]
        row.voice_clone_id = clone_id
        # Point the narration at the new file before the old files go (they cascade to it).
        await session.flush()
        old_keys = await _drop_assets(session, story_id, AssetKind.NARRATION, keep=asset)
        # The slideshow carries this narration, so it follows.
        await _queue_slideshow(session, story)
        await session.commit()
    await asyncio.to_thread(storage.delete, *old_keys)
    return {"segments": len(segments), "timing": timing.value}


# --- slideshow ---

# Zoom in, zoom out, pan right, pan left; z is the zoom, x and y the visible window's corner.
_MOTIONS = (
    ("1+0.15*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("1.15-0.15*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    ("1.12", "(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),
    ("1.12", "(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)"),
)


def slideshow_filters(count: int, seconds: float) -> str:
    """The FFmpeg filter graph for `count` photos sharing `seconds`."""
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
    return ";".join(chains)


@handler(SLIDESHOW)
async def slideshow(payload: dict) -> dict:
    story_id = uuid.UUID(payload["story_id"])
    async with get_sessionmaker()() as session:
        if not await is_current(session, payload):
            return STALE
        # The narration's file is looked up now, not taken from the payload: a job that is
        # run again for the same input (A -> B -> A) keeps its first payload, but each
        # narration is stored under a new name. The step's input hash already guarantees
        # it is the same narration.
        narration = await session.get(Narration, story_id)
        sound_asset = await session.get(Asset, narration.asset_id) if narration else None
        if narration is None or sound_asset is None:
            return STALE  # the narration is being made again; it queues the slideshow
        sound_key = sound_asset.storage_key
        narration_ms = narration.segments[-1]["end_ms"] if narration.segments else 0
    storage = get_storage()
    # A missing file fails the step rather than quietly making a different slideshow.
    if not all(storage.exists(k) for k in [*payload["images"], sound_key]):
        raise UserFacingError("A photo or the narration for the slideshow is missing.")
    images = [storage.path(k) for k in payload["images"]]
    sound = storage.path(sound_key)
    seconds = (narration_ms or await audio.duration_ms(sound)) / 1000
    key = _new_key(story_id, "slideshow", ".mp4")
    await _render(
        key, *_inputs("webp_pipe", images), *_inputs("mp3", [sound]),
        "-filter_complex", slideshow_filters(len(images), seconds),
        "-map", "[v]", "-map", f"{len(images)}:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", "-f", "mp4",
    )  # fmt: skip

    async with get_sessionmaker()() as session:
        if not await is_current(session, payload, lock=True):
            return await _discard(story_id, key)
        asset = await _save_asset(session, story_id, AssetKind.SLIDESHOW, key, MP4)
        old_keys = await _drop_assets(session, story_id, AssetKind.SLIDESHOW, keep=asset)
        await session.commit()
    await asyncio.to_thread(storage.delete, *old_keys)
    return {"photos": len(images), "seconds": round(seconds, 1)}


async def purge_speech(session: AsyncSession, voice: str) -> list[str]:
    """Remove every cached piece of speech in a voice (a revoked clone). Returns the file keys
    to delete once the transaction has committed."""
    keys = []
    cached = (
        await session.execute(
            select(ProviderCacheEntry).where(
                ProviderCacheEntry.operation == "speak",
                ProviderCacheEntry.result["voice"].astext == voice,
            )
        )
    ).scalars()
    for entry in cached:
        if entry.file_key:
            keys.append(entry.file_key)
        await session.delete(entry)
    return keys


async def narration_for(
    session: AsyncSession, story_id: uuid.UUID
) -> tuple[Narration, Asset] | None:
    row = await session.get(Narration, story_id)
    if row is None:
        return None
    asset = await session.get(Asset, row.asset_id)
    return (row, asset) if asset is not None else None


async def slideshow_of(session: AsyncSession, story_id: uuid.UUID) -> Asset | None:
    return await asset_of(session, story_id, AssetKind.SLIDESHOW)
