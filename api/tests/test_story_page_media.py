"""A published story's page: photos staff add after publishing, and the video story shown on it."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app import media
from app.config import get_settings
from app.models import AuditEvent, Story, User, VideoGeneration
from app.narrated_video import LEAD_MS
from tests.test_moderation import drain
from tests.test_narrated_video import narrated, probe, story_with_soundtrack, webp_photo
from tests.test_pipeline import sign_up
from tests.test_videos import admin


async def member(session, email="kiosk@example.com") -> User:
    user = User(email=email, display_name="Tariq", password_hash="!")
    session.add(user)
    await session.commit()
    return user


async def story_of(session, author: User, status="published") -> Story:
    story = Story(
        author_id=author.id,
        title="A magazine, forty years later",
        place_name="Downtown Amman",
        status=status,
        published_at=datetime.now(UTC) if status == "published" else None,
        original_language="jordanian",
    )
    session.add(story)
    await session.commit()
    return story


async def audit_actions(session, story_id) -> list[str]:
    rows = await session.execute(
        select(AuditEvent.action)
        .where(AuditEvent.target_id == story_id)
        .order_by(AuditEvent.created_at)
    )
    return list(rows.scalars())


def a_photo(name="kiosk.webp"):
    return {"file": (name, webp_photo(), "image/webp")}


# --- photos ---


async def test_staff_add_reorder_and_remove_photos_of_a_published_story(
    client, session, sessionmaker, monkeypatch
):
    queued = []

    async def remember(session, story):
        queued.append(story.id)

    monkeypatch.setattr(media, "queue", remember)
    story = await story_of(session, await member(session))
    await admin(client, sessionmaker)
    url = f"/api/v1/staff/stories/{story.id}/photos"
    ids = []
    for name in ("sign.webp", "front.webp"):
        r = await client.post(url, files=a_photo(name))
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    r = await client.put(f"{url}/order", json={"ids": ids[::-1]})
    assert r.status_code == 200, r.text
    assert [p["id"] for p in r.json()] == ids[::-1]
    r = await client.delete(f"{url}/{ids[1]}")
    assert r.status_code == 204, r.text

    client.cookies.clear()  # what any visitor sees
    page = (await client.get(f"/api/v1/stories/{story.id}")).json()
    assert [p["id"] for p in page["photos"]] == [ids[0]]
    assert await audit_actions(session, story.id) == [
        "photo_added",
        "photo_added",
        "photos_reordered",
        "photo_removed",
    ]
    assert queued == [story.id] * 4  # the slideshow is made again from the new photos


async def test_only_staff_change_photos_and_never_on_their_own_story_or_a_draft(
    client, session, sessionmaker
):
    author = await member(session)
    published = await story_of(session, author)
    draft = await story_of(session, author, status="draft")

    await sign_up(client, email="visitor@example.com")
    r = await client.post(f"/api/v1/staff/stories/{published.id}/photos", files=a_photo())
    assert r.status_code == 403

    staff = await admin(client, sessionmaker)
    own = await story_of(session, await session.get(User, uuid.UUID(staff["id"])))
    r = await client.post(f"/api/v1/staff/stories/{own.id}/photos", files=a_photo())
    assert r.status_code == 403
    r = await client.post(f"/api/v1/staff/stories/{draft.id}/photos", files=a_photo())
    assert r.status_code == 409
    assert await audit_actions(session, published.id) == []


# --- the video story ---


async def finished_video(client, session, sessionmaker, monkeypatch, seed=1):
    """A member's published story with a finished narrated video over its recording."""
    monkeypatch.setattr(get_settings(), "enable_ai_video", True)
    story = await story_with_soundtrack(
        client, session, sessionmaker, monkeypatch, narration=False, recording=True
    )
    story.author_id = (await member(session)).id  # staff never act on their own story
    await session.commit()
    r = await client.post(
        "/api/v1/staff/videos",
        json=narrated(story, provider="fake", soundtrack="recording", seed=seed),
    )
    assert r.status_code == 202, r.text
    await drain(sessionmaker)
    return story, r.json()["id"]


