"""Story photos (uploads and gallery picks, ordered) and the rights consent on submit."""

import subprocess
from pathlib import Path

import pytest

from app.config import get_settings
from app.seed_demo import seed_demo
from app.worker import run_one

PASSWORD = "correct horse battery"


def make_image(path: Path, codec: str = "png", size: str = "1400x900", color: str = "orange"):
    args = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}",
            "-frames:v", "1"]  # fmt: skip
    if codec == "jpeg":
        args += ["-f", "image2", "-c:v", "mjpeg"]
    subprocess.run([*args, str(path)], check=True)
    return path


@pytest.fixture
def images(tmp_path):
    return {
        "png": make_image(tmp_path / "one.png"),
        "jpeg": make_image(tmp_path / "two.jpg", codec="jpeg", color="teal"),
        "jpeg_named_png": make_image(tmp_path / "three.png", codec="jpeg", color="red"),
    }


@pytest.fixture(scope="session")
def tone(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("audio") / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=3", "-ac", "1", str(path)],
        check=True,
    )
    return path


async def sign_up(client, email="salma@example.com"):
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "display_name": "Salma"}
    )
    assert r.status_code == 201
    return client.cookies.get("hikaya_session")


async def new_story(client, **fields):
    return (await client.post("/api/v1/stories", json=fields)).json()


async def add_photo(client, story_id, path: Path, content_type="image/png"):
    with open(path, "rb") as f:
        return await client.post(
            f"/api/v1/stories/{story_id}/photos", files={"file": (path.name, f, content_type)}
        )


async def photos_of(client, story_id):
    return (await client.get(f"/api/v1/stories/{story_id}")).json()["photos"]


# --- uploads ---


