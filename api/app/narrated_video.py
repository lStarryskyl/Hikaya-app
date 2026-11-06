"""Narrated AI videos (docs/DECISIONS.md, "Narrated AI videos").

The story's soundtrack (its narration, or the storyteller's recording) is the script: its
timed lines are cut into shots at line boundaries, the first shot is made from the story
photo and each later one from the frame where the previous shot is cut, and FFmpeg joins the
shots' pictures, lays the soundtrack on as the only sound (the provider's own audio, voices
included, is dropped) and burns in subtitles.

Planning happens in the web request and calls no provider. Everything else runs in worker
jobs, one step per job (submit a shot, check it once, or join them), so the worker is never
held while a shot renders.
"""

import asyncio
import base64
import math
import re
import uuid
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select

from app import audio, gateway, jobs
from app.assets import asset_of
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import NotStarted, UserFacingError
from app.handlers import handler
from app.media import ffmpeg_inputs, narration_for, render
from app.models import AssetKind, Job, JobStatus, Story, VideoGeneration
from app.pipeline import get_layer
from app.providers.script import (
    LANGUAGES,
    FakeScriptWriter,
    Screenplay,
    ScriptRequest,
    ShotBrief,
    screenwriter_prompt,
    script_writer,
)
from app.providers.video import FreeVideoRead, VideoRejected, clip_extension, provider
from app.storage import get_storage

KIND = "narrated_video"
LEAD_MS = 300  # picture before the first word
TAIL_MS = 600  # the last frame held after the last word (not asked of the provider)
VOICE_FADE_MS = 120  # the voice fades out at the end of the last line the video covers
RLE, PDF = "‫", "‬"  # right-to-left embedding around Arabic subtitle lines
SIZES = {"16:9": (1280, 720), "9:16": (720, 1280)}
DEMUXERS = {".webm": "matroska", ".mp4": "mov"}
# Storage paths go into an FFmpeg filter argument unquoted, so only plain characters pass.
SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")

# Progress is one of these fixed messages (the console translates them); the shot number is
# reported beside it.
WRITING_SCRIPT = "Writing the shot script"
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


def shot_prompt(
    index: int,
    count: int,
    title: str,
    place: str,
    words: str,
    direction: str,
    *,
    audio: str = "soundtrack",
    scene: dict | None = None,
    cast: str = "",
    setting: str = "",
    narrator: str = "",
    spoken: str = "",
    language: str = "",
) -> str:
    """One shot's prompt: what is said during it, how it continues the film and, from the
    refined script, the cast, setting, action and camera. Each shot gets one image: Omni reads
    a second image as the shot's last frame (seen live on 2026-11-06), so the people's look is
    carried by the opening frame and by this prompt. With Omni's own voice, it also asks for a
    voice-over of the shot's words over the scene's natural sounds."""
    continuity = (
        "Start from the provided photo."
        if index == 0
        else "This shot continues straight on from the previous shot: the image given is its "
        "last frame, so start exactly from it and the cut is seamless. Keep the same people "
        "with the same faces, hair and clothes as in that image, even when the scene moves to "
        "another place."
    )
    parts = [
        f"Shot {index + 1} of {count} of one continuous short film for the heritage story "
        f'"{title}" from {place or "Jordan"}.',
        continuity,
    ]
    if cast:
        parts.append(f"The people, exactly the same in every shot: {cast}")
    if setting:
        parts.append(f"Setting: {setting}")
    if scene:
        parts.append(f"In this shot: {scene['action']} Camera: {scene['camera']}")
    parts.append(f'The narrator is saying: "{words}" Show what these words describe.')
    if audio == "omni":
        sounds = (scene or {}).get("sound") or "the natural sounds of the scene"
        voice = narrator or "a warm, calm voice"
        tongue = language or "the story's own language"
        parts.append(
            f"Sound: an off-screen voice-over narrator ({voice}) says, clearly and unhurried, "
            f'in {tongue}: "{spoken}". Under the voice, only {sounds}. No music.'
        )
    parts += [
        f"Visual direction: {direction}",
        "No one speaks or moves their lips on camera; no text, captions or logos on screen.",
    ]
    return "\n".join(parts)


def _shot_words(lines: list[Line], indexes) -> str:
    """What is said during a shot, in English when there is a translation."""
    words = " ".join((lines[i].english or lines[i].spoken).strip() for i in indexes)
    return words.strip() or "A quiet pause in the story."


def _spoken(lines: list[Line], indexes) -> str:
    """What is said during a shot, in the story's own language."""
    return " ".join(lines[i].spoken.strip() for i in indexes).strip()


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
    language: str  # jordanian | msa | english
    script: str  # who refines the shot script: fake | gemini

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
            "script": self.script,
        }


async def _soundtrack(
    session, story: Story, kind: str
) -> tuple[str, list[Line], str, bool, uuid.UUID | None]:
    """The soundtrack's file, its timed lines, their language, whether every line has an
    English translation, and the cloned voice that read it (if any)."""
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
    return key, lines, language, english is not None or language == "english", clone_id


