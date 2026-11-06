"""Narrated AI videos: shots planned from the story's soundtrack, chained by their last frame,
joined, voiced and subtitled (docs/DECISIONS.md, "Narrated AI videos").

The provider's HTTP is mocked; FFmpeg runs for real on generated clips, so the joining,
timing, audio and subtitles are the real thing.
"""

import base64
import json
import re
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app import gateway, photos
from app.config import get_settings
from app.errors import UserFacingError
from app.models import (
    Asset,
    Narration,
    SpendEntry,
    Story,
    TextLayer,
    VideoGeneration,
    VoiceClone,
)
from app.narrated_video import LEAD_MS, TAIL_MS, Line, Shot, plan_shots, shot_prompt, subtitles
from app.storage import get_storage
from tests.http_mock import mock_http
from tests.test_moderation import drain
from tests.test_videos import admin

# --- media made with FFmpeg for the tests ---


def ffmpeg_bytes(*args: str) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-v", "error", *args, "pipe:1"], check=True, capture_output=True
    ).stdout


def clip(seconds: int) -> bytes:
    """A small MP4 with picture and sound (a 3 kHz tone, like Omni's own audio), as a provider
    would return."""
    return ffmpeg_bytes(
        "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=24:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=3000:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-movflags", "frag_keyframe+empty_moov", "-f", "mp4",
    )  # fmt: skip


def tone(seconds: float) -> bytes:
    return ffmpeg_bytes(
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}", "-ac", "1", "-f", "mp3"
    )  # fmt: skip


def webp_photo() -> bytes:
    return ffmpeg_bytes(
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=1", "-frames:v", "1",
        "-c:v", "libwebp", "-f", "webp",
    )  # fmt: skip


def probe(data: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        f.write(data)
        f.flush()
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height", "-of", "json", f.name],
            check=True, capture_output=True,
        ).stdout  # fmt: skip
    info = json.loads(out)
    streams = info["streams"]
    video = next(s for s in streams if s["codec_type"] == "video")
    return {
        "seconds": float(info["format"]["duration"]),
        "audio": any(s["codec_type"] == "audio" for s in streams),
        "size": (video["width"], video["height"]),
    }


def lines_every(ms: int, count: int) -> list[Line]:
    return [Line(i * ms, (i + 1) * ms, f"سطر {i}.", f"Line {i}.") for i in range(count)]


# --- planning ---


def test_shots_cut_at_line_boundaries_within_the_longest_shot():
    kept, shots = plan_shots(lines_every(4000, 5), max_shot_seconds=15, max_total_seconds=60)
    assert len(kept) == 5
    # Cuts fall where a line starts (in video time, after the lead-in), never past 15 s. The
    # last shot ends with the last word: the tail is the held last frame, not asked for.
    assert shots == [
        Shot(0, 12000 + LEAD_MS, 13, (0, 1, 2)),
        Shot(12000 + LEAD_MS, 20000 + LEAD_MS, 8, (3, 4)),
    ]


def test_a_minute_of_soundtrack_becomes_contiguous_shots_of_at_most_15_seconds():
    kept, shots = plan_shots(lines_every(4000, 20), max_shot_seconds=15, max_total_seconds=60)
    # Whole lines only: the last kept line must end, with lead-in and tail, within 60 s.
    assert kept[-1].end_ms + LEAD_MS + TAIL_MS <= 60_000
    assert len(kept) == 14
    assert shots[0].start_ms == 0
    assert shots[-1].end_ms == kept[-1].end_ms + LEAD_MS
    for before, after in zip(shots, shots[1:], strict=False):
        assert before.end_ms == after.start_ms
        assert after.start_ms - LEAD_MS in {line.start_ms for line in kept}
    assert all(shot.end_ms - shot.start_ms <= 15_000 for shot in shots)
    assert all(3 <= shot.seconds <= 15 for shot in shots)
    assert sorted({i for shot in shots for i in shot.lines}) == list(range(14))


