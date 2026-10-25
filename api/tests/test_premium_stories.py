"""Premium (#19): AI video samples on seeded stories, and staff resetting a member's plan."""

import pytest
from sqlalchemy import select, update

from app.models import AuditEvent, Role, User
from app.seed_demo import seed_demo, story_id
from app.seed_staff import StaffSeed, seed_staff

PASSWORD = "correct horse battery"


@pytest.fixture
async def seeded(sessionmaker, tmp_path, monkeypatch):
    await seed_demo(sessionmaker)


async def sign_up(client, email="member@example.com"):
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "display_name": "Mo"}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def make_premium(session, email):
    await session.execute(update(User).where(User.email == email).values(plan="premium"))
    await session.commit()


async def staff(client, sessionmaker, role=Role.REVIEWER, email="rev@example.com"):
    await seed_staff(sessionmaker, [StaffSeed(email, PASSWORD, role, "Rania Reviewer")])
    client.cookies.clear()
    await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


PETRA = str(story_id("echoes-of-petra"))
DESERT = str(story_id("echoes-red-desert"))


async def ai_video(client, sid):
    return (await client.get(f"/api/v1/stories/{sid}")).json()["ai_video"]


# --- AI video on seeded stories ---


async def test_the_seed_attaches_ai_video_samples_to_two_stories(client, seeded):
    with_video = [
        s["id"]
        for s in (await client.get("/api/v1/stories?limit=50")).json()["items"]
        if (await ai_video(client, s["id"])) is not None
    ]
    assert sorted(with_video) == sorted([PETRA, DESERT])


async def test_visitors_and_free_members_see_a_locked_preview(client, seeded):
    video = await ai_video(client, PETRA)
    assert video["locked"] is True and video["video_url"] is None
    assert video["poster_url"] and video["credit"]
    # Honest labelling: a sample of what AI video looks like, not made from this story.
    assert "not made from this story" in video["note"]
    await sign_up(client)
    assert (await ai_video(client, PETRA))["locked"] is True


async def test_premium_members_and_staff_can_watch_it(client, session, sessionmaker, seeded):
    await sign_up(client)
    await make_premium(session, "member@example.com")
    video = await ai_video(client, PETRA)
    assert video["locked"] is False
    r = await client.get(video["video_url"])
    assert r.status_code == 200 and r.headers["content-type"] == "video/webm"
    await staff(client, sessionmaker)
    assert (await ai_video(client, DESERT))["locked"] is False


async def test_the_video_itself_stays_premium_only(client, seeded, session):
    await sign_up(client)
    await make_premium(session, "member@example.com")
    url = (await ai_video(client, PETRA))["video_url"]
    await sign_up(client, "free@example.com")
    assert (await client.get(url)).status_code == 403


async def test_a_missing_sample_file_attaches_nothing(client, sessionmaker, monkeypatch):
    from app import billing

    monkeypatch.setattr(billing, "SAMPLE_DIR", billing.SAMPLE_DIR / "missing")
    await seed_demo(sessionmaker)
    assert await ai_video(client, PETRA) is None


# --- staff resetting a plan ---


async def test_staff_reset_a_members_plan_to_free(client, session, sessionmaker):
    await sign_up(client)
    await make_premium(session, "member@example.com")
    await staff(client, sessionmaker)
    r = await client.post("/api/v1/staff/members/plan-reset", json={"email": "member@example.com"})
    assert r.status_code == 200, r.text
    assert r.json() == {"email": "member@example.com", "plan": "free"}
    member = (
        await session.execute(select(User).where(User.email == "member@example.com"))
    ).scalar_one()
    await session.refresh(member)
    assert member.plan == "free"
    (event,) = (await session.execute(select(AuditEvent))).scalars().all()
    assert (event.action, event.target_type, event.target_id) == ("plan_reset", "user", member.id)
    assert event.detail == {"from": "premium"}


async def test_plan_reset_is_staff_only_and_needs_a_known_account(client, sessionmaker):
    await sign_up(client)
    r = await client.post("/api/v1/staff/members/plan-reset", json={"email": "member@example.com"})
    assert r.status_code == 403
    client.cookies.clear()
    r = await client.post("/api/v1/staff/members/plan-reset", json={"email": "member@example.com"})
    assert r.status_code == 401
    await staff(client, sessionmaker)
    r = await client.post("/api/v1/staff/members/plan-reset", json={"email": "nobody@example.com"})
    assert r.status_code == 404


async def test_the_audit_log_names_the_member_whose_plan_was_reset(client, session, sessionmaker):
    await sign_up(client)
    await make_premium(session, "member@example.com")
    await staff(client, sessionmaker, Role.ADMIN, "admin@example.com")
    await client.post("/api/v1/staff/members/plan-reset", json={"email": "member@example.com"})
    (entry,) = (await client.get("/api/v1/staff/audit")).json()
    assert entry["action"] == "plan_reset"
    assert entry["target"] == {"type": "user", "id": entry["target"]["id"], "title": "Mo"}
