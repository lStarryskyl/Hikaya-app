"""Moderation on submit, the held / needs-edit loop, My stories, and deleting a story."""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select, text, update

from app.models import Job, Story
from app.providers import fake
from app.worker import run_one
from tests.conftest import CONSENT

PASSWORD = "correct horse battery"


@pytest.fixture(scope="session")
def tone(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("mod-audio") / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=6", "-ac", "1", str(path)],
        check=True,
    )
    return path


@pytest.fixture(autouse=True)
def fresh_fakes():
    fake.reset()
    yield
    fake.reset()


async def drain(sessionmaker) -> int:
    ran = 0
    while True:
        async with sessionmaker() as s:
            await s.execute(
                update(Job).where(Job.status == "queued").values(run_after=text("now()"))
            )
            await s.commit()
        if not await run_one(sessionmaker):
            return ran
        ran += 1


async def sign_up(client, email="salma@example.com"):
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "display_name": "Salma"}
    )
    assert r.status_code == 201
    return client.cookies.get("hikaya_session")


async def ready_story(client, sessionmaker, tone, language="jordanian", title="A story"):
    story = (
        await client.post(
            "/api/v1/stories",
            json={
                "title": title,
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
    await drain(sessionmaker)
    return story["id"]


async def submit(client, story_id):
    return await client.post(f"/api/v1/stories/{story_id}/submit", json=CONSENT)


async def edit(client, story_id, kind, first_line):
    story = (await client.get(f"/api/v1/stories/{story_id}")).json()
    layer = next(la for la in story["layers"] if la["kind"] == kind)
    texts = [s["text"] for s in layer["segments"]]
    texts[0] = first_line
    r = await client.patch(f"/api/v1/stories/{story_id}/layers/{kind}", json={"texts": texts})
    assert r.status_code == 200, r.text


# --- moderation on submit ---


async def test_a_clean_story_is_checked_then_published(client, sessionmaker, tone):
    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    r = await submit(client, story_id)
    assert r.status_code == 200
    assert r.json()["status"] == "moderating"
    assert r.json()["published_at"] is None

    await drain(sessionmaker)
    story = (await client.get(f"/api/v1/stories/{story_id}")).json()
    assert story["status"] == "published"
    assert story["published_at"] is not None
    assert story["moderation"]["held"] is False
    assert {label["label"] for label in story["moderation"]["labels"]} == {
        "hate", "violence", "sexual", "other_terrible"
    }  # fmt: skip
    assert not any(label["raised"] for label in story["moderation"]["labels"])
    client.cookies.clear()
    public = await client.get(f"/api/v1/stories/{story_id}")
    assert public.status_code == 200
    assert public.json()["moderation"] is None  # moderation detail is for the author and staff


async def test_any_label_holds_the_story(client, sessionmaker, tone):
    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    await edit(client, story_id, "translation_en", "They threatened to kill the shepherd.")
    await submit(client, story_id)
    await drain(sessionmaker)

    story = (await client.get(f"/api/v1/stories/{story_id}")).json()
    assert story["status"] == "held"
    assert story["published_at"] is None
    raised = [la for la in story["moderation"]["labels"] if la["raised"]]
    assert [la["label"] for la in raised] == ["violence"]
    assert "kill" in raised[0]["reason"]

    client.cookies.clear()
    assert (await client.get(f"/api/v1/stories/{story_id}")).status_code == 404
    feed = (await client.get("/api/v1/stories")).json()["items"]
    assert story_id not in {s["id"] for s in feed}


async def test_moderation_reads_the_polished_text_too(client, sessionmaker, tone):
    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone, language="english")
    await edit(client, story_id, "polished", "A hateful speech was given here.")
    await submit(client, story_id)
    await drain(sessionmaker)
    story = (await client.get(f"/api/v1/stories/{story_id}")).json()
    assert story["status"] == "held"
    assert [la["label"] for la in story["moderation"]["labels"] if la["raised"]] == ["hate"]


async def test_the_result_records_which_text_it_judged(client, sessionmaker, tone, session):
    from app.models import ModerationResult

    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    await submit(client, story_id)
    await drain(sessionmaker)
    result = (await session.execute(select(ModerationResult))).scalar_one()
    assert len(result.text_hash) == 64
    assert set(result.labels) == {"hate", "violence", "sexual", "other_terrible"}


async def test_publishing_waits_for_the_english_translation(client, sessionmaker, tone):
    await sign_up(client)
    fake.FAIL_ON.add("translate")
    story_id = await ready_story(client, sessionmaker, tone)
    r = await submit(client, story_id)
    assert r.status_code == 422
    assert "English translation" in r.json()["detail"]


async def test_a_story_being_checked_cannot_be_edited_or_submitted_again(
    client, sessionmaker, tone
):
    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    await submit(client, story_id)
    path = f"/api/v1/stories/{story_id}"
    assert (await client.patch(path, json={"title": "Changed"})).status_code == 409
    assert (await submit(client, story_id)).status_code == 409


async def test_a_failed_check_shows_and_can_be_retried(client, sessionmaker, tone):
    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    fake.FAIL_ON.add("moderate")
    await submit(client, story_id)
    await drain(sessionmaker)
    steps = {
        s["step"]: s
        for s in (await client.get(f"/api/v1/stories/{story_id}/pipeline")).json()["steps"]
    }
    assert steps["moderate"]["status"] == "failed"
    assert (await client.get(f"/api/v1/stories/{story_id}")).json()["status"] == "moderating"

    fake.FAIL_ON.clear()
    r = await client.post(f"/api/v1/stories/{story_id}/pipeline/moderate/retry")
    assert r.status_code == 200
    await drain(sessionmaker)
    assert (await client.get(f"/api/v1/stories/{story_id}")).json()["status"] == "published"


# --- needs edit and resubmit ---


async def reject(session, story_id, note):
    await session.execute(
        update(Story)
        .where(Story.id == story_id)
        .values(status="needs_edit", review_note=note, reviewed_at=text("now()"))
    )
    await session.commit()


async def test_after_a_rejection_the_author_edits_and_resubmits(
    client, sessionmaker, session, tone
):
    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    await edit(client, story_id, "translation_en", "He said he would kill them all.")
    await submit(client, story_id)
    await drain(sessionmaker)
    await reject(session, story_id, "Please remove the threat in the first line.")

    story = (await client.get(f"/api/v1/stories/{story_id}")).json()
    assert story["status"] == "needs_edit"
    assert story["review"]["note"] == "Please remove the threat in the first line."

    await edit(client, story_id, "translation_en", "He said he would come back one day.")
    r = await submit(client, story_id)
    assert r.json()["status"] == "moderating"
    await drain(sessionmaker)
    assert (await client.get(f"/api/v1/stories/{story_id}")).json()["status"] == "published"


async def test_held_and_needs_edit_stories_are_private(client, sessionmaker, session, tone):
    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    await edit(client, story_id, "translation_en", "An explicit scene.")
    await submit(client, story_id)
    await drain(sessionmaker)
    await sign_up(client, "other@example.com")
    assert (await client.get(f"/api/v1/stories/{story_id}")).status_code == 404
    await reject(session, story_id, "note")
    assert (await client.get(f"/api/v1/stories/{story_id}")).status_code == 404


# --- my stories ---


async def test_my_stories_lists_every_status_of_mine_only(client, sessionmaker, session, tone):
    await sign_up(client)
    draft = (await client.post("/api/v1/stories", json={"title": "Draft one"})).json()["id"]
    published = await ready_story(client, sessionmaker, tone, title="Published one")
    await submit(client, published)
    await drain(sessionmaker)
    held = await ready_story(client, sessionmaker, tone, title="Held one")
    await edit(client, held, "translation_en", "A weapon in the market.")
    await submit(client, held)
    await drain(sessionmaker)
    rejected = await ready_story(client, sessionmaker, tone, title="Rejected one")
    await reject(session, rejected, "Add the place.")

    await sign_up(client, "other@example.com")
    await client.post("/api/v1/stories", json={"title": "Not mine"})
    assert len((await client.get("/api/v1/me/stories")).json()) == 1

    client.cookies.clear()
    assert (await client.get("/api/v1/me/stories")).status_code == 401
    await client.post(
        "/api/v1/auth/login", json={"email": "salma@example.com", "password": PASSWORD}
    )
    mine = {s["title"]: s for s in (await client.get("/api/v1/me/stories")).json()}
    assert {t: s["status"] for t, s in mine.items()} == {
        "Draft one": "draft",
        "Published one": "published",
        "Held one": "held",
        "Rejected one": "needs_edit",
    }
    assert mine["Held one"]["held_for"] == ["violence"]
    assert mine["Rejected one"]["review_note"] == "Add the place."
    assert mine["Draft one"]["id"] == draft


# --- deleting ---


async def test_deleting_a_story_removes_its_rows_and_files(client, sessionmaker, session, tone):
    from app.config import get_settings

    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    story = (await client.get(f"/api/v1/stories/{story_id}")).json()
    audio_url = story["audio"]["url"]
    folder = Path(get_settings().media_dir) / "stories" / story_id
    assert folder.is_dir()

    r = await client.delete(f"/api/v1/stories/{story_id}")
    assert r.status_code == 204
    assert (await client.get(f"/api/v1/stories/{story_id}")).status_code == 404
    assert (await client.get(audio_url)).status_code == 404
    assert not folder.exists()
    for table in ("stories", "assets", "text_layers", "pipeline_steps", "story_photos"):
        count = (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
        assert count == 0, table


async def test_only_the_author_deletes(client, sessionmaker, tone):
    await sign_up(client)
    story_id = await ready_story(client, sessionmaker, tone)
    await sign_up(client, "other@example.com")
    assert (await client.delete(f"/api/v1/stories/{story_id}")).status_code == 404
    client.cookies.clear()
    assert (await client.delete(f"/api/v1/stories/{story_id}")).status_code == 401