def test_a_line_longer_than_a_shot_is_split_evenly():
    lines = [Line(0, 20000, "طويل", "Long."), Line(20000, 24000, "قصير", "Short.")]
    _, shots = plan_shots(lines, max_shot_seconds=15, max_total_seconds=60)
    first_cut = 20000 + LEAD_MS
    assert shots == [
        Shot(0, first_cut // 2, 11, (0,)),
        Shot(first_cut // 2, first_cut, 11, (0,)),
        Shot(first_cut, 24000 + LEAD_MS, 4, (1,)),
    ]


def test_a_short_last_shot_still_asks_for_the_shortest_length():
    lines = [Line(0, 14500, "أ", "A."), Line(14500, 15000, "ب", "B.")]
    _, shots = plan_shots(lines, max_shot_seconds=15, max_total_seconds=60)
    assert shots[-1].end_ms - shots[-1].start_ms < 3000
    assert shots[-1].seconds == 3


def test_a_soundtrack_that_does_not_fit_at_all_is_refused():
    with pytest.raises(UserFacingError, match="longer"):
        plan_shots([Line(0, 70_000, "طويل", "Long.")], max_shot_seconds=15, max_total_seconds=60)


def test_each_shot_prompt_carries_its_words_and_the_continuity():
    first = shot_prompt(0, 4, "Petra at dawn", "Petra", "They carved the facade.", "Slow pan")
    later = shot_prompt(1, 4, "Petra at dawn", "Petra", "They were masters of water.", "Slow pan")
    assert "Shot 1 of 4" in first and "photo" in first
    assert "Shot 2 of 4" in later and "previous shot" in later
    assert "even when the scene moves" in later
    assert "They were masters of water." in later and "Slow pan" in later
    assert "Petra at dawn" in later
    assert "No one speaks" in later


# --- subtitles ---


def test_subtitles_put_the_spoken_arabic_above_its_english():
    ass = subtitles(lines_every(4000, 2), 1280, 720, rtl=True)
    assert "PlayResX: 1280" in ass and "PlayResY: 720" in ass
    (first,) = [row for row in ass.splitlines() if row.startswith("Dialogue: 0,0:00:00.30,")]
    assert first.startswith("Dialogue: 0,0:00:00.30,0:00:04.30,")
    # A right-to-left embedding keeps the Arabic word order and its closing full stop right,
    # even with Latin words inside.
    assert "\u202bسطر 0.\u202c" in first
    assert first.index("سطر 0.") < first.index("\\N") < first.index("Line 0.")


def test_english_stories_get_one_subtitle_line():
    lines = [Line(0, 3000, "The well was ours.", None)]
    ass = subtitles(lines, 720, 1280, rtl=False)
    (row,) = [r for r in ass.splitlines() if r.startswith("Dialogue:")]
    assert "\\N" not in row and "\u202b" not in row
    assert "The well was ours." in row
    assert "PlayResX: 720" in ass and "PlayResY: 1280" in ass


def test_subtitle_text_cannot_carry_formatting_codes():
    ass = subtitles([Line(0, 3000, "a {\\b1}x\\Ny", None)], 1280, 720, rtl=False)
    (row,) = [r for r in ass.splitlines() if r.startswith("Dialogue:")]
    assert "{\\b1}" not in row and "x\\Ny" not in row
    assert "(/b1)x/Ny" in row


# --- spending ---


async def test_room_check_refuses_what_would_pass_a_cap(sessionmaker):
    async with sessionmaker() as session:
        session.add(
            SpendEntry(
                provider="earlier",
                operation="video_submit",
                budget="card",
                estimated_usd=Decimal("9"),
                actual_usd=Decimal("9"),
                state="committed",
            )
        )
        await session.commit()
    await gateway.check_room("card", Decimal("0.5"))
    with pytest.raises(gateway.SpendingLimit, match="daily"):
        await gateway.check_room("card", Decimal("2"))
    with pytest.raises(gateway.SpendingLimit, match="total"):
        await gateway.check_room("card", Decimal("17"))
    with pytest.raises(gateway.SpendingLimit, match="Azure"):
        await gateway.check_room("azure", Decimal("51"))
    async with sessionmaker() as session:
        # A check reserves nothing.
        assert len((await session.execute(select(SpendEntry))).scalars().all()) == 1


# --- through the API and the worker ---


class FakeGoogle:
    """Answers the Interactions API: each submission renders on the second check, as a real
    clip of the length asked for. Interactions in `fail` end as failed, those in `unknown`
    answer their first check with a status nobody knows; `refuse_submit` answers submissions
    with 503 (outcome unknown), `refuse_status` with that 4xx (refused outright)."""

    def __init__(
        self,
        fail: set[str] | None = None,
        refuse_submit: bool = False,
        unknown: set[str] | None = None,
        refuse_status: int | None = None,
        script: dict | None = None,
    ):
        self.posts: list[dict] = []
        self.script_posts: list[dict] = []
        self.order: list[str] = []
        self.script = script
        self.checks: dict[str, int] = {}
        self.lengths: dict[str, int] = {}
        self.fail = fail or set()
        self.refuse_submit = refuse_submit
        self.unknown = set(unknown or ())
        self.refuse_status = refuse_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and not json.loads(request.content)["model"].startswith(
            "gemini-omni"
        ):
            # The screenwriter (a Gemini text model) answers at once.
            self.script_posts.append(json.loads(request.content))
            self.order.append("script")
            text = json.dumps(self.script)
            steps = [{"type": "model_output", "content": [{"type": "text", "text": text}]}]
            return httpx.Response(
                200, json={"id": "v1_script", "status": "completed", "steps": steps}
            )
        if request.method == "POST":
            self.order.append("video")
            if self.refuse_submit:
                return httpx.Response(503)
            if self.refuse_status:
                error = {"code": self.refuse_status, "message": "no", "status": "REFUSED"}
                return httpx.Response(self.refuse_status, json=[{"error": error}])
            body = json.loads(request.content)
            self.posts.append(body)
            interaction = f"v1_shot{len(self.posts)}"
            self.lengths[interaction] = int(body["response_format"]["duration"].rstrip("s"))
            return httpx.Response(200, json={"id": interaction, "status": "in_progress"})
        interaction = request.url.path.rsplit("/", 1)[1]
        self.checks[interaction] = self.checks.get(interaction, 0) + 1
        if interaction in self.fail:
            return httpx.Response(200, json={"id": interaction, "status": "failed"})
        if interaction in self.unknown:
            self.unknown.discard(interaction)
            return httpx.Response(200, json={"id": interaction, "status": "something_new"})
        if self.checks[interaction] == 1:
            return httpx.Response(200, json={"id": interaction, "status": "in_progress"})
        video = base64.b64encode(clip(self.lengths[interaction])).decode()
        return httpx.Response(
            200,
            json={
                "id": interaction,
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "video", "mime_type": "video/mp4", "data": video}],
                    }
                ],
            },
        )


