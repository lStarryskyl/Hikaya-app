"""Story packs: a published story exported with what its page shows, imported on another copy."""

import json
import shutil

import pytest
from sqlalchemy import func, select

from app import story_pack
from app.config import get_settings
from app.models import Asset, Job, SpendEntry, Story, TextLayer, User, VideoGeneration
from app.providers import fake
from app.storage import get_storage
from tests.test_moderation import drain
from tests.test_narrated_video import clip, narrated, story_with_soundtrack, tone
from tests.test_story_page_media import a_photo, member, show
from tests.test_videos import admin


async def published_story(client, session, sessionmaker, monkeypatch) -> Story:
    """A member's published story with everything a page shows: every text version (one of
    them edited), a recording, a narration, a slideshow, a photo and its video story."""
    monkeypatch.setattr(get_settings(), "enable_ai_video", True)
    story = await story_with_soundtrack(
        client, session, sessionmaker, monkeypatch, narration=True, recording=True
    )
    story.author_id = (await member(session)).id
    storage = get_storage()
    for kind, key, data, content_type in (
        ("original_audio", f"stories/{story.id}/audio/original.mp3", tone(20), "audio/mpeg"),
        ("slideshow", f"stories/{story.id}/slideshow/test.mp4", clip(6), "video/mp4"),
    ):
        storage.write_bytes(key, data)
        session.add(
            Asset(
                story_id=story.id,
                kind=kind,
                storage_key=key,
                content_type=content_type,
                size_bytes=storage.size(key),
            )
        )
    polished = (
        await session.execute(
            select(TextLayer).where(TextLayer.story_id == story.id, TextLayer.kind == "polished")
        )
    ).scalar_one()
    polished.edited = True
    await session.commit()
    r = await client.post(
        "/api/v1/staff/videos",
        json=narrated(story, provider="fake", soundtrack="recording"),
    )
    await drain(sessionmaker)
    photo = await client.post(f"/api/v1/staff/stories/{story.id}/photos", files=a_photo())
    assert photo.status_code == 201, photo.text
    assert (await show(client, story, r.json()["id"])).status_code == 200
    client.cookies.clear()  # from here on, a visitor
    return story


async def page(client, story_id) -> dict:
    r = await client.get(f"/api/v1/stories/{story_id}")
    assert r.status_code == 200, r.text
    return r.json()


def what_visitors_see(p: dict) -> dict:
    return {
        "title": p["title"],
        "storyteller": p["author"]["display_name"],
        "place": (p["place_name"], p["latitude"], p["longitude"]),
        "category": p["category"],
        "language": p["original_language"],
        "status": p["status"],
        "layers": sorted(
            (layer["kind"], layer["language"], layer["edited"], layer["segments"])
            for layer in p["layers"]
        ),
        "photos": len(p["photos"]),
        "recording": p["audio"] is not None,
        "narration": p["narration"] and p["narration"]["segments"],
        "slideshow": p["slideshow"] is not None,
        "video": p["video"] and (p["video"]["voice"], p["video"]["captions"]),
    }


async def forget(session, story: Story) -> None:
    """Another copy of the app: no story, no storyteller, no files."""
    author = await session.get(User, story.author_id)
    await session.delete(story)
    await session.delete(author)
    await session.commit()
    shutil.rmtree(get_storage().path(f"stories/{story.id}"))


async def count(session, model, *where) -> int:
    return (await session.execute(select(func.count()).select_from(model).where(*where))).scalar()


async def test_a_published_story_comes_back_whole_from_its_pack(
    client, session, sessionmaker, monkeypatch, tmp_path
):
    story = await published_story(client, session, sessionmaker, monkeypatch)
    before = what_visitors_see(await page(client, story.id))
    await story_pack.export_story(sessionmaker, story.id, tmp_path / "kiosk")
    await forget(session, story)

    assert await story_pack.import_packs(sessionmaker, tmp_path) == [story.id]
    after = await page(client, story.id)
    assert what_visitors_see(after) == before
    files = [
        after["audio"]["url"],
        after["audio"]["original_url"],
        after["narration"]["url"],
        after["slideshow"]["url"],
        after["video"]["url"],
        *after["photos"][0]["photo"]["urls"].values(),
    ]
    for url in files:
        assert (await client.get(url)).status_code == 200, url


