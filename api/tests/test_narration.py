"""Narration and the slideshow: queued on submit, made in the worker, shown once ready.

The slideshow carries the narration, so it follows it."""

import json
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import ProviderCacheEntry
from app.providers import fake
from tests.test_moderation import drain, edit, reject, sign_up, submit
from tests.test_story_photos import add_photo, make_image


@pytest.fixture(scope="session")
def tone(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("narration-audio") / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=6", "-ac", "1", str(path)],
        check=True,
    )
    return path


@pytest.fixture(scope="session")
def pictures(tmp_path_factory) -> list[Path]:
    folder = tmp_path_factory.mktemp("narration-photos")
    return [
        make_image(folder / "a.png", color="orange"),
        make_image(folder / "b.png", size="900x1400", color="teal"),
    ]


@pytest.fixture(autouse=True)
def fresh_fakes():
    fake.reset()
    yield
    fake.reset()


async def story_with_photo(client, sessionmaker, tone, pictures, language="jordanian"):
    story = (
        await client.post(
            "/api/v1/stories",
            json={
                "title": "The lantern",
                "category": "folklore",
                "place_name": "Madaba",
                "latitude": 31.7,
                "longitude": 35.8,
                "original_language": language,
            },
        )
    ).json()
    with open(tone, "rb") as f:
        await client.put(
            f"/api/v1/stories/{story['id']}/audio", files={"file": ("t.wav", f, "audio/wav")}
        )
    assert (await add_photo(client, story["id"], pictures[0])).status_code == 201
    await drain(sessionmaker)
    return story["id"]


async def publish(client, sessionmaker, story_id):
    r = await submit(client, story_id)
    assert r.status_code == 200, r.text
    await drain(sessionmaker)
    story = (await client.get(f"/api/v1/stories/{story_id}")).json()
    assert story["status"] == "published"
    return story


def layer(story, kind):
    return next(la for la in story["layers"] if la["kind"] == kind)


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
    ).stdout
    return json.loads(out)


async def media_file(client, url: str, tmp_path: Path, name: str) -> Path:
    r = await client.get(url)
    assert r.status_code == 200, url
    path = tmp_path / name
    path.write_bytes(r.content)
    return path


def speak_calls():
    return [c for c in fake.CALLS if c[0] == "speak"]


# --- narration ---


