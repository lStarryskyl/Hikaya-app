"""Narrated AI videos: shots planned from the story's soundtrack, chained by their last frame,
joined, voiced and subtitled (docs/DECISIONS.md, "Narrated AI videos").

The provider's HTTP is mocked; FFmpeg runs for real on generated clips, so the joining,
timing, audio and subtitles are the real thing.
"""

import base64
import json
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
from app.models import Asset, Narration, SpendEntry, Story, TextLayer, VideoGeneration
from app.narrated_video import LEAD_MS, TAIL_MS, Line, Shot, plan, shot_prompt, subtitles
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
    """A small MP4 with picture and sound, as a provider would return."""
    return ffmpeg_bytes(
        "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=24:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}",
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
    kept, shots = plan(lines_every(4000, 5), max_shot_seconds=15, max_total_seconds=60)
    assert len(kept) == 5
    total = 20000 + LEAD_MS + TAIL_MS
    # Cuts fall where a line starts (in video time, after the lead-in), never past 15 s.
    assert shots == [
        Shot(0, 12000 + LEAD_MS, 13, (0, 1, 2)),
        Shot(12000 + LEAD_MS, total, 9, (3, 4)),
    ]


def test_a_minute_of_soundtrack_becomes_contiguous_shots_of_at_most_15_seconds():
    kept, shots = plan(lines_every(4000, 20), max_shot_seconds=15, max_total_seconds=60)
    # Whole lines only: the last kept line must end, with lead-in and tail, within 60 s.
    assert kept[-1].end_ms + LEAD_MS + TAIL_MS <= 60_000
    assert len(kept) == 14
    assert shots[0].start_ms == 0
    assert shots[-1].end_ms == kept[-1].end_ms + LEAD_MS + TAIL_MS
    for before, after in zip(shots, shots[1:], strict=False):
        assert before.end_ms == after.start_ms
        assert after.start_ms - LEAD_MS in {line.start_ms for line in kept}
    assert all(shot.end_ms - shot.start_ms <= 15_000 for shot in shots)
    assert all(3 <= shot.seconds <= 15 for shot in shots)
    assert sorted({i for shot in shots for i in shot.lines}) == list(range(14))


def test_a_line_longer_than_a_shot_is_split_evenly():
    lines = [Line(0, 20000, "طويل", "Long."), Line(20000, 24000, "قصير", "Short.")]
    _, shots = plan(lines, max_shot_seconds=15, max_total_seconds=60)
    first_cut = 20000 + LEAD_MS
    assert shots == [
        Shot(0, first_cut // 2, 11, (0,)),
        Shot(first_cut // 2, first_cut, 11, (0,)),
        Shot(first_cut, 24000 + LEAD_MS + TAIL_MS, 5, (1,)),
    ]


def test_a_short_last_shot_still_asks_for_the_shortest_length():
    lines = [Line(0, 14000, "أ", "A."), Line(14000, 14500, "ب", "B.")]
    _, shots = plan(lines, max_shot_seconds=15, max_total_seconds=60)
    assert shots[-1].end_ms - shots[-1].start_ms < 3000
    assert shots[-1].seconds == 3


def test_a_soundtrack_that_does_not_fit_at_all_is_refused():
    with pytest.raises(UserFacingError, match="longer"):
        plan([Line(0, 70_000, "طويل", "Long.")], max_shot_seconds=15, max_total_seconds=60)


def test_each_shot_prompt_carries_its_words_and_the_continuity():
    first = shot_prompt(0, 4, "Petra at dawn", "Petra", "They carved the facade.", "Slow pan")
    later = shot_prompt(1, 4, "Petra at dawn", "Petra", "They were masters of water.", "Slow pan")
    assert "Shot 1 of 4" in first and "photo" in first
    assert "Shot 2 of 4" in later and "previous shot" in later
    assert "They were masters of water." in later and "Slow pan" in later
    assert "Petra at dawn" in later
    assert "No one speaks" in later


# --- subtitles ---


def test_subtitles_put_the_spoken_arabic_above_its_english():
    ass = subtitles(lines_every(4000, 2), 1280, 720, rtl=True)
    assert "PlayResX: 1280" in ass and "PlayResY: 720" in ass
    (first,) = [row for row in ass.splitlines() if row.startswith("Dialogue: 0,0:00:00.30,")]
    assert first.startswith("Dialogue: 0,0:00:00.30,0:00:04.30,")
    # Right-to-left marks keep the Arabic full stop at the end of the right-to-left line.
    assert "‏سطر 0.‏" in first
    assert first.index("سطر 0.") < first.index("\\N") < first.index("Line 0.")


def test_english_stories_get_one_subtitle_line():
    lines = [Line(0, 3000, "The well was ours.", None)]
    ass = subtitles(lines, 720, 1280, rtl=False)
    (row,) = [r for r in ass.splitlines() if r.startswith("Dialogue:")]
    assert "\\N" not in row and "‏" not in row
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
    clip of the length asked for. Interactions in `fail` end as failed; `refuse_submit`
    answers submissions with 503."""

    def __init__(self, fail: set[str] | None = None, refuse_submit: bool = False):
        self.posts: list[dict] = []
        self.checks: dict[str, int] = {}
        self.lengths: dict[str, int] = {}
        self.fail = fail or set()
        self.refuse_submit = refuse_submit

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            if self.refuse_submit:
                return httpx.Response(503)
            body = json.loads(request.content)
            self.posts.append(body)
            interaction = f"v1_shot{len(self.posts)}"
            self.lengths[interaction] = int(body["response_format"]["duration"].rstrip("s"))
            return httpx.Response(200, json={"id": interaction, "status": "in_progress"})
        interaction = request.url.path.rsplit("/", 1)[1]
        self.checks[interaction] = self.checks.get(interaction, 0) + 1
        if interaction in self.fail:
            return httpx.Response(200, json={"id": interaction, "status": "failed"})
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
    client, session, sessionmaker, monkeypatch, *, narration=True, recording=False, count=5
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
    english = [{"start_ms": x.start_ms, "end_ms": x.end_ms, "text": x.english} for x in lines]
    session.add(TextLayer(story_id=story.id, kind="polished", language="jordanian", segments=timed))
    session.add(
        TextLayer(story_id=story.id, kind="translation_en", language="english", segments=english)
    )
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
    assert [(shot["seconds"], shot["lines"]) for shot in shown["shots"]] == [(13, 3), (9, 2)]
    assert shown["seconds"] == pytest.approx(20.9)
    assert (shown["lines"], shown["lines_total"]) == (5, 5)
    assert Decimal(shown["estimate_usd"]) == Decimal("1.76")  # (13 + 9) s at 0.08
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
    assert [p["response_format"]["duration"] for p in google.posts] == ["13s", "9s"]
    photo = (await photos.slideshow_images(None, story))[0]
    assert base64.b64decode(first["input"][0]["data"]) == get_storage().path(photo).read_bytes()
    chained = base64.b64decode(second["input"][0]["data"])
    assert chained[:4] == b"RIFF" and chained[8:12] == b"WEBP"
    assert chained != base64.b64decode(first["input"][0]["data"])
    assert "Shot 1 of 2" in first["input"][1]["text"]
    assert "Line 0." in first["input"][1]["text"] and "Line 3." not in first["input"][1]["text"]
    assert "Shot 2 of 2" in second["input"][1]["text"]
    assert "Line 3." in second["input"][1]["text"] and "Line 4." in second["input"][1]["text"]

    media = await client.get(done["video_url"])
    assert media.headers["content-type"] == "video/mp4"
    video = probe(media.content)
    assert video["seconds"] == pytest.approx(20.9, abs=0.15)
    assert video["audio"] is True
    assert video["size"] == (1280, 720)

    generation = await session.get(VideoGeneration, uuid.UUID(queued["id"]))
    await session.refresh(generation)
    folder = f"stories/{story.id}/videos/{generation.id}"
    captions = get_storage().path(f"{folder}/subtitles.ass").read_text(encoding="utf-8")
    assert "Line 4." in captions and "سطر 4." in captions
    assert await ledger(session) == [Decimal("1.04"), Decimal("0.72")]


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
    assert await ledger(session) == [Decimal("1.04"), Decimal("0.72"), Decimal("0.72")]


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
    assert failed["retryable"] is False
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
