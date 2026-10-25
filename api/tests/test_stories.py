import subprocess
from pathlib import Path

import pytest

from app.config import get_settings
from app.models import Role
from app.seed_staff import StaffSeed, seed_staff
from app.worker import run_one
from tests.conftest import CONSENT

PASSWORD = "correct horse battery"

COMPLETE = {
    "title": "The Loom of Ancestors",
    "category": "crafts",
    "place_name": "Madaba",
    "latitude": 31.7167,
    "longitude": 35.7939,
    "original_language": "jordanian",
}


@pytest.fixture(scope="session")
def tone(tmp_path_factory) -> Path:
    """A real 2-second recording, made with FFmpeg."""
    path = tmp_path_factory.mktemp("audio") / "tone.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ac",
            "1",
            str(path),
        ],
        check=True,
    )
    return path


async def sign_up(client, email):
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "display_name": email.split("@")[0]},
    )
    assert r.status_code == 201
    return client.cookies.get("hikaya_session")


def as_user(client, token):
    client.cookies.clear()
    if token:
        client.cookies.set("hikaya_session", token)


async def new_story(client, **fields):
    r = await client.post("/api/v1/stories", json=fields)
    assert r.status_code == 201, r.text
    return r.json()


async def upload(client, story_id, path, content_type="audio/wav"):
    with open(path, "rb") as f:
        return await client.put(
            f"/api/v1/stories/{story_id}/audio",
            files={"file": (Path(path).name, f, content_type)},
        )


async def published_story(client, tone, sessionmaker):
    story = await new_story(client, **COMPLETE)
    assert (await upload(client, story["id"], tone)).status_code == 200
    while await run_one(sessionmaker):  # the transcript must exist before publishing
        pass
    r = await client.post(f"/api/v1/stories/{story['id']}/submit", json=CONSENT)
    assert r.status_code == 200, r.text
    while await run_one(sessionmaker):  # the moderation check publishes it
        pass
    return (await client.get(f"/api/v1/stories/{story['id']}")).json()


# --- drafts ---


async def test_creating_a_story_needs_sign_in(client):
    assert (await client.post("/api/v1/stories", json={})).status_code == 401


async def test_member_creates_a_draft(client):
    await sign_up(client, "salma@example.com")
    story = await new_story(client, title="  Morning Steam  ")
    assert story["status"] == "draft"
    assert story["title"] == "Morning Steam"
    assert story["author"]["display_name"] == "salma"
    assert story["audio"] is None
    assert story["published_at"] is None


async def test_author_edits_a_draft(client):
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    r = await client.patch(f"/api/v1/stories/{story['id']}", json=COMPLETE)
    assert r.status_code == 200
    body = r.json()
    for key, value in COMPLETE.items():
        assert body[key] == value


@pytest.mark.parametrize(
    "bad",
    [
        {"category": "gossip"},
        {"original_language": "french"},
        {"latitude": 91},
        {"longitude": -181},
        {"title": "t" * 121},
        {"place_name": "p" * 121},
    ],
)
async def test_invalid_story_fields_are_refused(client, bad):
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    r = await client.patch(f"/api/v1/stories/{story['id']}", json=bad)
    assert r.status_code == 422


async def test_drafts_are_private_to_their_author_and_staff(client, sessionmaker):
    author = await sign_up(client, "salma@example.com")
    story = await new_story(client, title="Secret draft")
    path = f"/api/v1/stories/{story['id']}"

    as_user(client, None)
    assert (await client.get(path)).status_code == 404

    stranger = await sign_up(client, "other@example.com")
    as_user(client, stranger)
    assert (await client.get(path)).status_code == 404
    assert (await client.patch(path, json={"title": "Mine now"})).status_code == 404
    assert (await client.post(f"{path}/submit")).status_code == 404

    await seed_staff(
        sessionmaker, [StaffSeed("reviewer@example.com", PASSWORD, Role.REVIEWER, "Reviewer")]
    )
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/login", json={"email": "reviewer@example.com", "password": PASSWORD}
    )
    assert (await client.get(path)).status_code == 200
    # Staff can read a draft but not edit someone else's.
    assert (await client.patch(path, json={"title": "Staff edit"})).status_code == 404

    as_user(client, author)
    assert (await client.get(path)).json()["title"] == "Secret draft"