async def test_publishing_narrates_the_polished_text(client, sessionmaker, tone, pictures):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    story = await publish(client, sessionmaker, story_id)
    narration = story["narration"]
    polished = layer(story, "polished")
    assert narration["source"] == "polished"
    assert narration["language"] == "jordanian"
    assert narration["voice"]
    assert [s["text"] for s in narration["segments"]] == [s["text"] for s in polished["segments"]]
    r = await client.get(narration["url"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"


async def test_the_member_can_narrate_the_msa_translation(client, sessionmaker, tone, pictures):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    r = await client.patch(f"/api/v1/stories/{story_id}", json={"narration_source": "msa"})
    assert r.json()["narration_source"] == "msa"
    story = await publish(client, sessionmaker, story_id)
    msa = layer(story, "translation_msa")
    assert story["narration"]["source"] == "msa"
    assert story["narration"]["language"] == "msa"
    texts = [s["text"] for s in story["narration"]["segments"]]
    assert texts == [s["text"] for s in msa["segments"]]


async def test_an_unknown_narration_source_is_refused(client, sessionmaker, tone, pictures):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    r = await client.patch(f"/api/v1/stories/{story_id}", json={"narration_source": "english"})
    assert r.status_code == 422


async def test_alignment_data_gives_the_timings_in_one_call(
    client, sessionmaker, tone, pictures, tmp_path
):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    story = await publish(client, sessionmaker, story_id)
    narration = story["narration"]
    lines = len(narration["segments"])
    assert narration["timing"] == "alignment"
    assert speak_calls() == [("speak", "jordanian", narration["voice"], str(lines))]
    assert_contiguous(narration["segments"])
    audio = await media_file(client, narration["url"], tmp_path, "n.mp3")
    seconds = float(probe(audio)["format"]["duration"])
    assert abs(narration["segments"][-1]["end_ms"] - seconds * 1000) < 400


async def test_without_alignment_each_line_is_spoken_and_measured(
    client, sessionmaker, tone, pictures, tmp_path
):
    fake.TTS_ALIGNMENT[0] = False
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    story = await publish(client, sessionmaker, story_id)
    narration = story["narration"]
    lines = len(narration["segments"])
    assert narration["timing"] == "per_segment"
    assert lines > 1
    assert len(speak_calls()) == lines
    assert all(c[3] == "1" for c in speak_calls())
    assert_contiguous(narration["segments"])
    audio = await media_file(client, narration["url"], tmp_path, "n.mp3")
    seconds = float(probe(audio)["format"]["duration"])
    assert abs(narration["segments"][-1]["end_ms"] - seconds * 1000) < 400


def assert_contiguous(segments):
    assert segments[0]["start_ms"] == 0
    for a, b in zip(segments, segments[1:], strict=False):
        assert a["end_ms"] > a["start_ms"]
        assert b["start_ms"] == a["end_ms"]


async def test_speech_is_cached_as_a_file(client, sessionmaker, tone, pictures, session):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    await publish(client, sessionmaker, story_id)
    entries = (
        (
            await session.execute(
                select(ProviderCacheEntry).where(ProviderCacheEntry.operation == "speak")
            )
        )
        .scalars()
        .all()
    )
    assert entries and all(e.file_key for e in entries)
    root = Path(get_settings().media_dir)
    assert all((root / e.file_key).is_file() for e in entries)

    # The same text in another story is not spoken again.
    fake.CALLS.clear()
    await sign_up(client, "huda@example.com")
    other = await story_with_photo(client, sessionmaker, tone, pictures)
    await publish(client, sessionmaker, other)
    assert speak_calls() == []


async def test_a_failed_narration_does_not_stop_publishing_and_can_be_retried(
    client, sessionmaker, tone, pictures
):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    fake.FAIL_ON.add("speak")
    story = await publish(client, sessionmaker, story_id)
    assert story["narration"] is None
    steps = (await client.get(f"/api/v1/stories/{story_id}/pipeline")).json()["steps"]
    assert {s["step"]: s["status"] for s in steps}["narrate"] == "failed"

    fake.FAIL_ON.clear()
    r = await client.post(f"/api/v1/stories/{story_id}/pipeline/narrate/retry")
    assert r.status_code == 200, r.text
    await drain(sessionmaker)
    assert (await client.get(f"/api/v1/stories/{story_id}")).json()["narration"] is not None


# --- slideshow ---


async def test_the_slideshow_is_a_playable_mp4(client, sessionmaker, tone, pictures, tmp_path):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    await add_photo(client, story_id, pictures[1])
    story = await publish(client, sessionmaker, story_id)
    slideshow = story["slideshow"]
    assert slideshow["content_type"] == "video/mp4"
    video = await media_file(client, slideshow["url"], tmp_path, "s.mp4")
    info = probe(video)
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert "mp4" in info["format"]["format_name"]
    assert streams["video"]["codec_name"] == "h264"
    assert (streams["video"]["width"], streams["video"]["height"]) == (1280, 720)
    assert streams["video"]["pix_fmt"] == "yuv420p"
    assert streams["audio"]["codec_name"] == "aac"
    # The video carries the narration, so it lasts as long as the narration.
    narrated = story["narration"]["segments"][-1]["end_ms"] / 1000
    assert abs(float(info["format"]["duration"]) - narrated) < 0.5
    # Every frame decodes.
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"], capture_output=True
    )
    assert decoded.returncode == 0 and not decoded.stderr


async def test_a_story_without_any_picture_gets_no_slideshow(client, sessionmaker, tone):
    await sign_up(client)
    story = (
        await client.post(
            "/api/v1/stories",
            json={
                "title": "No photos",
                "category": "folklore",
                "original_language": "english",
                "place_name": "A village with no gallery",
                "latitude": 31.2,
                "longitude": 35.7,
            },
        )
    ).json()
    with open(tone, "rb") as f:
        await client.put(
            f"/api/v1/stories/{story['id']}/audio", files={"file": ("t.wav", f, "audio/wav")}
        )
    await drain(sessionmaker)
    published = await publish(client, sessionmaker, story["id"])
    assert published["slideshow"] is None
    assert published["narration"] is not None


# --- re-running only what changed ---


async def resubmit_after(client, sessionmaker, session, story_id, change):
    await reject(session, story_id, "One more change, please.")
    await change()
    await drain(sessionmaker)
    return await publish(client, sessionmaker, story_id)


async def test_editing_the_narrated_text_renarrates_and_remakes_the_slideshow(
    client, sessionmaker, session, tone, pictures
):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    before = await publish(client, sessionmaker, story_id)
    polished = layer(before, "polished")["segments"]
    texts = [s["text"] for s in polished]
    texts[0] = "سطر جديد."

    after = await resubmit_after(
        client, sessionmaker, session, story_id, lambda: edit_all(client, story_id, texts)
    )
    assert after["narration"]["url"] != before["narration"]["url"]
    assert after["narration"]["segments"][0]["text"] == "سطر جديد."
    assert after["slideshow"]["url"] != before["slideshow"]["url"]


async def edit_all(client, story_id, texts):
    r = await client.patch(f"/api/v1/stories/{story_id}/layers/polished", json={"texts": texts})
    assert r.status_code == 200, r.text


async def test_editing_text_that_is_not_narrated_changes_neither(
    client, sessionmaker, session, tone, pictures
):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    before = await publish(client, sessionmaker, story_id)
    fake.CALLS.clear()

    after = await resubmit_after(
        client,
        sessionmaker,
        session,
        story_id,
        lambda: edit(client, story_id, "translation_en", "A different English line."),
    )
    assert speak_calls() == []
    assert after["narration"]["url"] == before["narration"]["url"]
    assert after["slideshow"]["url"] == before["slideshow"]["url"]


async def test_changing_the_photos_rerenders_only_the_slideshow(
    client, sessionmaker, session, tone, pictures
):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    before = await publish(client, sessionmaker, story_id)

    after = await resubmit_after(
        client, sessionmaker, session, story_id, lambda: add_photo(client, story_id, pictures[1])
    )
    assert after["slideshow"]["url"] != before["slideshow"]["url"]
    assert after["narration"]["url"] == before["narration"]["url"]


async def test_switching_the_source_renarrates(client, sessionmaker, session, tone, pictures):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    before = await publish(client, sessionmaker, story_id)

    async def to_msa():
        await client.patch(f"/api/v1/stories/{story_id}", json={"narration_source": "msa"})

    after = await resubmit_after(client, sessionmaker, session, story_id, to_msa)
    assert before["narration"]["source"] == "polished"
    assert after["narration"]["source"] == "msa"
    # The replaced narration file is removed.
    old = await client.get(before["narration"]["url"])
    assert old.status_code == 404


async def test_a_cached_speech_file_that_went_missing_is_made_again(
    client, sessionmaker, tone, pictures, session
):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    await publish(client, sessionmaker, story_id)
    root = Path(get_settings().media_dir)
    for entry in (await session.execute(select(ProviderCacheEntry))).scalars():
        if entry.file_key:
            (root / entry.file_key).unlink()
    fake.CALLS.clear()
    await sign_up(client, "huda@example.com")
    other = await story_with_photo(client, sessionmaker, tone, pictures)
    story = await publish(client, sessionmaker, other)
    assert len(speak_calls()) == 1
    assert (await client.get(story["narration"]["url"])).status_code == 200


async def test_narration_starts_on_submit_alongside_the_check(client, sessionmaker, tone, pictures):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    await submit(client, story_id)
    steps = (await client.get(f"/api/v1/stories/{story_id}/pipeline")).json()["steps"]
    queued = {s["step"]: s["status"] for s in steps}
    assert queued["moderate"] == "queued"
    assert queued["narrate"] == "queued"
    # The slideshow carries the narration, so it waits for it.
    assert "slideshow" not in queued


async def test_a_held_story_is_narrated_too(client, sessionmaker, session, tone, pictures):
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    await edit(client, story_id, "translation_en", "A line about a weapon.")
    await submit(client, story_id)
    await drain(sessionmaker)
    story = (await client.get(f"/api/v1/stories/{story_id}")).json()
    assert story["status"] == "held"
    assert story["narration"] is not None and story["slideshow"] is not None


async def test_the_slideshow_carries_the_narration(client, sessionmaker, tone, pictures, tmp_path):
    fake.TTS_ALIGNMENT[0] = False  # line lengths differ from the recording's
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    story = await publish(client, sessionmaker, story_id)
    video = await media_file(client, story["slideshow"]["url"], tmp_path, "s.mp4")
    narration = await media_file(client, story["narration"]["url"], tmp_path, "n.mp3")
    video_s = float(probe(video)["format"]["duration"])
    assert abs(video_s - float(probe(narration)["format"]["duration"])) < 0.5
    assert abs(video_s - story["duration_ms"] / 1000) > 0.5


async def test_a_missing_photo_fails_the_slideshow_instead_of_dropping_it(
    client, sessionmaker, tone, pictures
):
    from app.storage import get_storage

    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    await add_photo(client, story_id, pictures[1])
    photo = (await client.get(f"/api/v1/stories/{story_id}")).json()["photos"][1]
    get_storage().delete(f"stories/{story_id}/photos/{uuid.UUID(photo['id']).hex}/1600.webp")
    await submit(client, story_id)
    await drain(sessionmaker)
    steps = (await client.get(f"/api/v1/stories/{story_id}/pipeline")).json()["steps"]
    assert {s["step"]: s["status"] for s in steps}["slideshow"] == "failed"


async def test_a_slideshow_is_remade_when_the_narration_returns_to_an_earlier_version(
    client, sessionmaker, session, tone, pictures
):
    # A -> B -> A: the first slideshow job runs again; it must use the current narration
    # file, not the one its first run used (that file was replaced and deleted).
    await sign_up(client)
    story_id = await story_with_photo(client, sessionmaker, tone, pictures)
    await publish(client, sessionmaker, story_id)

    async def source(value):
        await client.patch(f"/api/v1/stories/{story_id}", json={"narration_source": value})

    await resubmit_after(client, sessionmaker, session, story_id, lambda: source("msa"))
    back = await resubmit_after(client, sessionmaker, session, story_id, lambda: source("polished"))
    assert back["narration"]["source"] == "polished"
    assert back["slideshow"] is not None
    assert (await client.get(back["slideshow"]["url"])).status_code == 200
    steps = (await client.get(f"/api/v1/stories/{story_id}/pipeline")).json()["steps"]
    assert {s["step"]: s["status"] for s in steps}["slideshow"] == "done"