def _script_request(
    title: str, place: str, lines: list[Line], shots, direction: str, photo, language, audio
) -> ScriptRequest:
    return ScriptRequest(
        title=title,
        place=place,
        story=" ".join((line.english or line.spoken).strip() for line in lines),
        shots=[
            ShotBrief((shot.end_ms - shot.start_ms) / 1000, _shot_words(lines, shot.lines))
            for shot in shots
        ],
        direction=direction,
        photo=photo,
        spoken_language=language,
        audio=audio,
    )


async def plan_story(
    session, story: Story, provider_name: str, soundtrack: str, audio: str = "soundtrack"
) -> StoryPlan:
    adapter = provider(provider_name)
    shortest, longest = adapter.shot_seconds
    key, lines, language, english, clone_id = await _soundtrack(session, story, soundtrack)
    kept, shots = plan_shots(
        lines, longest, get_settings().narrated_video_max_seconds, min_shot_seconds=shortest
    )
    estimate = sum(
        (adapter.estimate_usd("video_submit", shot.seconds) for shot in shots), Decimal(0)
    )
    writer = script_writer()
    if writer.budget and writer.budget == adapter.budget:
        request = _script_request(
            story.title, story.place_name, kept, shots, "", None, language, audio
        )
        estimate += writer.estimate_usd("script", len(screenwriter_prompt(request)))
    return StoryPlan(
        key,
        kept,
        len(lines),
        shots,
        language != "english",
        english,
        clone_id,
        estimate,
        language,
        get_settings().script_provider,
    )


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

    @property
    def uncertain(self) -> bool:
        """Submitted, but the provider's answer never arrived: it may be rendering (and billed)."""
        return self.submitted and not self.request

    @property
    def span(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    def cache_parts(self, input_hash: str, index: int) -> tuple[str, ...]:
        return (input_hash, f"shot-{index}", f"try-{self.attempt}")


_SHOT_FIELDS = {f.name for f in fields(ShotState)}


def _states(generation: VideoGeneration) -> list[ShotState]:
    # Fields an earlier version stored and no longer uses are ignored.
    return [
        ShotState(**{k: v for k, v in shot.items() if k in _SHOT_FIELDS})
        for shot in generation.shots
    ]


def _store(generation: VideoGeneration, states: list[ShotState]) -> None:
    generation.shots = [asdict(state) for state in states]


def new_shots(
    plan: StoryPlan, title: str, place: str, direction: str, audio: str = "soundtrack"
) -> list[dict]:
    """The stored shots of a new narrated video. Their prompts are rewritten from the refined
    script once it is written (the first step of the video's jobs)."""
    count = len(plan.shots)
    return [
        asdict(
            ShotState(
                shot.start_ms,
                shot.end_ms,
                shot.seconds,
                list(shot.lines),
                shot_prompt(
                    index,
                    count,
                    title,
                    place,
                    _shot_words(plan.lines, shot.lines),
                    direction,
                    audio=audio,
                    spoken=_spoken(plan.lines, shot.lines),
                    language=LANGUAGES.get(plan.language, plan.language),
                ),
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
        states, written = _states(generation), generation.script is not None
    if not written:
        # The refined shot script comes first: no shot is paid for before it exists.
        states = await _write_script(generation_id)
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


async def _write_script(generation_id: uuid.UUID) -> list[ShotState]:
    """Have the screenwriter refine the shot script (through the gateway: ledger and cache),
    store it and rebuild every shot's prompt from it. Returns the updated shots."""
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        story = await session.get(Story, generation.story_id)
        title, place = story.title, story.place_name
        data, states, input_hash = generation.payload, _states(generation), generation.input_hash
        image_key = generation.image_key
        generation.progress = WRITING_SCRIPT
        await session.commit()
    lines = [Line(**line) for line in data["lines"]]
    language, audio = data.get("language", "jordanian"), data.get("audio", "soundtrack")
    photo = await asyncio.to_thread(get_storage().path(image_key).read_bytes) if image_key else None
    request = _script_request(title, place, lines, states, data["prompt"], photo, language, audio)
    writer = script_writer()

    async def run() -> dict:
        return (await writer.refine(request)).to_dict()

    script = await gateway.call(
        "script", writer, (input_hash, "script"), len(screenwriter_prompt(request)), run
    )
    screenplay = Screenplay.from_dict(script)
    # The fake writer only repeats each shot's words, so its scenes add nothing to a prompt.
    refined = not isinstance(writer, FakeScriptWriter)
    count = len(states)
    states = [
        replace(
            state,
            prompt=shot_prompt(
                i,
                count,
                title,
                place,
                _shot_words(lines, state.lines),
                data["prompt"],
                audio=audio,
                scene=(
                    {"action": scene.action, "camera": scene.camera, "sound": scene.sound}
                    if refined
                    else None
                ),
                cast=screenplay.cast,
                setting=screenplay.setting,
                narrator=screenplay.narrator,
                spoken=_spoken(lines, state.lines),
                language=LANGUAGES.get(language, language),
            ),
        )
        for i, (state, scene) in enumerate(zip(states, screenplay.scenes, strict=True))
    ]
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        _store(generation, states)
        generation.script = {"provider": get_settings().script_provider, **script}
        await session.commit()
    return states


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
    """Ask the provider once about a shot; when ready, store it and the frame to continue
    from. Returns running, queued, unavailable or done."""
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        states = _states(generation)
        name, input_hash, folder = generation.provider, generation.input_hash, _folder(generation)
        whole_clips = generation.payload.get("audio") == "omni"
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
        # Past the clip's end, the frame is its last one (held): where a whole clip ends.
        cut = shot.seconds + 0.5 if whole_clips else shot.span
        await _frame(clip, demuxer, cut, changes["frame_key"])
    await _update(generation_id, index, progress=SHOT_READY, **changes)
    return "done"


def _onto_clips(lines: list[Line], states: list[ShotState], lengths: list[float]) -> list[Line]:
    """Line timings moved from the planned shots onto whole clips: each moment of a shot is
    stretched to its clip's real length, so subtitles stay with the shot they belong to."""
    starts = [sum(lengths[:i]) * 1000 for i in range(len(lengths))]

    def moved(ms: int) -> int:
        at = ms + LEAD_MS  # in video time
        for state, start, length in zip(states, starts, lengths, strict=True):
            if at <= state.end_ms:
                within = max(0, at - state.start_ms) / max(state.end_ms - state.start_ms, 1)
                return round(start + within * length * 1000) - LEAD_MS
        return round(starts[-1] + lengths[-1] * 1000) - LEAD_MS

    return [
        replace(line, start_ms=moved(line.start_ms), end_ms=moved(line.end_ms)) for line in lines
    ]


async def _has_audio(path) -> bool:
    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
        "-of", "csv=p=0", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    out, _ = await process.communicate()
    return bool(out.strip())


async def _join(generation_id: uuid.UUID) -> dict:
    """Join the shots' pictures, each cut or held to its planned length, hold the last frame
    for the tail and burn in the subtitles. The sound is either the story's soundtrack alone
    (stopping at the last covered line; Omni's own audio, voices included, is never used) or,
    with Omni's own voice, the shots' own audio and nothing else."""
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
    demuxer = DEMUXERS[clip_extension(name)]
    clips = [storage.path(state.file_key) for state in states]
    omni_voice = data.get("audio") == "omni"
    # With Omni's own voice each clip is kept whole: Omni paces its voice-over to the length it
    # was asked for, so cutting a clip to the planned span cuts off its last words.
    lengths = (
        [await audio.duration_ms(clip) / 1000 for clip in clips]
        if omni_voice
        else [state.span for state in states]
    )
    if omni_voice:
        lines = _onto_clips(lines, states, lengths)
    total = sum(lengths) + tail
    voice_end = (lines[-1].end_ms + LEAD_MS) / 1000
    fade = min(VOICE_FADE_MS / 1000, voice_end)
    inputs = [arg for clip in clips for arg in ffmpeg_inputs(demuxer, [clip])]
    if not omni_voice:
        inputs += ffmpeg_inputs("mp3", [storage.path(data["audio_key"])])
    graph = []
    for i, length in enumerate(lengths):
        graph.append(
            f"[{i}:v]tpad=stop_mode=clone:stop_duration={length:.3f},"
            f"trim=duration={length:.3f},setpts=PTS-STARTPTS,fps=24,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]"
        )
    joined = "".join(f"[v{i}]" for i in range(len(states)))
    graph.append(f"{joined}concat=n={len(states)}:v=1:a=0[vcat]")
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
    normalise = f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,apad,atrim=duration={total:.3f}"
    if omni_voice:
        # Omni's own audio (its voice-over and the scene's sounds), each clip whole.
        for i, length in enumerate(lengths):
            graph.append(
                f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,"
                f"atrim=duration={length:.3f},asetpts=PTS-STARTPTS[a{i}]"
                if await _has_audio(clips[i])
                else f"anullsrc=r=48000:cl=stereo,atrim=duration={length:.3f}[a{i}]"
            )
        sounds = "".join(f"[a{i}]" for i in range(len(states)))
        graph.append(f"{sounds}concat=n={len(states)}:v=0:a=1,{normalise}[aout]")
    else:
        # Only the story's soundtrack is heard: the shots' own audio is never used.
        graph.append(
            f"[{len(states)}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"adelay={LEAD_MS}:all=1,atrim=duration={voice_end:.3f},"
            f"afade=t=out:st={voice_end - fade:.3f}:d={fade:.3f},{normalise}[aout]"
        )
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
