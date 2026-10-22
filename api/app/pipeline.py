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

from app import gateway, jobs
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import INTERNAL_PREFIX, UserFacingError
from app.handlers import handler
from app.models import Asset, AssetKind, Job, JobStatus, PipelineStep, Story, TextLayer
from app.providers import Segment, Transcript, language_model, speech_to_text
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
STEPS = ("transcribe", "polish", "translate_en", "translate_msa", "moderate")
# Which step writes each layer.
PRODUCED_BY = {
    VERBATIM: "transcribe",
    POLISHED: "polish",
    "translation_en": "translate_en",
    "translation_msa": "translate_msa",
}
WAITING = "waiting"  # a step that has not been queued yet

MAX_SEGMENT_CHARS = 2000
GENERIC_FAILURE = "Something went wrong in this step. Try again."


class Misaligned(UserFacingError):
    def __init__(self) -> None:
        super().__init__(
            "The language model returned a different number of lines than the transcript."
        )


def expected_steps(language: str | None) -> list[str]:
    targets = TARGETS.get(language or "", ())
    return ["transcribe", "polish", *(TARGET_STEP[t] for t in targets)]


def step_hash(*parts: str) -> str:
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


async def get_layer(session: AsyncSession, story_id: uuid.UUID, kind: str) -> TextLayer | None:
    return (
        await session.execute(
            select(TextLayer).where(TextLayer.story_id == story_id, TextLayer.kind == kind)
        )
    ).scalar_one_or_none()


async def _save_layer(
    session: AsyncSession, story_id: uuid.UUID, kind: str, language: str, segments: list[dict]
) -> None:
    layer = await get_layer(session, story_id, kind)
    if layer is None:
        session.add(TextLayer(story_id=story_id, kind=kind, language=language, segments=segments))
    else:
        layer.language, layer.segments, layer.edited = language, segments, False


async def queue_step(
    session: AsyncSession,
    story_id: uuid.UUID,
    step: str,
    kind: str,
    input_hash: str,
    *,
    always: bool = False,
    **extra,
) -> None:
    """Point `step` at a job for this input (creating it once), in the caller's transaction.
    With `always`, a finished job for the same input runs again (a resubmitted story)."""
    row = await session.get(PipelineStep, (story_id, step))
    if not always and row is not None and row.input_hash == input_hash and row.job_id is not None:
        return
    job = await jobs.enqueue(
        session,
        kind,
        {"story_id": str(story_id), "step": step, "input_hash": input_hash, **extra},
        idempotency_key=f"{step}:{story_id}:{input_hash}",
        commit=False,
    )
    # The same input came back (A -> B -> A, or a new upload of the same recording): its
    # earlier result was replaced since, so the same job runs again.
    if job.status in (JobStatus.DONE, JobStatus.FAILED):
        await jobs.restart(session, job.id)
    if row is None:
        session.add(
            PipelineStep(story_id=story_id, step=step, input_hash=input_hash, job_id=job.id)
        )
    else:
        row.input_hash, row.job_id = input_hash, job.id


async def is_current(session: AsyncSession, payload: dict, *, lock: bool = False) -> bool:
    """Is this job's input still the step's input? With lock, holds the step row until commit,
    so the input cannot change between this check and saving the result."""
    row = await session.get(
        PipelineStep,
        (uuid.UUID(payload["story_id"]), payload["step"]),
        with_for_update=lock,
        populate_existing=True,
    )
    return row is not None and row.input_hash == payload["input_hash"]


STALE = {"stale": True}


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
    return step_hash("transcribe", get_settings().stt_provider, audio_digest, language or "auto")


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
    await queue_step(session, story.id, "transcribe", "transcribe", input_hash, digest=digest)
    await session.commit()


async def _queue_polish(session: AsyncSession, story: Story) -> None:
    verbatim = await get_layer(session, story.id, VERBATIM)
    input_hash = step_hash(
        "polish", get_settings().llm_provider, verbatim.language, json.dumps(_texts(verbatim))
    )
    await queue_step(session, story.id, "polish", "polish", input_hash)


async def _queue_translations(session: AsyncSession, story: Story) -> None:
    polished = await get_layer(session, story.id, POLISHED)
    for target in TARGETS[polished.language]:
        input_hash = step_hash(
            "translate",
            get_settings().llm_provider,
            polished.language,
            target,
            json.dumps(_texts(polished)),
        )
        await queue_step(
            session, story.id, TARGET_STEP[target], "translate", input_hash, target=target
        )


