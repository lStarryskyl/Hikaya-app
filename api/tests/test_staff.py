"""Staff review and the museum: held stories, curation, self-review, audit and spending."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditEvent, ModerationResult, Role, SpendEntry, Story, TextLayer, User
from app.seed_staff import StaffSeed, seed_staff

PASSWORD = "correct horse battery"
REVIEWER, ADMIN = "rev@example.com", "admin@example.com"


@pytest.fixture
async def staff(sessionmaker):
    await seed_staff(
        sessionmaker,
        [
            StaffSeed(REVIEWER, PASSWORD, Role.REVIEWER, "Rania Reviewer"),
            StaffSeed(ADMIN, PASSWORD, Role.ADMIN, "Adel Admin"),
        ],
    )


@pytest.fixture
async def author(session):
    user = User(email="teller@example.com", display_name="Um Ahmad", password_hash="!")
    session.add(user)
    await session.commit()
    return user


async def sign_in(client, email):
    client.cookies.clear()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text


async def member(client):
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "member@example.com", "password": PASSWORD, "display_name": "Mo"},
    )


async def user_id(session, email):
    return (await session.execute(select(User.id).where(User.email == email))).scalar_one()


async def add_story(session, author_id, title="A story", *, status="published", curated=False):
    now = datetime.now(UTC)
    story = Story(
        author_id=author_id,
        title=title,
        category="folklore",
        place_name="Madaba",
        latitude=31.7,
        longitude=35.8,
        original_language="english",
        status=status,
        published_at=now if status == "published" else None,
        curated_at=now if curated else None,
    )
    session.add(story)
    await session.flush()
    if status == "held":
        session.add(
            ModerationResult(
                story_id=story.id,
                labels={
                    "hate": {"raised": False, "reason": ""},
                    "violence": {"raised": True, "reason": 'The text mentions "kill".'},
                    "sexual": {"raised": False, "reason": ""},
                    "other_terrible": {"raised": False, "reason": ""},
                },
                held=True,
                texts=["He would kill the wolf."],
                text_hash="h",
            )
        )
        session.add(
            TextLayer(
                story_id=story.id,
                kind="polished",
                language="english",
                segments=[{"start_ms": 0, "end_ms": 4000, "text": "He would kill the wolf."}],
            )
        )
    await session.commit()
    return story


async def audit(session):
    return (
        (await session.execute(select(AuditEvent).order_by(AuditEvent.created_at))).scalars().all()
    )


# --- permissions ---

STAFF_ROUTES = [
    ("get", "/api/v1/staff/review"),
    ("post", "/api/v1/staff/stories/{id}/approve"),
    ("post", "/api/v1/staff/stories/{id}/reject"),
    ("post", "/api/v1/staff/stories/{id}/curate"),
    ("post", "/api/v1/staff/stories/{id}/dismiss"),
]
ADMIN_ROUTES = [
    ("delete", "/api/v1/staff/stories/{id}/curation"),
    ("get", "/api/v1/staff/spend"),
    ("get", "/api/v1/staff/audit"),
]


async def call(client, method, path, story_id):
    url = path.format(id=story_id)
    if method == "post":
        return await client.post(url, json={})
    return await getattr(client, method)(url)


async def test_staff_routes_refuse_visitors_and_members(client, session, author, staff):
    story = await add_story(session, author.id, status="held")
    for method, path in STAFF_ROUTES + ADMIN_ROUTES:
        client.cookies.clear()
        assert (await call(client, method, path, story.id)).status_code == 401, path
    await member(client)
    for method, path in STAFF_ROUTES + ADMIN_ROUTES:
        assert (await call(client, method, path, story.id)).status_code == 403, path


async def test_admin_only_routes_refuse_reviewers(client, session, author, staff):
    story = await add_story(session, author.id, curated=True)
    await sign_in(client, REVIEWER)
    for method, path in ADMIN_ROUTES:
        assert (await call(client, method, path, story.id)).status_code == 403, path


# --- the review page ---


async def test_the_review_page_lists_held_stories_and_museum_candidates(
    client, session, author, staff
):
    held = await add_story(session, author.id, "Held one", status="held")
    candidate = await add_story(session, author.id, "Candidate")
    await add_story(session, author.id, "Already curated", curated=True)
    dismissed = await add_story(session, author.id, "Dismissed")
    dismissed.museum_dismissed_at = datetime.now(UTC)
    await add_story(session, author.id, "Draft", status="draft")
    await session.commit()

    await sign_in(client, REVIEWER)
    page = (await client.get("/api/v1/staff/review")).json()
    assert [s["id"] for s in page["held"]] == [str(held.id)]
    entry = page["held"][0]
    assert entry["moderation"]["labels"][1] == {
        "label": "violence",
        "raised": True,
        "reason": 'The text mentions "kill".',
    }
    assert entry["layers"][0]["segments"][0]["text"] == "He would kill the wolf."
    assert entry["own"] is False
    assert [s["id"] for s in page["candidates"]] == [str(candidate.id)]
    assert [s["title"] for s in page["museum"]] == ["Already curated"]


# --- held stories ---


async def test_approving_publishes_a_held_story(client, session, author, staff):
    story = await add_story(session, author.id, status="held")
    await sign_in(client, REVIEWER)
    r = await client.post(f"/api/v1/staff/stories/{story.id}/approve")
    assert r.status_code == 200, r.text
    await session.refresh(story)
    assert story.status == "published" and story.published_at is not None
    assert story.reviewed_by == await user_id(session, REVIEWER)
    client.cookies.clear()
    assert (await client.get(f"/api/v1/stories/{story.id}")).status_code == 200


async def test_rejecting_sends_the_story_back_with_a_note(client, session, author, staff):
    story = await add_story(session, author.id, status="held")
    await sign_in(client, REVIEWER)
    r = await client.post(
        f"/api/v1/staff/stories/{story.id}/reject", json={"note": "Please soften line 1."}
    )
    assert r.status_code == 200, r.text
    await session.refresh(story)
    assert story.status == "needs_edit"
    assert story.review_note == "Please soften line 1."


async def test_rejecting_without_a_note_is_allowed(client, session, author, staff):
    story = await add_story(session, author.id, status="held")
    await sign_in(client, REVIEWER)
    r = await client.post(f"/api/v1/staff/stories/{story.id}/reject", json={})
    assert r.status_code == 200
    await session.refresh(story)
    assert story.status == "needs_edit" and story.review_note is None


async def test_only_held_stories_can_be_approved_or_rejected(client, session, author, staff):
    story = await add_story(session, author.id, status="draft")
    await sign_in(client, REVIEWER)
    assert (await client.post(f"/api/v1/staff/stories/{story.id}/approve")).status_code == 409
    assert (
        await client.post(f"/api/v1/staff/stories/{story.id}/reject", json={})
    ).status_code == 409


async def test_an_unknown_story_is_not_found(client, staff):
    await sign_in(client, REVIEWER)
    r = await client.post("/api/v1/staff/stories/00000000-0000-0000-0000-000000000000/approve")
    assert r.status_code == 404


# --- the museum ---


async def test_curating_adds_a_story_to_the_museum(client, session, author, staff):
    story = await add_story(session, author.id)
    await sign_in(client, REVIEWER)
    r = await client.post(f"/api/v1/staff/stories/{story.id}/curate")
    assert r.status_code == 200, r.text
    await session.refresh(story)
    assert story.curated_at is not None
    assert story.curated_by == await user_id(session, REVIEWER)
    feed = (await client.get("/api/v1/stories?curated=true")).json()["items"]
    assert [s["id"] for s in feed] == [str(story.id)]
    assert feed[0]["curated"] is True


async def test_only_published_stories_can_be_curated(client, session, author, staff):
    held = await add_story(session, author.id, status="held")
    curated = await add_story(session, author.id, curated=True)
    await sign_in(client, REVIEWER)
    assert (await client.post(f"/api/v1/staff/stories/{held.id}/curate")).status_code == 409
    assert (await client.post(f"/api/v1/staff/stories/{curated.id}/curate")).status_code == 409


async def test_not_now_removes_a_candidate_without_curating(client, session, author, staff):
    story = await add_story(session, author.id)
    await sign_in(client, REVIEWER)
    assert (await client.post(f"/api/v1/staff/stories/{story.id}/dismiss")).status_code == 200
    await session.refresh(story)
    assert story.curated_at is None and story.museum_dismissed_at is not None
    assert (await client.get("/api/v1/staff/review")).json()["candidates"] == []


async def test_an_admin_can_remove_a_story_from_the_museum(client, session, author, staff):
    story = await add_story(session, author.id, curated=True)
    await sign_in(client, ADMIN)
    r = await client.delete(f"/api/v1/staff/stories/{story.id}/curation")
    assert r.status_code == 200, r.text
    await session.refresh(story)
    assert story.curated_at is None and story.curated_by is None
    assert (await client.delete(f"/api/v1/staff/stories/{story.id}/curation")).status_code == 409
    # It does not come back as a candidate.
    assert (await client.get("/api/v1/staff/review")).json()["candidates"] == []


async def test_the_feed_can_list_only_curated_stories(client, session, author):
    await add_story(session, author.id, "Plain")
    await add_story(session, author.id, "In the museum", curated=True)
    everything = (await client.get("/api/v1/stories")).json()
    museum = (await client.get("/api/v1/stories?curated=true&limit=1")).json()
    assert len(everything["items"]) == 2 and everything["total"] == 2
    assert [s["title"] for s in museum["items"]] == ["In the museum"]
    assert museum["total"] == 1


# --- self-review ---


async def test_staff_cannot_act_on_their_own_stories(client, session, staff):
    reviewer = await user_id(session, REVIEWER)
    admin = await user_id(session, ADMIN)
    held = await add_story(session, reviewer, status="held")
    published = await add_story(session, reviewer)
    curated = await add_story(session, admin, curated=True)
    await sign_in(client, REVIEWER)
    for action in ("approve", "reject"):
        r = await client.post(f"/api/v1/staff/stories/{held.id}/{action}", json={})
        assert r.status_code == 403, action
        assert "your own" in r.json()["detail"]
    for action in ("curate", "dismiss"):
        r = await client.post(f"/api/v1/staff/stories/{published.id}/{action}")
        assert r.status_code == 403, action
    page = (await client.get("/api/v1/staff/review")).json()
    assert page["held"][0]["own"] is True
    await sign_in(client, ADMIN)
    assert (await client.delete(f"/api/v1/staff/stories/{curated.id}/curation")).status_code == 403
    await session.refresh(held)
    assert held.status == "held"
    assert await audit(session) == []


# --- audit ---


async def test_every_staff_action_is_audited(client, session, author, staff):
    held = await add_story(session, author.id, status="held")
    rejected = await add_story(session, author.id, status="held")
    candidate = await add_story(session, author.id)
    other = await add_story(session, author.id)
    await sign_in(client, REVIEWER)
    await client.post(f"/api/v1/staff/stories/{held.id}/approve")
    await client.post(f"/api/v1/staff/stories/{rejected.id}/reject", json={"note": "Fix it."})
    await client.post(f"/api/v1/staff/stories/{candidate.id}/curate")
    await client.post(f"/api/v1/staff/stories/{other.id}/dismiss")
    await sign_in(client, ADMIN)
    await client.delete(f"/api/v1/staff/stories/{candidate.id}/curation")

    events = await audit(session)
    reviewer, admin = await user_id(session, REVIEWER), await user_id(session, ADMIN)
    assert [(e.actor_id, e.action, e.target_id) for e in events] == [
        (reviewer, "approve", held.id),
        (reviewer, "reject", rejected.id),
        (reviewer, "curate", candidate.id),
        (reviewer, "dismiss", other.id),
        (admin, "uncurate", candidate.id),
    ]
    assert all(e.target_type == "story" and e.created_at for e in events)
    assert events[1].detail == {"note": "Fix it."}

    log = (await client.get("/api/v1/staff/audit")).json()
    assert [e["action"] for e in log] == ["uncurate", "dismiss", "curate", "reject", "approve"]
    assert log[0]["actor"]["display_name"] == "Adel Admin"
    assert log[0]["target"]["title"] == "A story"


# --- spending ---


async def test_the_spend_summary_totals_the_ledger(client, session, staff):
    def entry(provider, usd, state="committed", budget="card", actual=None, days_ago=0):
        return SpendEntry(
            provider=provider,
            operation="op",
            budget=budget,
            estimated_usd=Decimal(usd),
            actual_usd=Decimal(actual) if actual else None,
            state=state,
            created_at=datetime.now(UTC) - timedelta(days=days_ago),
        )

    session.add_all(
        [
            entry("elevenlabs", "1.50"),
            entry("elevenlabs", "0.50", actual="0.40"),
            entry("azure", "2.00", budget="azure"),
            entry("elevenlabs", "9.00", state="released"),  # never spent
            entry("fal", "0.25", state="reserved"),  # in flight, counts until settled
            entry("elevenlabs", "3.00", days_ago=2),  # not today
        ]
    )
    await session.commit()
    await sign_in(client, ADMIN)
    summary = (await client.get("/api/v1/staff/spend")).json()
    assert summary["total_usd"] == "7.15"
    # Today, as the daily cap counts it: the card budget only.
    assert summary["today_card_usd"] == "2.15"
    assert summary["card_usd"] == "5.15"
    assert summary["azure_usd"] == "2.00"
    assert {p["provider"]: p["usd"] for p in summary["by_provider"]} == {
        "azure": "2.00",
        "elevenlabs": "4.90",
        "fal": "0.25",
    }
    assert summary["card_cap_usd"] and summary["daily_cap_usd"]