async def test_unknown_story_is_404(client):
    await sign_up(client, "salma@example.com")
    r = await client.get("/api/v1/stories/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert (await client.get("/api/v1/stories/not-a-uuid")).status_code == 404


# --- audio upload ---


async def test_uploading_audio_keeps_the_original_and_a_normalised_copy(client, tone):
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    r = await upload(client, story["id"], tone)
    assert r.status_code == 200, r.text
    body = r.json()
    assert 1800 <= body["duration_ms"] <= 2300
    audio = body["audio"]
    assert audio["content_type"] == "audio/mpeg"
    original = await client.get(audio["original_url"])
    assert original.status_code == 200
    assert original.content == tone.read_bytes()
    normalised = await client.get(audio["url"])
    assert normalised.status_code == 200
    assert normalised.headers["content-type"] == "audio/mpeg"
    assert len(normalised.content) > 1000


async def test_uploading_again_replaces_the_audio(client, tone):
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    first = (await upload(client, story["id"], tone)).json()["audio"]
    second = (await upload(client, story["id"], tone)).json()["audio"]
    assert first["url"] != second["url"]
    assert (await client.get(first["url"])).status_code == 404
    assert (await client.get(second["url"])).status_code == 200


async def test_non_audio_types_are_refused(client, tmp_path):
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    fake = tmp_path / "notes.txt"
    fake.write_text("hello")
    r = await upload(client, story["id"], fake, content_type="text/plain")
    assert r.status_code == 415


async def test_a_file_that_is_not_really_audio_is_refused(client, tmp_path):
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    fake = tmp_path / "fake.webm"
    fake.write_bytes(b"this is not audio at all" * 100)
    r = await upload(client, story["id"], fake, content_type="audio/webm;codecs=opus")
    assert r.status_code == 422
    assert (await client.get(f"/api/v1/stories/{story['id']}")).json()["audio"] is None


async def test_audio_over_the_size_limit_is_refused(client, tone, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_audio_upload_mb", 0.001)
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    r = await upload(client, story["id"], tone)
    assert r.status_code == 413
    assert (await client.get(f"/api/v1/stories/{story['id']}")).json()["audio"] is None


async def test_audio_over_the_length_limit_is_refused(client, tone, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_audio_minutes", 0.01)
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    assert (await upload(client, story["id"], tone)).status_code == 422


async def test_only_the_author_uploads_audio(client, tone):
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    await sign_up(client, "other@example.com")
    assert (await upload(client, story["id"], tone)).status_code == 404


# --- submitting and publishing ---


async def test_submitting_an_incomplete_story_lists_what_is_missing(client):
    await sign_up(client, "salma@example.com")
    story = await new_story(client, title="Only a title")
    r = await client.post(f"/api/v1/stories/{story['id']}/submit")
    assert r.status_code == 422
    detail = r.json()["detail"]
    for missing in ("category", "place", "map pin", "language", "audio", "transcript"):
        assert missing in detail


async def test_submitting_a_complete_story_publishes_it_for_everyone(client, tone, sessionmaker):
    await sign_up(client, "salma@example.com")
    story = await published_story(client, tone, sessionmaker)
    assert story["status"] == "published"
    assert story["published_at"] is not None

    as_user(client, None)
    public = await client.get(f"/api/v1/stories/{story['id']}")
    assert public.status_code == 200
    assert public.json()["title"] == COMPLETE["title"]
    assert (await client.get(public.json()["audio"]["url"])).status_code == 200


async def test_a_published_story_can_no_longer_be_edited(client, tone, sessionmaker):
    await sign_up(client, "salma@example.com")
    story = await published_story(client, tone, sessionmaker)
    path = f"/api/v1/stories/{story['id']}"
    assert (await client.patch(path, json={"title": "Changed"})).status_code == 409
    assert (await upload(client, story["id"], tone)).status_code == 409
    assert (await client.post(f"{path}/submit")).status_code == 409


# --- media ---


async def test_draft_audio_is_private(client, tone):
    author = await sign_up(client, "salma@example.com")
    story = await new_story(client)
    url = (await upload(client, story["id"], tone)).json()["audio"]["url"]
    as_user(client, None)
    assert (await client.get(url)).status_code == 404
    as_user(client, author)
    assert (await client.get(url)).status_code == 200


async def test_audio_supports_seeking_with_byte_ranges(client, tone, sessionmaker):
    await sign_up(client, "salma@example.com")
    story = await published_story(client, tone, sessionmaker)
    url = story["audio"]["url"]
    full = await client.get(url)
    assert full.headers.get("accept-ranges") == "bytes"
    part = await client.get(url, headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.headers["content-range"].startswith("bytes 100-199/")
    assert part.content == full.content[100:200]


async def test_unknown_media_is_404(client):
    assert (await client.get("/media/00000000-0000-0000-0000-000000000000")).status_code == 404
    assert (await client.get("/media/../../etc/passwd")).status_code == 404


async def test_a_playlist_disguised_as_audio_cannot_make_ffmpeg_read_other_files(client, tmp_path):
    """An HLS or concat playlist labelled as audio must not pull in files from the server."""
    await sign_up(client, "salma@example.com")
    story = await new_story(client)
    secret = tmp_path / "secret.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1", str(secret)], check=True
    )
    for name, body, content_type in [
        ("trick.wav", f"ffconcat version 1.0\nfile '{secret}'\n", "audio/wav"),
        ("trick.mp3", f"#EXTM3U\n#EXTINF:1,\nfile://{secret}\n#EXT-X-ENDLIST\n", "audio/mpeg"),
    ]:
        trick = tmp_path / name
        trick.write_text(body)
        assert (
            await upload(client, story["id"], trick, content_type=content_type)
        ).status_code == 422


async def test_tags_are_normalized_saved_and_editable(client):
    await sign_up(client, "tags@example.com")
    story = await new_story(client, tags=[" Weaving ", "WEAVING", "تراث"])
    assert story["tags"] == ["weaving", "تراث"]
    updated = await client.patch(f"/api/v1/stories/{story['id']}", json={"tags": ["History"]})
    assert updated.json()["tags"] == ["history"]
    read = await client.get(f"/api/v1/stories/{story['id']}")
    assert read.json()["tags"] == ["history"]
    for tags in ([" "], ["x" * 41], [str(i) for i in range(11)], None):
        assert (
            await client.patch(f"/api/v1/stories/{story['id']}", json={"tags": tags})
        ).status_code == 422