# --- job handlers ---


async def _llm(operation: str, language: str, texts: list[str], target: str | None = None):
    """Polish or translate through the gateway (cache, live switch, spending ledger)."""
    llm = language_model()

    async def run() -> dict:
        if operation == "polish":
            return {"texts": await llm.polish(texts, language)}
        return {"texts": await llm.translate(texts, language, target)}

    parts = (language, target or "", json.dumps(texts, ensure_ascii=False))
    result = await gateway.call(operation, llm, parts, sum(len(t) for t in texts), run)
    return result["texts"]


@handler("transcribe")
async def transcribe(payload: dict) -> dict:
    async with get_sessionmaker()() as session:
        story = await session.get(Story, uuid.UUID(payload["story_id"]))
        if story is None or not await is_current(session, payload):
            return STALE
        asset = (
            await session.execute(
                select(Asset).where(Asset.story_id == story.id, Asset.kind == AssetKind.AUDIO)
            )
        ).scalar_one()
        stt = speech_to_text()
        path = get_storage().path(asset.storage_key)
        language, duration = story.original_language, story.duration_ms or 0

        async def run() -> dict:
            t = await stt.transcribe(path, language, duration)
            return {"language": t.language, "segments": [_segment(x) for x in t.segments]}

        raw = await gateway.call(
            "transcribe", stt, (payload["digest"], language or "auto", str(duration)), duration, run
        )
        result = Transcript(
            language=raw["language"], segments=[Segment(**x) for x in raw["segments"]]
        )
        if not await is_current(session, payload, lock=True):
            return STALE
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
        if story is None or not await is_current(session, payload):
            return STALE
        verbatim = await get_layer(session, story.id, VERBATIM)
        texts = await _llm("polish", verbatim.language, _texts(verbatim))
        if not await is_current(session, payload, lock=True):
            return STALE
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
        if story is None or not await is_current(session, payload):
            return STALE
        target = payload["target"]
        polished = await get_layer(session, story.id, POLISHED)
        texts = await _llm("translate", polished.language, _texts(polished), target)
        if not await is_current(session, payload, lock=True):
            return STALE
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


def _status_and_message(job: Job | None) -> tuple[str, str]:
    if job is None:
        return WAITING, "Waits for the step above."
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
    out = [
        await _step_status(session, step, rows.get(step))
        for step in expected_steps(story.original_language)
    ]
    complete = all(s.status == JobStatus.DONE for s in out)
    # The moderation check appears once the story has been submitted; "complete" is about
    # the text being ready, so it does not count here.
    if "moderate" in rows:
        out.append(await _step_status(session, "moderate", rows["moderate"]))
    return out, complete


async def _step_status(session: AsyncSession, step: str, row: PipelineStep | None) -> StepStatus:
    job = await session.get(Job, row.job_id) if row and row.job_id else None
    return StepStatus(step, *_status_and_message(job))


async def step_done(session: AsyncSession, story_id: uuid.UUID, step: str) -> bool:
    """Has the step's current job finished? False while a newer input is still being worked on."""
    row = await session.get(PipelineStep, (story_id, step))
    job = await session.get(Job, row.job_id) if row and row.job_id else None
    return job is not None and job.status == JobStatus.DONE


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


class LayerBusy(Exception):
    """The step that makes this layer is queued or running; an edit would be overwritten."""


async def edit_layer(session: AsyncSession, story: Story, kind: str, texts: list[str]) -> None:
    """Save edited text (timestamps unchanged) and re-run only what depends on it. Commits."""
    layer = await get_layer(session, story.id, kind)
    if layer is None:
        raise LayerNotReady
    row = await session.get(PipelineStep, (story.id, PRODUCED_BY[kind]))
    job = await session.get(Job, row.job_id) if row and row.job_id else None
    if job is not None and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise LayerBusy
    layer.segments = _aligned(layer.segments, texts)
    layer.edited = True
    await session.flush()
    if kind == VERBATIM:
        await _queue_polish(session, story)
    elif kind == POLISHED:
        await _queue_translations(session, story)
    await session.commit()
