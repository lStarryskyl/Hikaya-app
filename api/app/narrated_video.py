"""Narrated AI videos (docs/DECISIONS.md, "Narrated AI videos").

The story's soundtrack (its narration, or the storyteller's recording) is the script: its
timed lines are cut into shots at line boundaries, the first shot is made from the story
photo and each later one from the frame where the previous shot is cut, and FFmpeg joins the
shots, lays the soundtrack over them (the provider's own sound kept low and ducked under the
voice) and burns in subtitles.

Planning happens in the web request and calls no provider. Everything else runs in worker
jobs, one step per job (submit a shot, check it once, or join them), so the worker is never
held while a shot renders.
"""

import asyncio
import base64
import math
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from app import gateway, jobs
from app.assets import asset_of
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import UserFacingError
from app.handlers import handler
from app.media import _inputs, _render, narration_for
from app.models import AssetKind, Job, JobStatus, Story, TextLayer, VideoGeneration
from app.providers.video import FreeVideoRead, provider
from app.storage import get_storage

KIND = "narrated_video"
LEAD_MS = 300  # picture before the first word
TAIL_MS = 600  # the last frame held after the last word
MIN_SHOT_SECONDS = 3
RLM = "‏"
SIZES = {"16:9": (1280, 720), "9:16": (720, 1280)}
# Storage paths go into an FFmpeg filter argument unquoted, so only plain characters pass.
SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")


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


def plan(
    lines: list[Line], max_shot_seconds: int, max_total_seconds: int
) -> tuple[list[Line], list[Shot]]:
    """The whole lines that fit in `max_total_seconds`, and shots covering them, cut where a
    line starts and never longer than `max_shot_seconds`. A line longer than a shot is split
    evenly. The first shot starts at 0 (the lead-in); the last ends after the tail."""
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
    total = kept[-1].end_ms + LEAD_MS + TAIL_MS
    longest = max_shot_seconds * 1000
    cuts = [line.start_ms + LEAD_MS for line in kept[1:]] + [total]
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
            max(MIN_SHOT_SECONDS, math.ceil((b - a) / 1000)),
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
    """One shot's prompt: what is said during it, and how it continues the film."""
    continuity = (
        "Start from the provided photo."
        if index == 0
        else "This shot continues straight on from the previous shot: the image given is its "
        "last frame. Keep the same place, light, colours, camera style and any people "
        "exactly as they are."
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
            # Keeps a closing full stop at the end of the right-to-left line.
            spoken = RLM + spoken + RLM
        english = _clean(line.english or "")
        text = (
            f"{{\\fs{small}\\c&HE6F2FF&}}{spoken}\\N{{\\fs{base}\\c&HFFFFFF&}}{english}"
            if english
            else spoken
        )
        start, end = _time(line.start_ms + LEAD_MS), _time(line.end_ms + LEAD_MS)
        events.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}")
    return header + "\n".join(events) + "\n"


# --- the plan for a story (web request: database only, no provider call) ---


@dataclass
class Planned:
    soundtrack_key: str
    lines: list[Line]  # the lines the video covers
    lines_total: int
    shots: list[Shot]
    rtl: bool
    estimate: Decimal

    @property
    def seconds(self) -> float:
        return self.shots[-1].end_ms / 1000

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
        }


async def _layer(session, story_id: uuid.UUID, kind: str) -> TextLayer | None:
    from sqlalchemy import select

    return (
        await session.execute(
            select(TextLayer).where(TextLayer.story_id == story_id, TextLayer.kind == kind)
        )
    ).scalar_one_or_none()


async def _soundtrack(session, story: Story, kind: str) -> tuple[str, list[Line], bool]:
    """The soundtrack's file, its timed lines and whether they are right-to-left."""
    if kind == "narration":
        found = await narration_for(session, story.id)
        if found is None:
            raise UserFacingError(
                "This story has no narration yet; it is made when the story is submitted."
            )
        row, asset = found
        segments, language, key = row.segments, row.language, asset.storage_key
    else:
        asset = await asset_of(session, story.id, AssetKind.AUDIO)
        layer = await _layer(session, story.id, "polished") or await _layer(
            session, story.id, "verbatim"
        )
        if asset is None or layer is None or not layer.segments:
            raise UserFacingError("This story has no recording with a transcript.")
        segments, language, key = layer.segments, layer.language, asset.storage_key
    english = None
    if language != "english":
        layer = await _layer(session, story.id, "translation_en")
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
    return key, lines, language != "english"


