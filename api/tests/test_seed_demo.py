"""The demo seed: places, photos, storytellers and seven published stories."""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import PlacePhoto, Story, User
from app.seed_demo import seed_demo


@pytest.fixture
def photo_dir(tmp_path) -> Path:
    """Two of the catalogue's photos as small real PNGs; the rest are missing on purpose."""
    for name in ("petra-treasury", "weaving-loom-2"):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=orange:s=2000x1200",
             "-frames:v", "1", str(tmp_path / f"{name}.png")],
            check=True,
        )  # fmt: skip
    return tmp_path


async def counts(session):
    stories = (await session.execute(select(func.count()).select_from(Story))).scalar_one()
    photos = (await session.execute(select(func.count()).select_from(PlacePhoto))).scalar_one()
    return stories, photos


async def test_seed_loads_seven_published_stories(client, sessionmaker, session, photo_dir):
    await seed_demo(sessionmaker, photo_dir)
    feed = (await client.get("/api/v1/stories", params={"limit": 50})).json()["items"]
    assert len(feed) == 7
    titles = {s["title"] for s in feed}
    assert "The Loom of Ancestors" in titles and "The Ceramic Legacy" in titles
    assert all(s["excerpt"] for s in feed)

    pins = (await client.get("/api/v1/map/pins")).json()
    assert len(pins) == 7
    assert {p["kind"] for p in pins} == {"featured", "recent", "ordinary"}


async def test_seed_stories_have_every_text_version_lined_up(client, sessionmaker, photo_dir):
    await seed_demo(sessionmaker, photo_dir)
    feed = (await client.get("/api/v1/stories", params={"limit": 50})).json()["items"]
    for card in feed:
        story = (await client.get(f"/api/v1/stories/{card['id']}")).json()
        layers = {layer["kind"]: layer for layer in story["layers"]}
        expected = {
            "jordanian": {"verbatim", "polished", "translation_en", "translation_msa"},
            "msa": {"verbatim", "polished", "translation_en"},
            "english": {"verbatim", "polished", "translation_msa"},
        }[story["original_language"]]
        assert set(layers) == expected, story["title"]
        timing = [(s["start_ms"], s["end_ms"]) for s in layers["verbatim"]["segments"]]
        assert len(timing) >= 4
        assert timing[-1][1] == story["duration_ms"]
        for layer in layers.values():
            assert [(s["start_ms"], s["end_ms"]) for s in layer["segments"]] == timing
            assert all(s["text"] for s in layer["segments"])


async def test_seed_storytellers_cannot_sign_in(client, sessionmaker, session, photo_dir):
    await seed_demo(sessionmaker, photo_dir)
    tellers = (await session.execute(select(User))).scalars().all()
    assert len(tellers) >= 5
    for user in tellers:
        r = await client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "anything at all"}
        )
        assert r.status_code == 401


async def test_seed_is_idempotent(sessionmaker, session, photo_dir):
    await seed_demo(sessionmaker, photo_dir)
    first = await counts(session)
    ids = set((await session.execute(select(Story.id))).scalars())
    await seed_demo(sessionmaker, photo_dir)
    assert await counts(session) == first
    assert set((await session.execute(select(Story.id))).scalars()) == ids


async def test_place_photos_are_converted_to_webp_sizes(client, sessionmaker, photo_dir):
    await seed_demo(sessionmaker, photo_dir)
    places = (await client.get("/api/v1/places")).json()
    by_name = {p["name"]: p for p in places}
    assert {"Petra", "Amman", "Madaba", "Jerash", "Wadi Rum", "Aqaba"} <= set(by_name)
    petra = by_name["Petra"]
    assert [p["slug"] for p in petra["photos"]] == ["petra-treasury"]  # only files that exist
    photo = petra["photos"][0]
    assert set(photo["urls"]) == {"480", "960", "1600"}
    assert petra["cover"]["slug"] == "petra-treasury"
    assert petra["story_count"] == 1
    r = await client.get(photo["urls"]["480"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WEBP"
    assert len(r.content) < len((await client.get(photo["urls"]["1600"])).content)
    # A place without any photo file still exists, just without photos.
    assert by_name["Aqaba"]["photos"] == [] and by_name["Aqaba"]["cover"] is None


async def test_story_cover_comes_from_its_photo_or_its_place(client, sessionmaker, photo_dir):
    await seed_demo(sessionmaker, photo_dir)
    feed = {
        s["title"]: s
        for s in (await client.get("/api/v1/stories", params={"limit": 50})).json()["items"]
    }
    assert feed["The Loom of Ancestors"]["cover"]["slug"] == "weaving-loom-2"
    assert feed["The Echoes of Petra"]["cover"]["slug"] == "petra-treasury"
    assert feed["Echoes of the Red Desert"]["cover"] is None  # no Wadi Rum file in this test


@pytest.mark.parametrize(
    "path", ["/media/places/nope/480.webp", "/media/places/petra-treasury/333.webp"]
)
async def test_unknown_photos_and_sizes_are_404(client, sessionmaker, photo_dir, path):
    await seed_demo(sessionmaker, photo_dir)
    assert (await client.get(path)).status_code == 404


async def test_seed_keeps_curation_made_in_the_app(sessionmaker, session, photo_dir):
    await seed_demo(sessionmaker, photo_dir)
    loom = (
        await session.execute(select(Story).where(Story.title == "The Loom of Ancestors"))
    ).scalar_one()
    petra = (
        await session.execute(select(Story).where(Story.title == "The Echoes of Petra"))
    ).scalar_one()
    from datetime import UTC, datetime

    loom.curated_at = datetime.now(UTC)  # staff added it to the museum
    petra.curated_at = None  # staff took it out
    await session.commit()
    await seed_demo(sessionmaker, photo_dir)
    await session.refresh(loom)
    await session.refresh(petra)
    assert loom.curated_at is not None
    assert petra.curated_at is None


async def test_a_jpeg_saved_with_a_png_name_still_converts(sessionmaker, tmp_path, client):
    """Several catalogue files are JPEGs named .png; the real format decides how to read them."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=teal:s=1200x800",
         "-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", str(tmp_path / "aqaba.png")],
        check=True,
    )  # fmt: skip
    assert (tmp_path / "aqaba.png").read_bytes()[:3] == b"\xff\xd8\xff"
    await seed_demo(sessionmaker, tmp_path)
    places = {p["name"]: p for p in (await client.get("/api/v1/places")).json()}
    assert [p["slug"] for p in places["Aqaba"]["photos"]] == ["aqaba"]


def test_an_unknown_image_format_is_refused(tmp_path):
    from app.places import image_demuxer

    odd = tmp_path / "odd.png"
    odd.write_bytes(b"#EXTM3U\nfile:///etc/passwd\n")
    assert image_demuxer(odd) is None
