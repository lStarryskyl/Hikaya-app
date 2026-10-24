"""Feed, map pins and places: the public reads behind Home, Feed and Explore."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Story, User


@pytest.fixture
async def author(session):
    user = User(email="teller@example.com", display_name="Um Ahmad", password_hash="!")
    session.add(user)
    await session.commit()
    return user


async def add_story(session, author, title, *, days_ago=None, status="published", curated=False,
                    lat=31.7, lng=35.8):  # fmt: skip
    now = datetime.now(UTC)
    story = Story(
        author_id=author.id,
        title=title,
        category="folklore",
        place_name="Madaba",
        latitude=lat,
        longitude=lng,
        original_language="jordanian",
        status=status,
        published_at=None if days_ago is None else now - timedelta(days=days_ago),
        curated_at=now if curated else None,
    )
    session.add(story)
    await session.commit()
    return story


async def test_feed_lists_published_stories_newest_first(client, session, author):
    await add_story(session, author, "Old", days_ago=30)
    await add_story(session, author, "New", days_ago=1)
    await add_story(session, author, "Middle", days_ago=10)
    await add_story(session, author, "A draft", status="draft")
    r = await client.get("/api/v1/stories")
    assert r.status_code == 200
    body = r.json()
    assert [s["title"] for s in body["items"]] == ["New", "Middle", "Old"]
    assert body["next_cursor"] is None
    card = body["items"][0]
    assert card["author"]["display_name"] == "Um Ahmad"
    assert {"id", "title", "category", "place_name", "published_at", "excerpt", "cover",
            "curated", "duration_ms", "latitude", "longitude"} <= set(card)  # fmt: skip


async def test_feed_pages_with_a_cursor(client, session, author):
    titles = [f"Story {i}" for i in range(7)]
    for i, title in enumerate(titles):
        await add_story(session, author, title, days_ago=i)
    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        body = (await client.get("/api/v1/stories", params=params)).json()
        seen += [s["title"] for s in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == titles  # newest first, nothing repeated or skipped
    assert pages == 3


async def test_stories_published_at_the_same_moment_still_page_correctly(client, session, author):
    same = datetime.now(UTC) - timedelta(days=2)
    ids = set()
    for i in range(4):
        story = await add_story(session, author, f"Twin {i}", days_ago=2)
        story.published_at = same
        ids.add(str(story.id))
    await session.commit()
    first = (await client.get("/api/v1/stories", params={"limit": 2})).json()
    second = (
        await client.get("/api/v1/stories", params={"limit": 2, "cursor": first["next_cursor"]})
    ).json()
    assert {s["id"] for s in first["items"] + second["items"]} == ids


@pytest.mark.parametrize("params", [{"cursor": "not-a-cursor"}, {"limit": 0}, {"limit": 101}])
async def test_bad_feed_parameters_are_refused(client, params):
    assert (await client.get("/api/v1/stories", params=params)).status_code == 422


async def test_map_pins_have_kinds(client, session, author):
    featured = await add_story(session, author, "Curated", days_ago=60, curated=True)
    recent = await add_story(session, author, "Fresh", days_ago=3)
    ordinary = await add_story(session, author, "Older", days_ago=40)
    await add_story(session, author, "Draft", status="draft")
    await add_story(session, author, "No pin", days_ago=1, lat=None, lng=None)
    r = await client.get("/api/v1/map/pins")
    assert r.status_code == 200
    kinds = {p["story_id"]: p["kind"] for p in r.json()}
    assert kinds == {
        str(featured.id): "featured",
        str(recent.id): "recent",
        str(ordinary.id): "ordinary",
    }
    pin = next(p for p in r.json() if p["story_id"] == str(recent.id))
    assert pin["title"] == "Fresh"
    assert pin["latitude"] == 31.7 and pin["longitude"] == 35.8


async def test_a_story_card_says_whether_it_is_curated(client, session, author):
    await add_story(session, author, "Curated", days_ago=5, curated=True)
    card = (await client.get("/api/v1/stories")).json()["items"][0]
    assert card["curated"] is True


async def test_an_empty_feed_is_not_an_error(client):
    body = (await client.get("/api/v1/stories")).json()
    assert body == {"items": [], "next_cursor": None, "total": 0}


async def test_a_cursor_without_a_timezone_is_refused(client):
    import base64
    import json

    raw = json.dumps(["2026-01-01T00:00:00", str(uuid.uuid4())]).encode()
    cursor = base64.urlsafe_b64encode(raw).decode()
    assert (await client.get("/api/v1/stories", params={"cursor": cursor})).status_code == 422


async def test_a_full_feed_page_takes_a_handful_of_queries(client, session, author):
    """Cards are loaded in batches, not one story at a time."""
    from sqlalchemy import event

    from app.db import get_engine

    for i in range(20):
        await add_story(session, author, f"Story {i}", days_ago=i)
    statements = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(get_engine().sync_engine, "before_cursor_execute", listener)
    try:
        r = await client.get("/api/v1/stories", params={"limit": 20})
    finally:
        event.remove(get_engine().sync_engine, "before_cursor_execute", listener)
    assert len(r.json()["items"]) == 20
    assert len(statements) <= 8, statements