async def plan_for(
    session, story: Story, provider_name: str, max_shot_seconds: int, soundtrack: str
) -> Planned:
    key, lines, rtl = await _soundtrack(session, story, soundtrack)
    kept, shots = plan(lines, max_shot_seconds, get_settings().narrated_video_max_seconds)
    adapter = provider(provider_name)
    estimate = sum(
        (adapter.estimate_usd("video_submit", shot.seconds) for shot in shots), Decimal(0)
    )
    return Planned(key, kept, len(lines), shots, rtl, estimate)


def shot_states(planned: Planned, title: str, place: str, direction: str) -> list[dict]:
    """The stored state of each shot of a new narrated video."""
    count = len(planned.shots)
    return [
        {
            "start_ms": shot.start_ms,
            "end_ms": shot.end_ms,
            "seconds": shot.seconds,
            "lines": list(shot.lines),
            "prompt": shot_prompt(
                index, count, title, place, _shot_words(planned.lines, shot), direction
            ),
            "attempt": 1,
            "submitted": False,
            "request": None,
            "failed": False,
            "file_key": None,
            "frame_key": None,
        }
        for index, shot in enumerate(planned.shots)
    ]


def payload_lines(planned: Planned) -> list[dict]:
    return [asdict(line) for line in planned.lines]


def deadline_for(shots: int) -> datetime:
    """Each shot gets the full wait a single video gets."""
    return datetime.now(UTC) + timedelta(seconds=get_settings().video_max_wait_seconds * shots)


# --- retrying ---


def _current(shots: list[dict]) -> int | None:
    return next((i for i, shot in enumerate(shots) if not shot["file_key"]), None)


def retryable(generation: VideoGeneration, job: Job | None) -> bool:
    """A failed narrated video can go on from where it stopped, unless a shot's submission
    is uncertain (it may have been accepted and billed: that needs a person to check)."""
    if not generation.shots or generation.file_key or job is None:
        return False
    if job.status != JobStatus.FAILED:
        return False
    index = _current(generation.shots)
    if index is None:
        return True  # joining failed: the shots are all there
    shot = generation.shots[index]
    return not (shot["submitted"] and not shot["request"])


async def retry(session, generation: VideoGeneration) -> None:
    """Queue the next step again; a shot the provider rejected is submitted once more."""
    shots = [dict(shot) for shot in generation.shots]
    index = _current(shots)
    if index is not None and shots[index]["failed"]:
        shots[index].update(
            attempt=shots[index]["attempt"] + 1, submitted=False, request=None, failed=False
        )
    remaining = len(shots) - (index if index is not None else len(shots)) or 1
    job = await jobs.enqueue(
        session,
        KIND,
        {
            "generation_id": str(generation.id),
            "deadline": deadline_for(remaining).isoformat(),
        },
        idempotency_key=f"{KIND}:{generation.id}:retry:{uuid.uuid4()}",
        max_attempts=1,
        commit=False,
    )
    generation.shots = shots
    generation.job_id = job.id
    generation.progress = "Retrying"


# --- the worker: one step per job ---


def _folder(generation: VideoGeneration) -> str:
    return f"stories/{generation.story_id}/videos/{generation.id}"


def _container(name: str) -> tuple[str, str]:
    """(file extension, FFmpeg demuxer) of a provider's clips."""
    return (".webm", "matroska") if name == "fake" else (".mp4", "mov")


async def _save(generation_id: uuid.UUID, index: int | None = None, progress=None, **changes):
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        if index is not None:
            shots = [dict(shot) for shot in generation.shots]
            shots[index].update(changes)
            generation.shots = shots
        if progress:
            generation.progress = progress
        await session.commit()