async def test_uploaded_photos_become_webp_in_three_sizes(client, images):
    await sign_up(client)
    story = await new_story(client)
    r = await add_photo(client, story["id"], images["png"])
    assert r.status_code == 201, r.text
    photo = r.json()
    assert photo["source"] == "upload"
    assert set(photo["photo"]["urls"]) == {"480", "960", "1600"}
    image = await client.get(photo["photo"]["urls"]["480"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/webp"
    assert image.content[8:12] == b"WEBP"


async def test_a_jpeg_with_a_png_name_is_read_by_its_content(client, images):
    await sign_up(client)
    story = await new_story(client)
    r = await add_photo(client, story["id"], images["jpeg_named_png"])
    assert r.status_code == 201


async def test_photos_are_kept_in_order_and_the_first_is_the_cover(client, images):
    await sign_up(client)
    story = await new_story(client)
    first = (await add_photo(client, story["id"], images["png"])).json()
    second = (await add_photo(client, story["id"], images["jpeg"], "image/jpeg")).json()
    photos = await photos_of(client, story["id"])
    assert [p["id"] for p in photos] == [first["id"], second["id"]]
    cover = (await client.get(f"/api/v1/stories/{story['id']}")).json()["cover"]
    assert cover["slug"] == first["photo"]["slug"]


async def test_photos_can_be_reordered(client, images):
    await sign_up(client)
    story = await new_story(client)
    a = (await add_photo(client, story["id"], images["png"])).json()["id"]
    b = (await add_photo(client, story["id"], images["jpeg"], "image/jpeg")).json()["id"]
    r = await client.put(f"/api/v1/stories/{story['id']}/photos/order", json={"ids": [b, a]})
    assert r.status_code == 200
    assert [p["id"] for p in await photos_of(client, story["id"])] == [b, a]


@pytest.mark.parametrize("ids", [[], ["missing"], "dupe"])
async def test_a_reorder_must_list_every_photo_once(client, images, ids):
    await sign_up(client)
    story = await new_story(client)
    a = (await add_photo(client, story["id"], images["png"])).json()["id"]
    b = (await add_photo(client, story["id"], images["jpeg"], "image/jpeg")).json()["id"]
    if ids == "dupe":
        ids = [a, a]
    elif ids == ["missing"]:
        ids = [a]
    r = await client.put(f"/api/v1/stories/{story['id']}/photos/order", json={"ids": ids})
    assert r.status_code == 422
    assert {p["id"] for p in await photos_of(client, story["id"])} == {a, b}


async def test_a_photo_can_be_removed(client, images):
    await sign_up(client)
    story = await new_story(client)
    photo = (await add_photo(client, story["id"], images["png"])).json()
    url = photo["photo"]["urls"]["480"]
    r = await client.delete(f"/api/v1/stories/{story['id']}/photos/{photo['id']}")
    assert r.status_code == 204
    assert await photos_of(client, story["id"]) == []
    assert (await client.get(url)).status_code == 404


async def test_photo_limits(client, images, tmp_path, monkeypatch):
    await sign_up(client)
    story = await new_story(client)
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not a photo")
    assert (await add_photo(client, story["id"], text_file, "text/plain")).status_code == 415
    fake = tmp_path / "fake.png"
    fake.write_bytes(b"#EXTM3U\nfile:///etc/passwd\n")
    assert (await add_photo(client, story["id"], fake)).status_code == 422

    monkeypatch.setattr(get_settings(), "max_photo_upload_mb", 0.001)
    assert (await add_photo(client, story["id"], images["png"])).status_code == 413
    monkeypatch.setattr(get_settings(), "max_photo_upload_mb", 15)

    monkeypatch.setattr(get_settings(), "max_photos_per_story", 2)
    assert (await add_photo(client, story["id"], images["png"])).status_code == 201
    assert (await add_photo(client, story["id"], images["png"])).status_code == 201
    r = await add_photo(client, story["id"], images["png"])
    assert r.status_code == 409
    assert "2 photos" in r.json()["detail"]


async def test_draft_photos_are_private_and_only_the_author_edits(client, images):
    author = await sign_up(client)
    story = await new_story(client)
    photo = (await add_photo(client, story["id"], images["png"])).json()
    url = photo["photo"]["urls"]["480"]
    await sign_up(client, "other@example.com")
    assert (await client.get(url)).status_code == 404
    assert (await add_photo(client, story["id"], images["png"])).status_code == 404
    path = f"/api/v1/stories/{story['id']}/photos/{photo['id']}"
    assert (await client.delete(path)).status_code == 404
    client.cookies.clear()
    assert (await client.get(url)).status_code == 404
    client.cookies.set("hikaya_session", author)
    assert (await client.get(url)).status_code == 200


# --- gallery picks ---


async def test_a_member_can_pick_photos_from_a_place_gallery(
    client, sessionmaker, tmp_path, images
):
    make_image(tmp_path / "petra-treasury.png")
    await seed_demo(sessionmaker, tmp_path)
    await sign_up(client)
    story = await new_story(client)
    r = await client.post(
        f"/api/v1/stories/{story['id']}/photos/gallery", json={"slug": "petra-treasury"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "gallery"
    assert r.json()["photo"]["slug"] == "petra-treasury"
    unknown = await client.post(
        f"/api/v1/stories/{story['id']}/photos/gallery", json={"slug": "nowhere"}
    )
    assert unknown.status_code == 404
    # Removing a gallery pick never deletes the shared place photo.
    pick = r.json()
    await client.delete(f"/api/v1/stories/{story['id']}/photos/{pick['id']}")
    assert (await client.get(pick["photo"]["urls"]["480"])).status_code == 200


# --- consent on submit ---


async def ready_story(client, sessionmaker, tone):
    story = await new_story(
        client,
        title="T",
        category="folklore",
        place_name="Madaba",
        latitude=31.7,
        longitude=35.8,
        original_language="jordanian",
    )
    with open(tone, "rb") as f:
        await client.put(
            f"/api/v1/stories/{story['id']}/audio", files={"file": ("t.wav", f, "audio/wav")}
        )
    while await run_one(sessionmaker):
        pass
    return story


async def test_the_rights_statement_is_served_with_its_version(client):
    r = await client.get("/api/v1/stories/consent")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] and len(body["text"]) > 40


async def test_publishing_needs_the_current_rights_statement(client, sessionmaker, tone):
    await sign_up(client)
    story = await ready_story(client, sessionmaker, tone)
    path = f"/api/v1/stories/{story['id']}/submit"
    current = (await client.get("/api/v1/stories/consent")).json()["version"]

    assert (await client.post(path)).status_code == 422
    assert (
        await client.post(path, json={"consent": False, "consent_version": current})
    ).status_code == 422
    old = await client.post(path, json={"consent": True, "consent_version": "an-old-version"})
    assert old.status_code == 422
    assert "statement" in old.json()["detail"]

    ok = await client.post(path, json={"consent": True, "consent_version": current})
    assert ok.status_code == 200, ok.text
    assert ok.json()["consent"]["version"] == current
    assert ok.json()["consent"]["at"] is not None
