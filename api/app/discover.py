"""Public reads for Home, Feed and Explore: the feed, map pins and places."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Place, PlacePhoto, Story, StoryStatus, TextLayer, User
from app.pipeline import POLISHED, TARGET_LAYER
from app.places import PhotoOut, covers_for, photo_out
from app.stories import AuthorOut

router = APIRouter(tags=["discover"])

RECENT_DAYS = 14
PinKind = Literal["featured", "recent", "ordinary"]
# A card's excerpt is the first English line, else the first polished line.
EXCERPT_LAYERS = (TARGET_LAYER["english"], POLISHED)


class StoryCard(BaseModel):
    id: uuid.UUID
    title: str
    category: str | None
    place_name: str
    latitude: float | None
    longitude: float | None
    duration_ms: int | None
    published_at: datetime | None
    curated: bool
    author: AuthorOut
    excerpt: str
    cover: PhotoOut | None


class FeedPage(BaseModel):
    items: list[StoryCard]
    next_cursor: str | None


class PinOut(BaseModel):
    story_id: uuid.UUID
    title: str
    place_name: str
    category: str | None
    latitude: float
    longitude: float
    kind: PinKind


class PlaceOut(BaseModel):
    slug: str
    name: str
    latitude: float
    longitude: float
    cover: PhotoOut | None
    photos: list[PhotoOut]
    story_count: int


def pin_kind(story: Story, now: datetime) -> PinKind:
    if story.curated_at is not None:
        return "featured"
    if story.published_at and story.published_at >= now - timedelta(days=RECENT_DAYS):
        return "recent"
    return "ordinary"


async def cards_for(session: AsyncSession, stories: list[Story]) -> list[StoryCard]:
    """Cards for many stories in a fixed number of queries (authors, excerpts, covers)."""
    if not stories:
        return []
    ids = [s.id for s in stories]
    authors = {
        u.id: u
        for u in (
            await session.execute(select(User).where(User.id.in_({s.author_id for s in stories})))
        ).scalars()
    }
    layers: dict[uuid.UUID, dict[str, TextLayer]] = {}
    for layer in (
        await session.execute(
            select(TextLayer).where(TextLayer.story_id.in_(ids), TextLayer.kind.in_(EXCERPT_LAYERS))
        )
    ).scalars():
        layers.setdefault(layer.story_id, {})[layer.kind] = layer
    covers = await covers_for(session, stories)

    def excerpt(story_id: uuid.UUID) -> str:
        found = layers.get(story_id, {})
        layer = next((found[k] for k in EXCERPT_LAYERS if k in found), None)
        return layer.segments[0]["text"] if layer and layer.segments else ""

    return [
        StoryCard(
            id=s.id,
            title=s.title,
            category=s.category,
            place_name=s.place_name,
            latitude=s.latitude,
            longitude=s.longitude,
            duration_ms=s.duration_ms,
            published_at=s.published_at,
            curated=s.curated_at is not None,
            author=AuthorOut(id=s.author_id, display_name=authors[s.author_id].display_name),
            excerpt=excerpt(s.id),
            cover=photo_out(covers[s.id]) if covers[s.id] else None,
        )
        for s in stories
    ]


def _encode_cursor(story: Story) -> str:
    raw = json.dumps([story.published_at.isoformat(), str(story.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        published_at, story_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        when = datetime.fromisoformat(published_at)
        if when.tzinfo is None:
            raise ValueError("cursor time without a timezone")
        return when, uuid.UUID(story_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "That page link is not valid.") from exc


@router.get("/stories", response_model=FeedPage)
async def feed(
    limit: int = Query(12, ge=1, le=100),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> FeedPage:
    """Published stories, newest first. Pass `next_cursor` back to get the next page."""
    query = select(Story).where(
        Story.status == StoryStatus.PUBLISHED, Story.published_at.is_not(None)
    )
    if cursor:
        published_at, story_id = _decode_cursor(cursor)
        query = query.where(tuple_(Story.published_at, Story.id) < (published_at, story_id))
    query = query.order_by(Story.published_at.desc(), Story.id.desc()).limit(limit + 1)
    stories = list((await session.execute(query)).scalars())
    more = len(stories) > limit
    stories = stories[:limit]
    return FeedPage(
        items=await cards_for(session, stories),
        next_cursor=_encode_cursor(stories[-1]) if more else None,
    )


@router.get("/map/pins", response_model=list[PinOut])
async def map_pins(session: AsyncSession = Depends(get_session)) -> list[PinOut]:
    now = datetime.now(UTC)
    stories = (
        await session.execute(
            select(Story).where(
                Story.status == StoryStatus.PUBLISHED,
                Story.latitude.is_not(None),
                Story.longitude.is_not(None),
            )
        )
    ).scalars()
    return [
        PinOut(
            story_id=s.id,
            title=s.title,
            place_name=s.place_name,
            category=s.category,
            latitude=s.latitude,
            longitude=s.longitude,
            kind=pin_kind(s, now),
        )
        for s in stories
    ]


@router.get("/places", response_model=list[PlaceOut])
async def list_places(session: AsyncSession = Depends(get_session)) -> list[PlaceOut]:
    counts = dict(
        (
            await session.execute(
                select(Story.place_slug, func.count())
                .where(Story.status == StoryStatus.PUBLISHED, Story.place_slug.is_not(None))
                .group_by(Story.place_slug)
            )
        ).all()
    )
    by_place: dict[str, list[PhotoOut]] = {}
    for photo in (
        await session.execute(select(PlacePhoto).order_by(PlacePhoto.sort_order))
    ).scalars():
        by_place.setdefault(photo.place_slug, []).append(photo_out(photo))
    out = []
    for place in (await session.execute(select(Place).order_by(Place.sort_order))).scalars():
        photos = by_place.get(place.slug, [])
        cover = next((p for p in photos if p.slug == place.cover_photo_slug), None)
        out.append(
            PlaceOut(
                slug=place.slug,
                name=place.name,
                latitude=place.latitude,
                longitude=place.longitude,
                cover=cover,
                photos=photos,
                story_count=counts.get(place.slug, 0),
            )
        )
    return out