@handler(KIND)
async def step(payload: dict) -> dict:
    generation_id = uuid.UUID(payload["generation_id"])
    deadline = datetime.fromisoformat(payload["deadline"])
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        if generation is None:
            return {"stale": True}
        if generation.file_key:
            return {"file_key": generation.file_key}
        shots = [dict(shot) for shot in generation.shots]
    index = _current(shots)
    if index is None:
        return await _join(generation_id)
    shot = shots[index]
    if not shot["submitted"]:
        await _submit(generation_id, index)
        return await _again(generation_id, deadline, get_settings().video_poll_seconds)
    if not shot["request"]:
        raise UserFacingError(
            f"Shot {index + 1} could not be confirmed with the provider. "
            "Check the provider before trying again."
        )
    status = await _check(generation_id, index)
    if status == "done":
        return await _again(generation_id, deadline, 0)
    if datetime.now(UTC) >= deadline:
        raise UserFacingError(
            f"The provider is still rendering shot {index + 1}. "
            "Its request ID was saved for staff follow-up."
        )
    return await _again(generation_id, deadline, get_settings().video_poll_seconds)


async def _again(generation_id: uuid.UUID, deadline: datetime, delay: float) -> dict:
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


async def _submit(generation_id: uuid.UUID, index: int) -> None:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        if not settings.enable_ai_video or (
            generation.provider != "fake" and not settings.live_ai_enabled
        ):
            raise UserFacingError("AI video generation is disabled for this demo.")
        shots = generation.shots
        shot = shots[index]
        image_key = generation.image_key if index == 0 else shots[index - 1]["frame_key"]
        name, data, input_hash = generation.provider, generation.payload, generation.input_hash
    count = len(shots)
    # Marked before the call: if the answer is lost, the shot is known to be uncertain.
    await _save(
        generation_id,
        index,
        progress=f"Shot {index + 1} of {count}: submitting",
        submitted=True,
    )
    arguments = {
        "model": data["model"],
        "prompt": shot["prompt"],
        "aspect_ratio": data["aspect_ratio"],
        "seed": data["seed"],
        "seconds": shot["seconds"],
        "request_id": f"{input_hash[:20]}-{index}-{shot['attempt']}",
    }
    if image_key:
        image = await asyncio.to_thread(get_storage().path(image_key).read_bytes)
        arguments["image_url"] = "data:image/webp;base64," + base64.b64encode(image).decode()
    adapter = provider(name)
    try:
        request = await gateway.call(
            "video_submit",
            adapter,
            (input_hash, f"shot-{index}", f"try-{shot['attempt']}"),
            shot["seconds"],
            lambda: adapter.submit(arguments),
            charge_on_failure=True,
        )
    except UserFacingError:
        # Refused outright (live AI off, a cap, or the provider said no): nothing started.
        await _save(generation_id, index, submitted=False)
        raise
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise UserFacingError(
            f"Shot {index + 1} could not be confirmed with the provider. "
            "Check the provider before trying again."
        ) from exc
    await _save(
        generation_id,
        index,
        progress=f"Shot {index + 1} of {count}: rendering",
        request=request,
    )


