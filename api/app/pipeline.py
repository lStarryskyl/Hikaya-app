"""The story pipeline: transcribe → polish → translate, as jobs in the Postgres queue.

Every step records the hash of the input it was made from. A job carries that hash too, so
when the input changes (a new recording, an edited transcript) the old job's result is
dropped instead of overwriting newer text, and the idempotency key `step:story:hash` means
the same input is never processed twice.

Text layers are lists of segments that share the verbatim timestamps, so the player can
highlight the line being spoken in any language.
"""

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import jobs
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import UserFacingError
from app.handlers import handler
from app.models import Asset, AssetKind, Job, JobStatus, PipelineStep, Story, TextLayer
from app.providers import Segment, language_model, speech_to_text
from app.storage import get_storage

VERBATIM, POLISHED = "verbatim", "polished"
LAYER_KINDS = (VERBATIM, POLISHED, "translation_en", "translation_msa")

# Translation targets are never the original language and never dialect.
TARGETS: dict[str, tuple[str, ...]] = {
    "jordanian": ("english", "msa"),
    "msa": ("english",),
    "english": ("msa",),
}
TARGET_LAYER = {"english": "translation_en", "msa": "translation_msa"}
TARGET_STEP = {"english": "translate_en", "msa": "translate_msa"}
STEPS = ("transcribe", "polish", "translate_en", "translate_msa")

MAX_SEGMENT_CHARS = 2000
INTERNAL_PREFIX = "internal: "
GENERIC_FAILURE = "Something went wrong in this step. Try again."


class Misaligned(UserFacingError):
    def __init__(self) -> None:
        super().__init__(
            "The language model returned a different number of lines than the transcript."
        )


def expected_steps(language: str | None) -> list[str]:
    targets = TARGETS.get(language or "", ())
    return ["transcribe", "polish", *(TARGET_STEP[t] for t in targets)]


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _texts(layer: TextLayer) -> list[str]:
    return [s["text"] for s in layer.segments]


def _aligned(timing: list[dict], texts: list[str]) -> list[dict]:
    """New segments with `timing`'s timestamps and `texts`, one to one."""
    if len(texts) != len(timing):
        raise Misaligned
    return [
        {"start_ms": t["start_ms"], "end_ms": t["end_ms"], "text": text.strip()}
        for t, text in zip(timing, texts, strict=True)
    ]


async def _layer(session: AsyncSession, story_id: uuid.UUID, kind: str) -> TextLayer | None:
    return (
        await session.execute(
            select(TextLayer).where(TextLayer.story_id == story_id, TextLayer.kind == kind)
        )
    ).scalar_one_or_none()


async def _save_layer(
    session: AsyncSession, story_id: uuid.UUID, kind: str, language: str, segments: list[dict]
) -> None:
    layer = await _layer(session, story_id, kind)
    if layer is None:
        session.add(TextLayer(story_id=story_id, kind=kind, language=language, segments=segments))
    else:
        layer.language, layer.segments, layer.edited = language, segments, False


async def _queue(
    session: AsyncSession, story_id: uuid.UUID, step: str, kind: str, input_hash: str, **extra
) -> None:
    """Point `step` at a job for this input (creating it once), in the caller's transaction."""
    row = await session.get(PipelineStep, (story_id, step))
    if row is not None and row.input_hash == input_hash and row.job_id is not None:
        return
    job = await jobs.enqueue(
        session,
        kind,
        {"story_id": str(story_id), "step": step, "input_hash": input_hash, **extra},
        idempotency_key=f"{step}:{story_id}:{input_hash}",
        commit=False,
    )
    if row is None:
        session.add(
            PipelineStep(story_id=story_id, step=step, input_hash=input_hash, job_id=job.id)
        )
    else:
        row.input_hash, row.job_id = input_hash, job.id


async def _is_current(session: AsyncSession, payload: dict) -> bool:
    row = await session.get(PipelineStep, (uuid.UUID(payload["story_id"]), payload["step"]))
    return row is not None and row.input_hash == payload["input_hash"]


# --- starting and re-running ---


async def _audio_digest(story_id: uuid.UUID, session: AsyncSession) -> str | None:
    asset = (
        await session.execute(
            select(Asset).where(Asset.story_id == story_id, Asset.kind == AssetKind.AUDIO)
        )
    ).scalar_one_or_none()
    if asset is None:
        return None
    path = get_storage().path(asset.storage_key)
    return await asyncio.to_thread(lambda: hashlib.sha256(path.read_bytes()).hexdigest())


def _transcribe_hash(audio_digest: str, language: str | None) -> str:
    return _hash("transcribe", get_settings().stt_provider, audio_digest, language or "auto")


async def start(session: AsyncSession, story: Story) -> None:
    """(Re)start from transcription if the recording or the language changed. Commits."""
    digest = await _audio_digest(story.id, session)
    if digest is None:
        return
    input_hash = _transcribe_hash(digest, story.original_language)
    row = await session.get(PipelineStep, (story.id, "transcribe"))
    if row is not None and row.input_hash == input_hash:
        return
    # Old text must never show against a new recording or language.
    await session.execute(delete(TextLayer).where(TextLayer.story_id == story.id))
    await session.execute(delete(PipelineStep).where(PipelineStep.story_id == story.id))
    await _queue(session, story.id, "transcribe", "transcribe", input_hash, digest=digest)
    await session.commit()


async def _queue_polish(session: AsyncSession, story: Story) -> None:
    verbatim = await _layer(session, story.id, VERBATIM)
    input_hash = _hash(
        "polish", get_settings().llm_provider, verbatim.language, json.dumps(_texts(verbatim))
    )
    await _queue(session, story.id, "polish", "polish", input_hash)