async def show(client, story, video_id):
    return await client.put(f"/api/v1/staff/stories/{story.id}/video", json={"video_id": video_id})


async def test_a_finished_narrated_video_is_shown_on_the_story_page_to_everyone(
    client, session, sessionmaker, monkeypatch
):
    story, video_id = await finished_video(client, session, sessionmaker, monkeypatch)
    staff_view = (await client.get(f"/api/v1/staff/videos/{video_id}")).json()
    assert staff_view["shown"] is False
    r = await show(client, story, video_id)
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/v1/staff/videos/{video_id}")).json()["shown"] is True

    client.cookies.clear()  # a visitor, not signed in
    video = (await client.get(f"/api/v1/stories/{story.id}")).json()["video"]
    assert video["voice"] == "recording"
    # Captions in video time (the picture starts before the first word), with the English.
    first = video["captions"][0]
    assert first["start_ms"] == LEAD_MS and first["text"] and first["english"]
    played = await client.get(video["url"])
    assert played.status_code == 200
    assert played.headers["content-type"] == "video/mp4"
    assert probe(played.content)["audio"] is True
    seek = await client.get(video["url"], headers={"Range": "bytes=0-99"})
    assert seek.status_code == 206  # browsers seek with ranges

    await admin(client, sessionmaker)
    assert (await show(client, story, None)).status_code == 200
    client.cookies.clear()
    assert (await client.get(f"/api/v1/stories/{story.id}")).json()["video"] is None
    assert (await client.get(video["url"])).status_code == 404
    assert await audit_actions(session, story.id) == ["video_shown", "video_hidden"]


async def test_only_a_finished_narrated_video_of_the_same_story_can_be_shown(
    client, session, sessionmaker, monkeypatch
):
    story, video_id = await finished_video(client, session, sessionmaker, monkeypatch)
    unfinished = await client.post(
        "/api/v1/staff/videos",
        json=narrated(story, provider="fake", soundtrack="recording", seed=2),
    )
    assert (await show(client, story, unfinished.json()["id"])).status_code == 409

    other = await story_of(session, await member(session, email="other@example.com"))
    assert (await show(client, other, video_id)).status_code == 404
    assert (await show(client, story, str(uuid.uuid4()))).status_code == 404
    assert (await client.get(f"/api/v1/stories/{story.id}")).json()["video"] is None


async def test_the_video_leaves_the_page_when_the_story_is_held_or_the_video_removed(
    client, session, sessionmaker, monkeypatch
):
    story, video_id = await finished_video(client, session, sessionmaker, monkeypatch)
    assert (await show(client, story, video_id)).status_code == 200
    url = (await client.get(f"/api/v1/stories/{story.id}")).json()["video"]["url"]
    client.cookies.clear()

    story.status = "held"
    await session.commit()
    assert (await client.get(url)).status_code == 404
    story.status = "published"
    await session.commit()
    assert (await client.get(url)).status_code == 200

    generation = await session.get(VideoGeneration, uuid.UUID(video_id))
    generation.payload = {**generation.payload, "removed": True}  # its voice was revoked
    await session.commit()
    assert (await client.get(f"/api/v1/stories/{story.id}")).json()["video"] is None
    assert (await client.get(url)).status_code == 404


@pytest.mark.parametrize("voice", ["recording", "narration"])
async def test_the_page_says_whose_voice_the_video_carries(
    client, session, sessionmaker, monkeypatch, voice
):
    monkeypatch.setattr(get_settings(), "enable_ai_video", True)
    story = await story_with_soundtrack(
        client, session, sessionmaker, monkeypatch, narration=True, recording=True
    )
    story.author_id = (await member(session)).id
    await session.commit()
    r = await client.post(
        "/api/v1/staff/videos", json=narrated(story, provider="fake", soundtrack=voice)
    )
    await drain(sessionmaker)
    assert (await show(client, story, r.json()["id"])).status_code == 200
    assert (await client.get(f"/api/v1/stories/{story.id}")).json()["video"]["voice"] == voice