async def _check(generation_id: uuid.UUID, index: int) -> str:
    """Ask the provider once about a shot; when ready, store it and the frame to continue
    from. Returns running, queued, unavailable or done."""
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        shots = generation.shots
        shot = shots[index]
        name, input_hash, folder = generation.provider, generation.input_hash, _folder(generation)
    count = len(shots)
    adapter = provider(name)
    try:
        result = await adapter.poll(shot["request"])
        status = result["status"]
    except (httpx.HTTPError, ValueError, KeyError):
        return "unavailable"
    except UserFacingError:
        await _save(generation_id, index, failed=True)
        raise
    if status != "done":
        await _save(generation_id, progress=f"Shot {index + 1} of {count}: rendering")
        return status
    extension, demuxer = _container(name)

    async def download() -> tuple[dict, bytes]:
        return {}, await adapter.download(result.get("video_url", ""))

    try:
        _, cache_key = await gateway.call_file(
            "video_result",
            FreeVideoRead(name),
            (input_hash, f"shot-{index}", f"try-{shot['attempt']}"),
            0,
            download,
            extension,
        )
    except (httpx.HTTPError, UserFacingError, ValueError, KeyError):
        return "unavailable"  # ready but not arrived: fetched again on the next check
    storage = get_storage()
    clip_key = f"{folder}/shot-{index}{extension}"
    await asyncio.to_thread(storage.copy, cache_key, clip_key)
    frame_key = None
    if index + 1 < count:
        frame_key = f"{folder}/shot-{index}-end.webp"
        span = (shot["end_ms"] - shot["start_ms"]) / 1000
        await _render(
            frame_key,
            *_inputs(demuxer, [storage.path(clip_key)]),
            "-vf",
            f"tpad=stop_mode=clone:stop_duration={span:.3f},"
            f"trim=start={max(span - 0.04, 0):.3f},setpts=PTS-STARTPTS",
            "-frames:v",
            "1",
            "-c:v",
            "libwebp",
            "-f",
            "webp",
        )
    await _save(
        generation_id,
        index,
        progress=f"Shot {index + 1} of {count} ready",
        file_key=clip_key,
        frame_key=frame_key,
    )
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
    """Join the shots, each cut or held to its planned length, lay the soundtrack over them
    with the shots' own sound ducked underneath, and burn in the subtitles."""
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        shots, data, name = generation.shots, generation.payload, generation.provider
        folder = _folder(generation)
    await _save(generation_id, progress="Joining the shots")
    storage = get_storage()
    width, height = SIZES.get(data["aspect_ratio"], SIZES["16:9"])
    total = shots[-1]["end_ms"] / 1000
    _, demuxer = _container(name)
    clips = [storage.path(shot["file_key"]) for shot in shots]
    inputs = [arg for clip in clips for arg in _inputs(demuxer, [clip])]
    inputs += _inputs("mp3", [storage.path(data["audio_key"])])
    graph = []
    for i, shot in enumerate(shots):
        span = (shot["end_ms"] - shot["start_ms"]) / 1000
        graph.append(
            f"[{i}:v]tpad=stop_mode=clone:stop_duration={span:.3f},trim=duration={span:.3f},"
            f"setpts=PTS-STARTPTS,fps=24,scale={width}:{height}:force_original_aspect_ratio="
            f"decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]"
        )
        if await _has_audio(clips[i]):
            graph.append(
                f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,"
                f"atrim=duration={span:.3f},asetpts=PTS-STARTPTS[a{i}]"
            )
        else:
            graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={span:.3f}[a{i}]")
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(shots)))
    graph.append(f"{joined}concat=n={len(shots)}:v=1:a=1[vcat][bed0]")
    video = "[vcat]"
    if data.get("subtitles"):
        captions_key = f"{folder}/subtitles.ass"
        lines = [Line(**line) for line in data["lines"]]
        await asyncio.to_thread(
            storage.write_bytes,
            captions_key,
            subtitles(lines, width, height, data.get("rtl", True)).encode(),
        )
        path = str(storage.path(captions_key))
        if not SAFE_PATH.match(path):
            raise RuntimeError("The media folder path has characters FFmpeg filters cannot take.")
        graph.append(f"[vcat]subtitles=filename={path}[vout]")
        video = "[vout]"
    voice = len(shots)
    graph += [
        f"[{voice}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={LEAD_MS}:all=1,"
        f"apad,atrim=duration={total:.3f},asplit=2[voice][key]",
        "[bed0]volume=0.6[bed]",
        "[bed][key]sidechaincompress=threshold=0.02:ratio=12:attack=15:release=400[ducked]",
        "[ducked][voice]amix=inputs=2:duration=first:normalize=0,"
        "loudnorm=I=-16:TP=-1.5:LRA=11[aout]",
    ]
    target = f"{folder}/result.mp4"
    await _render(
        target,
        *inputs,
        "-filter_complex", ";".join(graph),
        "-map", video, "-map", "[aout]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", "-f", "mp4",
    )  # fmt: skip
    async with get_sessionmaker()() as session:
        generation = await session.get(VideoGeneration, generation_id)
        generation.file_key = target
        generation.progress = "Video ready"
        await session.commit()
    return {"file_key": target, "shots": len(shots)}