async def _queue_translations(session: AsyncSession, story: Story) -> None:
    polished = await _layer(session, story.id, POLISHED)
    for target in TARGETS[polished.language]:
        input_hash = _hash(
            "translate",
            get_settings().llm_provider,
            polished.language,
            target,
            json.dumps(_texts(polished)),
        )
        await _queue(session, story.id, TARGET_STEP[target], "translate", input_hash, target=target)


# --- job handlers ---


@handler("transcribe")
async def transcribe(payload: dict) -> dict:
    async with get_sessionmaker()() as session:
        story = await session.get(Story, uuid.UUID(payload["story_id"]))
        if story is None or not await _is_current(session, payload):
            return {"stale": True}
        asset = (
            await session.execute(
                select(Asset).where(Asset.story_id == story.id, Asset.kind == AssetKind.AUDIO)
            )
        ).scalar_one()
        result = await speech_to_text().transcribe(
            get_storage().path(asset.storage_key), story.original_language, story.duration_ms or 0
        )
        if not result.segments:
            raise UserFacingError("No speech was found in the recording.")
        if story.original_language is None:
            # Detected language: record it, and keep the step current under the new language.
            story.original_language = result.language
            row = await session.get(PipelineStep, (story.id, "transcribe"))
            row.input_hash = _transcribe_hash(payload["digest"], result.language)
        await _save_layer(
            session, story.id, VERBATIM, result.language, [_segment(s) for s in result.segments]
        )
        await session.flush()
        await _queue_polish(session, story)
        await session.commit()
        return {"segments": len(result.segments), "language": result.language}


def _segment(s: Segment) -> dict:
    return {"start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.text.strip()}


@handler("polish")
async def polish(payload: dict) -> dict:
    async with get_sessionmaker()() as session:
        story = await session.get(Story, uuid.UUID(payload["story_id"]))
        if story is None or not await _is_current(session, payload):
            return {"stale": True}
        verbatim = await _layer(session, story.id, VERBATIM)
        texts = await language_model().polish(_texts(verbatim), verbatim.language)
        await _save_layer(
            session, story.id, POLISHED, verbatim.language, _aligned(verbatim.segments, texts)
        )
        await session.flush()
        await _queue_translations(session, story)
        await session.commit()
        return {"segments": len(texts)}


@handler("translate")
async def translate(payload: dict) -> dict:
    async with get_sessionmaker()() as session:
        story = await session.get(Story, uuid.UUID(payload["story_id"]))
        if story is None or not await _is_current(session, payload):
            return {"stale": True}
        target = payload["target"]
        polished = await _layer(session, story.id, POLISHED)
        texts = await language_model().translate(_texts(polished), polished.language, target)
        await _save_layer(
            session, story.id, TARGET_LAYER[target], target, _aligned(polished.segments, texts)
        )
        await session.commit()
        return {"segments": len(texts), "target": target}


# --- what the API needs ---


@dataclass
class StepStatus:
    step: str
    status: str  # queued | running | done | failed
    message: str


def _message(job: Job | None) -> tuple[str, str]:
    if job is None:
        return JobStatus.QUEUED, "Waits for the previous step."
    error = job.error or ""
    shown = GENERIC_FAILURE if error.startswith(INTERNAL_PREFIX) else error
    if job.status == JobStatus.FAILED:
        return JobStatus.FAILED, shown or GENERIC_FAILURE
    if job.status == JobStatus.RUNNING:
        return JobStatus.RUNNING, "Working on it."
    if job.status == JobStatus.DONE:
        return JobStatus.DONE, "Done."
    return JobStatus.QUEUED, f"Retrying after a problem: {shown}" if error else "Waiting to start."


async def status(session: AsyncSession, story: Story) -> tuple[list[StepStatus], bool]:
    rows = {
        r.step: r
        for r in (
            await session.execute(select(PipelineStep).where(PipelineStep.story_id == story.id))
        ).scalars()
    }
    if "transcribe" not in rows:
        return [], False
    out = []
    for step in expected_steps(story.original_language):
        row = rows.get(step)
        job = await session.get(Job, row.job_id) if row and row.job_id else None
        state, message = _message(job if row else None)
        out.append(StepStatus(step, state, message))
    return out, all(s.status == JobStatus.DONE for s in out)


async def retry(session: AsyncSession, story: Story, step: str) -> bool:
    row = await session.get(PipelineStep, (story.id, step))
    if row is None or row.job_id is None:
        return False
    return await jobs.requeue(session, row.job_id)


async def layers(session: AsyncSession, story_id: uuid.UUID) -> list[TextLayer]:
    found = {
        layer.kind: layer
        for layer in (
            await session.execute(select(TextLayer).where(TextLayer.story_id == story_id))
        ).scalars()
    }
    return [found[k] for k in LAYER_KINDS if k in found]


class LayerNotReady(Exception):
    pass


async def edit_layer(session: AsyncSession, story: Story, kind: str, texts: list[str]) -> None:
    """Save edited text (timestamps unchanged) and re-run only what depends on it. Commits."""
    layer = await _layer(session, story.id, kind)
    if layer is None:
        raise LayerNotReady
    layer.segments = _aligned(layer.segments, texts)
    layer.edited = True
    await session.flush()
    if kind == VERBATIM:
        await _queue_polish(session, story)
    elif kind == POLISHED:
        await _queue_translations(session, story)
    await session.commit()
