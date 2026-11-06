"""Narrated AI videos (docs/DECISIONS.md, "Narrated AI videos").

The story's soundtrack (its narration, or the storyteller's recording) is the script: its
timed lines are cut into shots at line boundaries, the first shot is made from the story
photo and each later one from the frame where the previous shot is cut (with a reference frame
of the people from the first shot), and FFmpeg joins the shots, lays the soundtrack over them
(the provider's own sound kept low and ducked under the voice) and burns in subtitles.

Planning happens in the web request and calls no provider. Everything else runs in worker
jobs, one step per job (submit a shot, check it once, or join them), so the worker is never
held while a shot renders.
"""

import asyncio
import base64
import math
import re
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select

from app import gateway, jobs
from app.assets import asset_of
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import NotStarted, UserFacingError
from app.handlers import handler
from app.media import ffmpeg_inputs, narration_for, render
from app.models import AssetKind, Job, JobStatus, Story, VideoGeneration
from app.pipeline import get_layer
from app.providers.video import FreeVideoRead, VideoRejected, clip_extension, provider
from app.storage import get_storage

KIND = "narrated_video"
LEAD_MS = 300  # picture before the first word
TAIL_MS = 600  # the last frame held after the last word (not asked of the provider)
VOICE_FADE_MS = 120  # the voice fades out at the end of the last line the video covers
REFERENCE_AT = 0.4  # where in the first shot the reference frame of the people is taken
RLE, PDF = "‫", "‬"  # right-to-left embedding around Arabic subtitle lines
SIZES = {"16:9": (1280, 720), "9:16": (720, 1280)}
DEMUXERS = {".webm": "matroska", ".mp4": "mov"}
# Storage paths go into an FFmpeg filter argument unquoted, so only plain characters pass.
SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")

# Progress is one of these fixed messages (the console translates them); the shot number is
# reported beside it.
SUBMITTING = "Submitting a shot"
RENDERING = "Rendering a shot"
SHOT_READY = "Shot ready"
JOINING = "Joining the shots"
RETRYING = "Retrying"
REMOVED = "Removed: the narrator's voice was revoked"
READY = "Video ready"


@dataclass(frozen=True)
class Line:
    start_ms: int
    end_ms: int
    spoken: str
    english: str | None  # the English translation, when the spoken text is not English


@dataclass(frozen=True)
class Shot:
    start_ms: int  # in video time: the soundtrack starts LEAD_MS in
    end_ms: int
    seconds: int  # the length asked of the provider; the clip is cut to end_ms - start_ms
    lines: tuple[int, ...]  # the lines spoken during the shot


# --- planning (pure) ---