@pytest.fixture
def omni_live(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_ai_video", True)
    monkeypatch.setattr(settings, "live_ai_enabled", True)
    monkeypatch.setattr(settings, "gemini_api_key", "ai-studio-test-key")
    return settings


async def story_with_soundtrack(
    client,
    session,
    sessionmaker,
    monkeypatch,
    *,
    narration=True,
    recording=False,
    count=5,
    english=True,
    cloned=False,
):
    """A published Jordanian story with a photo, 4-second lines, an English translation and
    a narration and/or a recording."""
    user = await admin(client, sessionmaker)
    story = Story(
        author_id=uuid.UUID(user["id"]),
        title="Petra at dawn",
        place_name="Petra",
        status="published",
        published_at=datetime.now(UTC),
        original_language="jordanian",
    )
    session.add(story)
    await session.flush()
    storage = get_storage()
    lines = lines_every(4000, count)
    timed = [{"start_ms": x.start_ms, "end_ms": x.end_ms, "text": x.spoken} for x in lines]
    session.add(TextLayer(story_id=story.id, kind="polished", language="jordanian", segments=timed))
    if english:
        session.add(
            TextLayer(
                story_id=story.id,
                kind="translation_en",
                language="english",
                segments=[
                    {"start_ms": x.start_ms, "end_ms": x.end_ms, "text": x.english} for x in lines
                ],
            )
        )
    clone = None
    if cloned:
        clone = VoiceClone(
            id=uuid.uuid4(),
            actor_id=uuid.UUID(user["id"]),
            request_id="clone-test",
            speaker_name="Salma",
            consent={"speaker_confirmed": True},
            sample_key="voices/test/sample.mp3",
            sample_hash="test",
            duration_ms=30_000,
            provider="fake",
            provider_voice_id="demo-consenting-voice",
        )
        session.add(clone)
        await session.flush()
    if narration:
        key = f"stories/{story.id}/narration/test.mp3"
        storage.write_bytes(key, tone(count * 4))
        asset = Asset(
            story_id=story.id,
            kind="narration",
            storage_key=key,
            content_type="audio/mpeg",
            size_bytes=storage.size(key),
        )
        session.add(asset)
        await session.flush()
        session.add(
            Narration(
                story_id=story.id,
                asset_id=asset.id,
                provider="elevenlabs",
                voice="voice-ar",
                language="jordanian",
                source="polished",
                timing="alignment",
                segments=timed,
                input_hash="test",
                voice_clone_id=clone.id if clone else None,
            )
        )
    if recording:
        key = f"stories/{story.id}/audio/test.mp3"
        storage.write_bytes(key, tone(count * 4))
        session.add(
            Asset(
                story_id=story.id,
                kind="audio",
                storage_key=key,
                content_type="audio/mpeg",
                size_bytes=storage.size(key),
            )
        )
    await session.commit()
    photo_key = f"test-narrated/{story.id}/photo.webp"
    storage.write_bytes(photo_key, webp_photo())

    async def one_photo(session, story):
        return [photo_key]

    monkeypatch.setattr(photos, "slideshow_images", one_photo)
    return story


def narrated(story, provider="gemini_omni", **extra) -> dict:
    return {
        "story_id": str(story.id),
        "provider": provider,
        "model": "gemini-omni-1.2-flash" if provider == "gemini_omni" else "demo",
        "prompt": "Golden hour light on the stone",
        "aspect_ratio": "16:9",
        "seed": 1,
        "mode": "narrated",
        **extra,
    }


async def ledger(session, provider="gemini_omni") -> list[Decimal]:
    session.expire_all()
    rows = await session.execute(
        select(SpendEntry)
        .where(SpendEntry.provider == provider, SpendEntry.state == "committed")
        .order_by(SpendEntry.created_at)
    )
    return [row.actual_usd for row in rows.scalars()]


async def test_the_plan_is_shown_before_anything_is_queued(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    response = await client.post("/api/v1/staff/videos/plan", json=narrated(story))
    assert response.status_code == 200, response.text
    shown = response.json()
    assert [(shot["seconds"], shot["lines"]) for shot in shown["shots"]] == [(13, 3), (8, 2)]
    assert shown["seconds"] == pytest.approx(20.9)
    assert (shown["lines"], shown["lines_total"]) == (5, 5)
    assert Decimal(shown["estimate_usd"]) == Decimal("1.68")  # (13 + 8) s at 0.08
    assert shown["english"] is True
    assert (await session.execute(select(VideoGeneration))).scalars().all() == []


async def test_a_narrated_video_is_chained_joined_voiced_and_subtitled(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    google = FakeGoogle()
    mock_http(monkeypatch, google)
    response = await client.post("/api/v1/staff/videos", json=narrated(story))
    assert response.status_code == 202, response.text
    queued = response.json()
    assert (queued["mode"], queued["shots"]) == ("narrated", 2)

    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{queued['id']}")).json()
    assert done["status"] == "done", done

    # Two shots, one after another: the first from the story photo, the second from the
    # frame where the first is cut, each asking for its own length.
    first, second = google.posts
    assert [p["response_format"]["duration"] for p in google.posts] == ["13s", "8s"]
    photo = (await photos.slideshow_images(None, story))[0]
    assert base64.b64decode(first["input"][0]["data"]) == get_storage().path(photo).read_bytes()
    chained = base64.b64decode(second["input"][0]["data"])
    assert chained[:4] == b"RIFF" and chained[8:12] == b"WEBP"
    assert chained != base64.b64decode(first["input"][0]["data"])
    assert "Shot 1 of 2" in first["input"][1]["text"]
    assert "Line 0." in first["input"][1]["text"] and "Line 3." not in first["input"][1]["text"]
    # One image per shot: Omni reads a second image as the shot's last frame (seen live), so
    # the people's look is carried by the opening frame and the prompt, not a reference.
    assert len(first["input"]) == 2 and len(second["input"]) == 2
    prompt = second["input"][1]["text"]
    assert "Shot 2 of 2" in prompt and "same faces, hair and clothes" in prompt
    assert "Line 3." in prompt and "Line 4." in prompt

    media = await client.get(done["video_url"])
    assert media.headers["content-type"] == "video/mp4"
    video = probe(media.content)
    assert video["seconds"] == pytest.approx(20.9, abs=0.15)
    assert video["audio"] is True
    assert video["size"] == (1280, 720)
    # Only the soundtrack is heard. The provider's clips carry a loud 3 kHz tone (Omni always
    # makes its own sound, voices included); the narration is a 220 Hz tone.
    assert band_loudness(media.content, 220, 2.0, 16.0) > -40
    assert band_loudness(media.content, 3000, 2.0, 16.0) < -70
    assert loudness(media.content, 0.0, 0.25) < -70  # the lead-in is silent
    assert loudness(media.content, 20.4, 0.45) < -70  # and so is the tail

    generation = await session.get(VideoGeneration, uuid.UUID(queued["id"]))
    await session.refresh(generation)
    folder = f"stories/{story.id}/videos/{generation.id}"
    captions = get_storage().path(f"{folder}/subtitles.ass").read_text(encoding="utf-8")
    assert "Line 4." in captions and "سطر 4." in captions
    assert await ledger(session) == [Decimal("1.04"), Decimal("0.64")]


async def test_a_rehearsal_with_the_fake_provider_needs_no_keys(
    client, session, sessionmaker, monkeypatch
):
    monkeypatch.setattr(get_settings(), "enable_ai_video", True)
    story = await story_with_soundtrack(
        client, session, sessionmaker, monkeypatch, narration=False, recording=True
    )
    response = await client.post(
        "/api/v1/staff/videos",
        json=narrated(story, provider="fake", soundtrack="recording", aspect_ratio="9:16"),
    )
    assert response.status_code == 202, response.text
    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{response.json()['id']}")).json()
    assert done["status"] == "done", done
    media = await client.get(done["video_url"])
    assert media.headers["content-type"] == "video/mp4"
    video = probe(media.content)
    # The demo clip is silent and 6 s long; the result still carries the recording and
    # lasts as long as it.
    assert video["audio"] is True
    assert video["seconds"] == pytest.approx(20.9, abs=0.15)
    assert video["size"] == (720, 1280)
    assert await ledger(session, "fake") == []


async def test_a_failed_shot_is_retried_without_redoing_finished_ones(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    google = FakeGoogle(fail={"v1_shot2"})
    mock_http(monkeypatch, google)
    generation_id = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()["id"]
    await drain(sessionmaker)
    failed = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert failed["status"] == "failed"
    assert "Gemini Omni could not generate" in failed["error"]
    assert failed["retryable"] is True

    retried = await client.post(f"/api/v1/staff/videos/{generation_id}/retry")
    assert retried.status_code == 202, retried.text
    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert done["status"] == "done", done
    # Shot 1 was not made again; shot 2 was submitted once more as a new paid attempt.
    assert len(google.posts) == 3
    assert google.posts[1]["input"][0] == google.posts[2]["input"][0]
    assert await ledger(session) == [Decimal("1.04"), Decimal("0.64"), Decimal("0.64")]


async def test_an_uncertain_shot_submission_is_not_retried(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    mock_http(monkeypatch, FakeGoogle(refuse_submit=True))
    generation_id = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()["id"]
    await drain(sessionmaker)
    failed = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert failed["status"] == "failed"
    assert "could not be confirmed" in failed["error"]
    assert failed["retryable"] is False and failed["needs_confirmation"] is True
    assert (await client.post(f"/api/v1/staff/videos/{generation_id}/retry")).status_code == 409
    # The uncertain submission stays counted: Google may have started (and billed) it.
    assert await ledger(session) == [Decimal("1.04")]


async def test_the_whole_video_must_fit_the_budget_before_anything_starts(
    client, session, sessionmaker, monkeypatch, omni_live
):
    monkeypatch.setattr(omni_live, "spend_cap_usd_total", 1.0)
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    response = await client.post("/api/v1/staff/videos", json=narrated(story))
    assert response.status_code == 422
    assert "spending limit" in response.json()["detail"]
    assert (await session.execute(select(VideoGeneration))).scalars().all() == []


async def test_a_narrated_video_needs_its_soundtrack(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch, narration=False)
    response = await client.post("/api/v1/staff/videos/plan", json=narrated(story))
    assert response.status_code == 422
    assert "narration" in response.json()["detail"]
    response = await client.post(
        "/api/v1/staff/videos/plan", json=narrated(story, soundtrack="recording")
    )
    assert response.status_code == 422
    assert "recording" in response.json()["detail"]


async def test_fixed_length_providers_are_not_offered_for_narrated_videos(
    client, session, sessionmaker, monkeypatch, omni_live
):
    monkeypatch.setattr(omni_live, "fal_key", "fal-test-key")
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    body = {**narrated(story, provider="fal"), "model": "fal-ai/wan/v2.2-a14b/image-to-video"}
    response = await client.post("/api/v1/staff/videos", json=body)
    assert response.status_code == 422
    assert "narrated" in response.json()["detail"]
    config = (await client.get("/api/v1/staff/videos/config")).json()
    shots = {item["id"]: item.get("max_shot_seconds") for item in config["providers"]}
    assert shots["gemini_omni"] == 15 and shots["fake"] == 15 and shots["fal"] is None
    assert config["narrated_max_seconds"] == 60


def loudness(data: bytes, start: float, seconds: float, band: str = "") -> float:
    """Mean volume in dB of a stretch of a video's sound (-inf for digital silence)."""
    with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
        f.write(data)
        f.flush()
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(seconds), "-i", f.name,
             "-vn", "-af", f"{band}volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        ).stderr  # fmt: skip
    found = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", out)
    return float(found.group(1)) if found else float("-inf")


def band_loudness(data: bytes, hertz: int, start: float, seconds: float) -> float:
    """Mean volume in dB of one narrow band of frequencies around `hertz` (three band-pass
    filters in a row, so a loud tone elsewhere does not leak in)."""
    return loudness(data, start, seconds, f"bandpass=f={hertz}:width_type=h:w=100," * 3)


async def test_the_voice_stops_at_the_last_line_the_video_covers(
    client, session, sessionmaker, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_ai_video", True)
    monkeypatch.setattr(settings, "narrated_video_max_seconds", 10)
    # 20 s of narration, but only the first two 4-second lines fit in 10 s.
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    queued = await client.post("/api/v1/staff/videos", json=narrated(story, provider="fake"))
    assert queued.json()["seconds"] == pytest.approx(8000 / 1000 + (LEAD_MS + TAIL_MS) / 1000)
    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{queued.json()['id']}")).json()
    media = (await client.get(done["video_url"])).content
    assert probe(media)["seconds"] == pytest.approx(8.9, abs=0.15)
    # The demo clips are silent, so what is heard is the voice: there while the two lines
    # play, gone after the second line ends at 8.3 s (the third line is never heard).
    assert loudness(media, 1.0, 6.0) > -40
    assert loudness(media, 8.45, 0.4) < -70


async def test_a_check_that_fails_for_another_reason_is_checked_again_not_paid_twice(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    google = FakeGoogle(unknown={"v1_shot2"})
    mock_http(monkeypatch, google)
    generation_id = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()["id"]
    await drain(sessionmaker)
    failed = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert failed["status"] == "failed" and failed["retryable"] is True
    assert (await client.post(f"/api/v1/staff/videos/{generation_id}/retry")).status_code == 202
    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert done["status"] == "done", done
    # Shot 2 was asked about again, not submitted again.
    assert len(google.posts) == 2
    assert await ledger(session) == [Decimal("1.04"), Decimal("0.64")]


async def test_an_uncertain_shot_is_submitted_again_only_when_staff_confirm(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    google = FakeGoogle(refuse_submit=True)
    mock_http(monkeypatch, google)
    generation_id = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()["id"]
    await drain(sessionmaker)
    url = f"/api/v1/staff/videos/{generation_id}/retry"
    assert (await client.post(url)).status_code == 409
    google.refuse_submit = False
    confirmed = await client.post(url, json={"confirm_resubmit": True})
    assert confirmed.status_code == 202, confirmed.text
    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert done["status"] == "done", done
    # The unknown first submission stays counted; the confirmed one is a new paid attempt.
    assert await ledger(session) == [Decimal("1.04"), Decimal("1.04"), Decimal("0.64")]


async def test_a_shot_refused_outright_is_released_not_counted(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    mock_http(monkeypatch, FakeGoogle(refuse_status=429))
    generation_id = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()["id"]
    await drain(sessionmaker)
    failed = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert failed["status"] == "failed" and "paid tier" in failed["error"]
    assert failed["retryable"] is True and failed["needs_confirmation"] is False
    assert await ledger(session) == []
    session.expire_all()
    (released,) = (await session.execute(select(SpendEntry))).scalars().all()
    assert released.state == "released"


async def test_a_retry_needs_room_for_the_shots_still_to_make(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    mock_http(monkeypatch, FakeGoogle(fail={"v1_shot2"}))
    generation_id = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()["id"]
    await drain(sessionmaker)
    # 1.68 USD spent; shot 2 again needs 0.64 more, which a 2 USD total cap cannot take.
    monkeypatch.setattr(omni_live, "spend_cap_usd_total", 2.0)
    response = await client.post(f"/api/v1/staff/videos/{generation_id}/retry")
    assert response.status_code == 422
    assert "spending limit" in response.json()["detail"]
    still = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert still["status"] == "failed"


async def test_revoking_the_narrators_voice_removes_the_narrated_video(
    client, session, sessionmaker, monkeypatch
):
    monkeypatch.setattr(get_settings(), "enable_ai_video", True)
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch, cloned=True)
    generation_id = (
        await client.post("/api/v1/staff/videos", json=narrated(story, provider="fake"))
    ).json()["id"]
    await drain(sessionmaker)
    assert (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()["status"] == "done"
    folder = f"stories/{story.id}/videos/{generation_id}"
    assert get_storage().exists(f"{folder}/result.mp4")

    clone_id = (
        await session.execute(
            select(Narration.voice_clone_id).where(Narration.story_id == story.id)
        )
    ).scalar_one()
    assert (await client.post(f"/api/v1/staff/voices/{clone_id}/revoke")).status_code == 200
    removed = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert removed["video_url"] is None
    assert removed["progress"] == "Removed: the narrator's voice was revoked"
    assert removed["retryable"] is False
    assert not get_storage().exists(f"{folder}/result.mp4")
    assert not get_storage().exists(f"{folder}/soundtrack.mp3")
    assert (await client.get(f"/api/v1/staff/videos/{generation_id}/media")).status_code == 404


async def test_renaming_the_story_makes_a_new_video_request(
    client, session, sessionmaker, monkeypatch
):
    monkeypatch.setattr(get_settings(), "enable_ai_video", True)
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    body = narrated(story, provider="fake")
    first = (await client.post("/api/v1/staff/videos", json=body)).json()["id"]
    assert (await client.post("/api/v1/staff/videos", json=body)).json()["id"] == first
    story.title = "Petra at dusk"
    await session.commit()
    # The shots' prompts name the story, so a rename is a new request, not the old video.
    assert (await client.post("/api/v1/staff/videos", json=body)).json()["id"] != first


async def test_progress_is_a_fixed_message_with_the_shot_number(
    client, session, sessionmaker, monkeypatch, omni_live
):
    from app.worker import run_one

    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    mock_http(monkeypatch, FakeGoogle())
    generation_id = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()["id"]
    assert await run_one(sessionmaker)  # submits shot 1
    shown = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert (shown["progress"], shown["shot"], shown["shots"]) == ("Rendering a shot", 1, 2)
    await drain(sessionmaker)
    shown = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert (shown["progress"], shown["shot"]) == ("Video ready", None)


async def test_without_an_english_translation_the_plan_says_so(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch, english=False)
    shown = (await client.post("/api/v1/staff/videos/plan", json=narrated(story))).json()
    assert shown["english"] is False
    assert len(shown["shots"]) == 2


SCRIPT_FOR_TWO = {
    "cast": "The guide: a man in his fifties, grey moustache, dark robe, red keffiyeh.",
    "setting": "The Siq at first light, walking towards the Treasury.",
    "narrator": "A warm older Jordanian man.",
    "shots": [
        {
            "action": "The guide walks into the Siq past the carved water channel.",
            "camera": "Slow tracking shot behind him.",
            "sound": "Sandals on stone, a light wind.",
        },
        {
            "action": "He reaches the end of the Siq as the Treasury appears.",
            "camera": "The camera rises over his shoulder.",
            "sound": "Footsteps slowing on sand, distant birds.",
        },
    ],
}


async def test_a_refined_script_shapes_every_shot(
    client, session, sessionmaker, monkeypatch, omni_live
):
    monkeypatch.setattr(omni_live, "script_provider", "gemini")
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    google = FakeGoogle(script=SCRIPT_FOR_TWO)
    mock_http(monkeypatch, google)
    shown = (await client.post("/api/v1/staff/videos/plan", json=narrated(story))).json()
    assert shown["script"] == "gemini"
    assert Decimal(shown["estimate_usd"]) > Decimal("1.68")  # the shots plus the script
    generation_id = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()["id"]
    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert done["status"] == "done", done
    # The script is written once, before any shot is paid for.
    assert google.order == ["script", "video", "video"]
    (asked,) = google.script_posts
    assert "Line 0." in asked["input"][-1]["text"] and "Line 4." in asked["input"][-1]["text"]
    first, second = (post["input"][1]["text"] for post in google.posts)
    for prompt, scene in zip((first, second), SCRIPT_FOR_TWO["shots"], strict=True):
        assert SCRIPT_FOR_TWO["cast"] in prompt and SCRIPT_FOR_TWO["setting"] in prompt
        assert scene["action"] in prompt and scene["camera"] in prompt
    assert done["script"]["shots"][1]["action"] == SCRIPT_FOR_TWO["shots"][1]["action"]
    assert len(await ledger(session, "gemini_script")) == 1


async def test_omni_voice_keeps_the_shots_own_sound(
    client, session, sessionmaker, monkeypatch, omni_live
):
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)
    google = FakeGoogle()
    mock_http(monkeypatch, google)
    body = narrated(story, audio="omni")
    generation_id = (await client.post("/api/v1/staff/videos", json=body)).json()["id"]
    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert (done["status"], done["audio"]) == ("done", "omni")
    media = (await client.get(done["video_url"])).content
    # Omni's own sound (the clips' 3 kHz tone) is kept; the ElevenLabs narration is not laid on.
    assert band_loudness(media, 3000, 2.0, 16.0) > -40
    assert band_loudness(media, 220, 2.0, 16.0) < -60
    # Each shot asks Omni for a voice-over of its own words, in the story's language.
    prompt = google.posts[0]["input"][1]["text"]
    assert "voice-over" in prompt and "Jordanian Arabic" in prompt
    assert "سطر 0." in prompt and "سطر 3." not in prompt


async def test_the_default_voice_is_a_setting(
    client, session, sessionmaker, monkeypatch, omni_live
):
    monkeypatch.setattr(omni_live, "narrated_video_audio", "omni")
    story = await story_with_soundtrack(client, session, sessionmaker, monkeypatch)  # signs in
    config = (await client.get("/api/v1/staff/videos/config")).json()
    assert (config["narrated_audio"], config["script_provider"]) == ("omni", "fake")
    mock_http(monkeypatch, FakeGoogle())
    queued = (await client.post("/api/v1/staff/videos", json=narrated(story))).json()
    assert queued["audio"] == "omni"