async def test_a_pack_holds_only_what_the_page_shows(
    client, session, sessionmaker, monkeypatch, tmp_path
):
    story = await published_story(client, session, sessionmaker, monkeypatch)
    folder = await story_pack.export_story(sessionmaker, story.id, tmp_path / "kiosk")
    assert sorted(p.name for p in folder.iterdir()) == [
        "narration.mp3",
        "photo-01.webp",
        "recording.mp3",
        "slideshow.mp4",
        "story.json",
        "video.mp4",
    ]
    data = (folder / "story.json").read_text()
    assert json.loads(data)["storyteller"]["display_name"] == "Tariq"
    assert "@" not in data  # no account details
    # Shots keep what the video was made from, not provider request ids or file paths.
    shots = json.loads(data)["video"]["shots"]
    assert shots
    assert all(set(shot) == {"start_ms", "end_ms", "seconds", "lines", "prompt"} for shot in shots)


async def test_only_published_stories_without_a_cloned_voice_are_exported(
    client, session, sessionmaker, monkeypatch, tmp_path
):
    cloned = await story_with_soundtrack(
        client, session, sessionmaker, monkeypatch, narration=True, cloned=True
    )
    with pytest.raises(story_pack.PackError, match="cloned voice"):
        await story_pack.export_story(sessionmaker, cloned.id, tmp_path / "cloned")
    cloned.status = "draft"
    await session.commit()
    with pytest.raises(story_pack.PackError, match="published"):
        await story_pack.export_story(sessionmaker, cloned.id, tmp_path / "draft")
    assert list(tmp_path.iterdir()) == []


async def test_importing_calls_nothing_pays_nothing_and_queues_nothing(
    client, session, sessionmaker, monkeypatch, tmp_path
):
    story = await published_story(client, session, sessionmaker, monkeypatch)
    await story_pack.export_story(sessionmaker, story.id, tmp_path / "kiosk")
    await forget(session, story)
    fake.reset()
    spent = await count(session, SpendEntry)
    waiting = await count(session, Job, Job.status.in_(["queued", "running"]))

    await story_pack.import_packs(sessionmaker, tmp_path)
    assert fake.CALLS == []
    assert await count(session, SpendEntry) == spent
    assert await count(session, Job, Job.status.in_(["queued", "running"])) == waiting


async def test_a_story_already_there_keeps_its_changes_unless_refreshed(
    client, session, sessionmaker, monkeypatch, tmp_path
):
    story = await published_story(client, session, sessionmaker, monkeypatch)
    await story_pack.export_story(sessionmaker, story.id, tmp_path / "kiosk")
    assert await story_pack.import_packs(sessionmaker, tmp_path) == []

    await admin(client, sessionmaker)
    assert (await show(client, story, None)).status_code == 200  # taken off in the app
    client.cookies.clear()
    assert await story_pack.import_packs(sessionmaker, tmp_path) == []
    assert (await page(client, story.id))["video"] is None

    assert await story_pack.import_packs(sessionmaker, tmp_path, refresh=True) == [story.id]
    assert (await page(client, story.id))["video"] is not None
    assert await count(session, VideoGeneration, VideoGeneration.story_id == story.id) == 1
    # The recording and its original, the narration and the slideshow, once each.
    assert await count(session, Asset, Asset.story_id == story.id) == 4


async def test_the_packs_in_the_repository_import(client, sessionmaker):
    for story_id in await story_pack.import_packs(sessionmaker, story_pack.DEFAULT_ROOT):
        shown = await page(client, story_id)
        assert shown["status"] == "published"
        assert (await client.get(shown["video"]["url"])).status_code == 200