def plan_shots(
    lines: list[Line], max_shot_seconds: int, max_total_seconds: int, min_shot_seconds: int = 3
) -> tuple[list[Line], list[Shot]]:
    """The whole lines that fit in `max_total_seconds` (lead-in and tail included), and shots
    covering them, cut where a line starts and never longer than `max_shot_seconds`. A line
    longer than a shot is split evenly. The first shot starts at 0 (the lead-in); the last
    ends with the last word, since the tail is the held last frame."""
    if not lines:
        raise UserFacingError("The soundtrack has no timed lines to follow.")
    cap = max_total_seconds * 1000
    kept: list[Line] = []
    for line in lines:
        if line.end_ms + LEAD_MS + TAIL_MS > cap:
            break
        kept.append(line)
    if not kept:
        raise UserFacingError(
            f"The soundtrack's first line is longer than a narrated video can be "
            f"({max_total_seconds} s)."
        )
    longest = max_shot_seconds * 1000
    cuts = [line.start_ms + LEAD_MS for line in kept[1:]] + [kept[-1].end_ms + LEAD_MS]
    spans: list[tuple[int, int]] = []
    start, reach, i = 0, None, 0
    while i < len(cuts):
        cut = cuts[i]
        if cut - start <= longest:
            reach, i = cut, i + 1
        elif reach is not None and reach > start:
            spans.append((start, reach))
            start, reach = reach, None
        else:
            parts = math.ceil((cut - start) / longest)
            edges = [start + (cut - start) * p // parts for p in range(parts + 1)]
            spans += list(zip(edges, edges[1:], strict=False))
            start, reach, i = cut, None, i + 1
    if reach is not None and reach > start:
        spans.append((start, reach))
    shots = [
        Shot(
            a,
            b,
            max(min_shot_seconds, math.ceil((b - a) / 1000)),
            tuple(
                n
                for n, line in enumerate(kept)
                if line.start_ms + LEAD_MS < b and line.end_ms + LEAD_MS > a
            ),
        )
        for a, b in spans
    ]
    return kept, shots


def shot_prompt(index: int, count: int, title: str, place: str, words: str, direction: str) -> str:
    """One shot's prompt: what is said during it, and how it continues the film. A later shot
    gets two images, and Omni has no field for image roles, so the prompt names them."""
    continuity = (
        "Start from the provided photo."
        if index == 0
        else "Two images are given. The first image is the last frame of the previous shot: "
        "start exactly from it, so the cut is seamless. The second image shows how the people "
        "in this film look: keep their faces, hair and clothes exactly the same."
    )
    return "\n".join(
        [
            f"Shot {index + 1} of {count} of one continuous short film for the heritage story "
            f'"{title}" from {place or "Jordan"}.',
            continuity,
            f'The narrator is saying: "{words}" Show what these words describe.',
            f"Visual direction: {direction}",
            "No one speaks or moves their lips on camera; no text, captions or logos on screen.",
        ]
    )


def _shot_words(lines: list[Line], shot: Shot) -> str:
    words = " ".join((lines[i].english or lines[i].spoken).strip() for i in shot.lines)
    return words.strip() or "A quiet pause in the story."


def _clean(text: str) -> str:
    """Subtitle text with no way to carry formatting codes or line breaks of its own."""
    return " ".join(text.replace("\\", "/").replace("{", "(").replace("}", ")").split())


def _time(ms: int) -> str:
    cs = round(ms / 10)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def subtitles(lines: list[Line], width: int, height: int, rtl: bool) -> str:
    """ASS subtitles timed to the soundtrack: the spoken line, and its English translation
    under it when the story is not in English."""
    base = round(min(width, height) * 33 / 720)
    small = round(base * 31 / 33)
    margin = round(height * 0.055)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, \
Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, \
Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,{base},&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,0,0,0,0,100,\
100,0,0,1,2.4,0.8,2,{round(width * 0.07)},{round(width * 0.07)},{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for line in lines:
        spoken = _clean(line.spoken)
        if not spoken:
            continue
        if rtl:
            # The subtitle renderer lays lines out left to right; the embedding keeps Arabic
            # word order and its closing full stop right, even with Latin words inside.
            spoken = RLE + spoken + PDF
        english = _clean(line.english or "")
        text = (
            f"{{\\fs{small}\\c&HE6F2FF&}}{spoken}\\N{{\\fs{base}\\c&HFFFFFF&}}{english}"
            if english
            else spoken
        )
        start, end = _time(line.start_ms + LEAD_MS), _time(line.end_ms + LEAD_MS)
        events.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}")
    return header + "\n".join(events) + "\n"


# --- a story's plan (web request: database only, no provider call) ---


@dataclass
class StoryPlan:
    soundtrack_key: str
    lines: list[Line]  # the lines the video covers
    lines_total: int
    shots: list[Shot]
    rtl: bool
    english: bool  # every line has an English translation (prompts and second subtitle line)
    voice_clone_id: uuid.UUID | None  # the cloned voice that read the narration, if any
    estimate: Decimal

    @property
    def seconds(self) -> float:
        return (self.shots[-1].end_ms + TAIL_MS) / 1000

    def summary(self) -> dict:
        return {
            "shots": [
                {
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "seconds": s.seconds,
                    "lines": len(s.lines),
                }
                for s in self.shots
            ],
            "seconds": self.seconds,
            "estimate_usd": str(self.estimate.quantize(Decimal("0.01"))),
            "lines": len(self.lines),
            "lines_total": self.lines_total,
            "english": self.english,
        }


async def _soundtrack(
    session, story: Story, kind: str
) -> tuple[str, list[Line], bool, bool, uuid.UUID | None]:
    """The soundtrack's file, its timed lines, whether they are right-to-left, whether every
    line has an English translation, and the cloned voice that read it (if any)."""
    clone_id = None
    if kind == "narration":
        found = await narration_for(session, story.id)
        if found is None:
            raise UserFacingError(
                "This story has no narration yet; it is made when the story is submitted."
            )
        row, asset = found
        segments, language, key = row.segments, row.language, asset.storage_key
        clone_id = row.voice_clone_id
    else:
        asset = await asset_of(session, story.id, AssetKind.AUDIO)
        # The polished text of each spoken line, at the transcript's timings.
        layer = await get_layer(session, story.id, "polished") or await get_layer(
            session, story.id, "verbatim"
        )
        if asset is None or layer is None or not layer.segments:
            raise UserFacingError("This story has no recording with a transcript.")
        segments, language, key = layer.segments, layer.language, asset.storage_key
    english = None
    if language != "english":
        layer = await get_layer(session, story.id, "translation_en")
        if layer is not None and len(layer.segments) == len(segments):
            english = [str(s.get("text", "")) for s in layer.segments]
    lines = [
        Line(
            int(s["start_ms"]),
            int(s["end_ms"]),
            str(s.get("text", "")),
            english[i] if english else None,
        )
        for i, s in enumerate(segments)
    ]
    rtl = language != "english"
    return key, lines, rtl, english is not None or not rtl, clone_id


async def plan_story(session, story: Story, provider_name: str, soundtrack: str) -> StoryPlan:
    adapter = provider(provider_name)
    shortest, longest = adapter.shot_seconds
    key, lines, rtl, english, clone_id = await _soundtrack(session, story, soundtrack)
    kept, shots = plan_shots(
        lines, longest, get_settings().narrated_video_max_seconds, min_shot_seconds=shortest
    )
    estimate = sum(
        (adapter.estimate_usd("video_submit", shot.seconds) for shot in shots), Decimal(0)
    )
    return StoryPlan(key, kept, len(lines), shots, rtl, english, clone_id, estimate)


# --- the stored state of each shot ---


@dataclass
class ShotState:
    start_ms: int
    end_ms: int
    seconds: int
    lines: list[int]
    prompt: str
    attempt: int = 1
    submitted: bool = False
    request: dict | None = None
    failed: bool = False  # the provider reported the job failed, cancelled or filtered
    file_key: str | None = None
    frame_key: str | None = None  # where the next shot starts
    reference_key: str | None = None  # first shot only: how the people look

    @property
    def uncertain(self) -> bool:
        """Submitted, but the provider's answer never arrived: it may be rendering (and billed)."""
        return self.submitted and not self.request

    @property
    def span(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    def cache_parts(self, input_hash: str, index: int) -> tuple[str, ...]:
        return (input_hash, f"shot-{index}", f"try-{self.attempt}")


def _states(generation: VideoGeneration) -> list[ShotState]:
    return [ShotState(**shot) for shot in generation.shots]


def _store(generation: VideoGeneration, states: list[ShotState]) -> None:
    generation.shots = [asdict(state) for state in states]


def new_shots(plan: StoryPlan, title: str, place: str, direction: str) -> list[dict]:
    """The stored shots of a new narrated video."""
    count = len(plan.shots)
    return [
        asdict(
            ShotState(
                shot.start_ms,
                shot.end_ms,
                shot.seconds,
                list(shot.lines),
                shot_prompt(index, count, title, place, _shot_words(plan.lines, shot), direction),
            )
        )
        for index, shot in enumerate(plan.shots)
    ]


def payload_lines(plan: StoryPlan) -> list[dict]:
    return [asdict(line) for line in plan.lines]


def deadline_for(shots: int) -> datetime:
    """Each shot gets the full wait a single video gets."""
    return datetime.now(UTC) + timedelta(seconds=get_settings().video_max_wait_seconds * shots)


def _current(states: list[ShotState]) -> int | None:
    return next((i for i, state in enumerate(states) if not state.file_key), None)


def _stopped(generation: VideoGeneration, job: Job | None) -> list[ShotState] | None:
    """The shots of a narrated video that failed and can be looked at again, else None."""
    if (
        not generation.shots
        or generation.file_key
        or generation.payload.get("removed")
        or job is None
        or job.status != JobStatus.FAILED
    ):
        return None
    return _states(generation)


def current_shot(generation: VideoGeneration) -> int | None:
    """The shot being worked on (1-based), while a narrated video is not finished."""
    if not generation.shots or generation.file_key or generation.payload.get("removed"):
        return None
    index = _current(_states(generation))
    return index + 1 if index is not None else None


def retryable(generation: VideoGeneration, job: Job | None) -> bool:
    """A failed narrated video can go on from where it stopped, unless a shot's submission is
    uncertain (it may have been accepted and billed: staff must confirm before resubmitting)."""
    states = _stopped(generation, job)
    if states is None:
        return False
    index = _current(states)
    return index is None or not states[index].uncertain


def needs_confirmation(generation: VideoGeneration, job: Job | None) -> bool:
    states = _stopped(generation, job)
    if states is None:
        return False
    index = _current(states)
    return index is not None and states[index].uncertain


def retry_plan(generation: VideoGeneration, confirm_resubmit: bool) -> tuple[list[dict], Decimal]:
    """The shots after a retry, and the estimate of what they will still pay for. A shot the
    provider rejected (or an uncertain one staff confirmed) is submitted again as a new
    attempt; a shot whose check failed for another reason is checked again, not repaid."""
    states = _states(generation)
    index = _current(states)
    if index is not None:
        shot = states[index]
        if shot.failed or (shot.uncertain and confirm_resubmit):
            states[index] = replace(
                shot, attempt=shot.attempt + 1, submitted=False, request=None, failed=False
            )
    adapter = provider(generation.provider)
    estimate = sum(
        (adapter.estimate_usd("video_submit", s.seconds) for s in states if not s.submitted),
        Decimal(0),
    )
    return [asdict(state) for state in states], estimate


async def queue_retry(session, generation: VideoGeneration, shots: list[dict]) -> None:
    remaining = sum(1 for shot in shots if not shot["file_key"]) or 1
    job = await jobs.enqueue(
        session,
        KIND,
        {"generation_id": str(generation.id), "deadline": deadline_for(remaining).isoformat()},
        # Keyed by the failed step it follows, so a double click queues one retry.
        idempotency_key=f"{KIND}:{generation.id}:after:{generation.job_id}",
        max_attempts=1,
        commit=False,
    )
    generation.shots = shots
    generation.job_id = job.id
    generation.progress = RETRYING


async def remove_for_voice(session, voice_id: uuid.UUID) -> list[str]:
    """Mark every narrated video voiced by a revoked clone as removed, in the caller's
    transaction. Returns the folders to delete once it has committed."""
    rows = (
        await session.execute(
            select(VideoGeneration).where(
                VideoGeneration.payload["voice_clone_id"].astext == str(voice_id)
            )
        )
    ).scalars()
    folders = []
    for generation in rows:
        generation.payload = {**generation.payload, "removed": True}
        generation.file_key = None
        generation.progress = REMOVED
        folders.append(_folder(generation))
    return folders


# --- the worker: one step per job ---


def _folder(generation: VideoGeneration) -> str:
    return f"stories/{generation.story_id}/videos/{generation.id}"


async def _update(generation_id: uuid.UUID, index: int | None = None, progress=None, **changes):
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        if index is not None:
            states = _states(generation)
            states[index] = replace(states[index], **changes)
            _store(generation, states)
        if progress:
            generation.progress = progress
        await session.commit()


@handler(KIND)
async def narrated_step(payload: dict) -> dict:
    generation_id = uuid.UUID(payload["generation_id"])
    deadline = datetime.fromisoformat(payload["deadline"])
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        if generation is None or generation.payload.get("removed"):
            return {"stale": True}
        if generation.file_key:
            return {"file_key": generation.file_key}
        states = _states(generation)
    index = _current(states)
    if index is None:
        return await _join(generation_id)
    shot = states[index]
    if not shot.submitted:
        await _submit(generation_id, index)
        return await _queue_next_step(generation_id, deadline, get_settings().video_poll_seconds)
    if shot.uncertain:
        raise UserFacingError(
            f"Shot {index + 1} was never confirmed by the provider. Check the provider; staff "
            "can submit it again, knowing it may be billed twice."
        )
    status = await _check(generation_id, index)
    if status == "done":
        return await _queue_next_step(generation_id, deadline, 0)
    if datetime.now(UTC) >= deadline:
        raise UserFacingError(
            f"The provider is still rendering shot {index + 1}. "
            "Its request ID was saved for staff follow-up."
        )
    return await _queue_next_step(generation_id, deadline, get_settings().video_poll_seconds)


async def _queue_next_step(generation_id: uuid.UUID, deadline: datetime, delay: float) -> dict:
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        job = await jobs.enqueue(
            session,
            KIND,
            {"generation_id": str(generation_id), "deadline": deadline.isoformat()},
            # Each step queues at most one next step, keyed by itself.
            idempotency_key=f"{KIND}:{generation_id}:{gateway.CURRENT_JOB.get()}",
            max_attempts=1,
            run_after=datetime.now(UTC) + timedelta(seconds=delay),
            commit=False,
        )
        generation.job_id = job.id  # the page follows the latest step
        await session.commit()
    return {"next": str(job.id)}


async def _data_url(key: str) -> str:
    image = await asyncio.to_thread(get_storage().path(key).read_bytes)
    return "data:image/webp;base64," + base64.b64encode(image).decode()


async def _submit(generation_id: uuid.UUID, index: int) -> None:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        if not settings.enable_ai_video or (
            generation.provider != "fake" and not settings.live_ai_enabled
        ):
            raise UserFacingError("AI video generation is disabled for this demo.")
        states = _states(generation)
        shot = states[index]
        image_key = generation.image_key if index == 0 else states[index - 1].frame_key
        reference_key = states[0].reference_key if index > 0 else None
        name, data, input_hash = generation.provider, generation.payload, generation.input_hash
        # Marked before the call: if the answer is lost, the shot is known to be uncertain.
        states[index] = replace(shot, submitted=True)
        _store(generation, states)
        generation.progress = SUBMITTING
        await session.commit()
    arguments = {
        "model": data["model"],
        "prompt": shot.prompt,
        "aspect_ratio": data["aspect_ratio"],
        "seed": data["seed"],
        "seconds": shot.seconds,
        "request_id": f"{input_hash[:20]}-{index}-{shot.attempt}",
    }
    if image_key:
        arguments["image_url"] = await _data_url(image_key)
    if reference_key:
        arguments["reference_url"] = await _data_url(reference_key)
    adapter = provider(name)
    try:
        request = await gateway.call(
            "video_submit",
            adapter,
            shot.cache_parts(input_hash, index),
            shot.seconds,
            lambda: adapter.submit(arguments),
            charge_on_failure=True,
        )
    except (NotStarted, gateway.LiveAIOff, gateway.SpendingLimit):
        # Nothing started at the provider: the shot can simply be submitted again later.
        await _update(generation_id, index, submitted=False)
        raise
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise UserFacingError(
            f"Shot {index + 1} could not be confirmed with the provider. Check the provider; "
            "staff can submit it again, knowing it may be billed twice."
        ) from exc
    await _update(generation_id, index, progress=RENDERING, request=request)


async def _frame(clip, demuxer: str, at: float, key: str) -> None:
    """One frame of a clip at `at` seconds, as WebP; a clip shorter than that is held."""
    await render(
        key,
        *ffmpeg_inputs(demuxer, [clip]),
        "-vf",
        f"tpad=stop_mode=clone:stop_duration={at + 1:.3f},"
        f"trim=start={max(at - 0.04, 0):.3f},setpts=PTS-STARTPTS",
        "-frames:v",
        "1",
        "-c:v",
        "libwebp",
        "-f",
        "webp",
    )


async def _check(generation_id: uuid.UUID, index: int) -> str:
    """Ask the provider once about a shot; when ready, store it, the frame to continue from
    and (first shot) the reference frame of the people. Returns running, queued, unavailable
    or done."""
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        states = _states(generation)
        name, input_hash, folder = generation.provider, generation.input_hash, _folder(generation)
    shot, count = states[index], len(states)
    adapter = provider(name)
    try:
        result = await adapter.poll(shot.request)
        status = result["status"]
    except (httpx.HTTPError, ValueError, KeyError):
        return "unavailable"
    except VideoRejected:
        # The provider ended the job: a retry submits the shot again (a new paid attempt).
        await _update(generation_id, index, failed=True)
        raise
    if status != "done":
        await _update(generation_id, progress=RENDERING)
        return status
    extension = clip_extension(name)

    async def download() -> tuple[dict, bytes]:
        return {}, await adapter.download(result.get("video_url", ""))

    try:
        _, cache_key = await gateway.call_file(
            "video_result",
            FreeVideoRead(name),
            shot.cache_parts(input_hash, index),
            0,
            download,
            extension,
        )
    except (httpx.HTTPError, UserFacingError, ValueError, KeyError):
        return "unavailable"  # ready but not arrived: fetched again on the next check
    storage = get_storage()
    clip_key = f"{folder}/shot-{index}{extension}"
    await asyncio.to_thread(storage.copy, cache_key, clip_key)
    clip, demuxer = storage.path(clip_key), DEMUXERS[extension]
    changes: dict = {"file_key": clip_key}
    if index + 1 < count:
        changes["frame_key"] = f"{folder}/shot-{index}-end.webp"
        await _frame(clip, demuxer, shot.span, changes["frame_key"])
        if index == 0:
            changes["reference_key"] = f"{folder}/reference.webp"
            await _frame(clip, demuxer, shot.span * REFERENCE_AT, changes["reference_key"])
    await _update(generation_id, index, progress=SHOT_READY, **changes)
    return "done"


async def _has_audio(path) -> bool:
    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
        "-of", "csv=p=0", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    out, _ = await process.communicate()
    return bool(out.strip())


async def _join(generation_id: uuid.UUID) -> dict:
    """Join the shots, each cut or held to its planned length, hold the last frame for the
    tail, lay the soundtrack over them (stopping at the last covered line) with the shots' own
    sound ducked underneath, and burn in the subtitles."""
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        states, data, name = _states(generation), generation.payload, generation.provider
        folder = _folder(generation)
        generation.progress = JOINING
        await session.commit()
    storage = get_storage()
    width, height = SIZES.get(data["aspect_ratio"], SIZES["16:9"])
    lines = [Line(**line) for line in data["lines"]]
    tail = TAIL_MS / 1000
    total = states[-1].end_ms / 1000 + tail
    voice_end = (lines[-1].end_ms + LEAD_MS) / 1000
    fade = min(VOICE_FADE_MS / 1000, voice_end)
    demuxer = DEMUXERS[clip_extension(name)]
    clips = [storage.path(state.file_key) for state in states]
    inputs = [arg for clip in clips for arg in ffmpeg_inputs(demuxer, [clip])]
    inputs += ffmpeg_inputs("mp3", [storage.path(data["audio_key"])])
    graph = []
    for i, state in enumerate(states):
        graph.append(
            f"[{i}:v]tpad=stop_mode=clone:stop_duration={state.span:.3f},"
            f"trim=duration={state.span:.3f},setpts=PTS-STARTPTS,fps=24,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]"
        )
        if await _has_audio(clips[i]):
            graph.append(
                f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,"
                f"atrim=duration={state.span:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
        else:
            graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={state.span:.3f}[a{i}]")
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(states)))
    graph.append(f"{joined}concat=n={len(states)}:v=1:a=1[vcat][bed0]")
    graph.append(f"[vcat]tpad=stop_mode=clone:stop_duration={tail:.3f}[vheld]")
    video = "[vheld]"
    if data.get("subtitles"):
        captions_key = f"{folder}/subtitles.ass"
        await asyncio.to_thread(
            storage.write_bytes,
            captions_key,
            subtitles(lines, width, height, data.get("rtl", True)).encode(),
        )
        path = str(storage.path(captions_key))
        if not SAFE_PATH.match(path):
            raise RuntimeError("The media folder path has characters FFmpeg filters cannot take.")
        graph.append(f"[vheld]subtitles=filename={path}[vout]")
        video = "[vout]"
    voice = len(states)
    graph += [
        f"[{voice}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={LEAD_MS}:all=1,"
        f"atrim=duration={voice_end:.3f},afade=t=out:st={voice_end - fade:.3f}:d={fade:.3f},"
        f"apad,atrim=duration={total:.3f},asplit=2[voice][key]",
        f"[bed0]apad,atrim=duration={total:.3f},volume=0.6[bed]",
        "[bed][key]sidechaincompress=threshold=0.02:ratio=12:attack=15:release=400[ducked]",
        "[ducked][voice]amix=inputs=2:duration=first:normalize=0,"
        "loudnorm=I=-16:TP=-1.5:LRA=11[aout]",
    ]
    target = f"{folder}/result.mp4"
    await render(
        target,
        *inputs,
        "-filter_complex", ";".join(graph),
        "-map", video, "-map", "[aout]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-f", "mp4",
    )  # fmt: skip
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        if generation is None or generation.payload.get("removed"):
            # The narrator's voice was revoked while the shots were joined.
            await asyncio.to_thread(storage.delete, target)
            return {"stale": True}
        generation.file_key = target
        generation.progress = READY
        await session.commit()
    return {"file_key": target, "shots": len(states)}
