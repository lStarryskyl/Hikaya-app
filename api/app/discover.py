"""Public reads for Home, Feed and Explore: the feed, map pins and places."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Place, PlacePhoto, Story, StoryStatus, TextLayer, User
from app.places import PhotoOut, cover_for, photo_out

router = APIRouter(tags=["discover"])

RECENT_DAYS = 14


class AuthorOut(BaseModel):
    id: uuid.UUID
    display_name: str


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
    kind: str  # featured | recent | ordinary


class PlaceOut(BaseModel):
    slug: str
    name: str
    latitude: float
    longitude: float
    cover: PhotoOut | None
    photos: list[PhotoOut]
    story_count: int


def pin_kind(story: Story, now: datetime) -> str:
    if story.curated_at is not None:
        return "featured"
    if story.published_at and story.published_at >= now - timedelta(days=RECENT_DAYS):
        return "recent"
    return "ordinary"


async def excerpt_for(session: AsyncSession, story: Story) -> str:
    """The first English line, else the first polished line."""
    rows = {
        layer.kind: layer
        for layer in (
            await session.execute(
                select(TextLayer).where(
                    TextLayer.story_id == story.id,
                    TextLayer.kind.in_(["translation_en", "polished"]),
                )
            )
        ).scalars()
    }
    layer = rows.get("translation_en") or rows.get("polished")
    return layer.segments[0]["text"] if layer and layer.segments else ""


async def card_for(session: AsyncSession, story: Story) -> StoryCard:
    author = await session.get(User, story.author_id)
    cover = await cover_for(session, story)
    return StoryCard(
        id=story.id,
        title=story.title,
        category=story.category,
        place_name=story.place_name,
        latitude=story.latitude,
        longitude=story.longitude,
        duration_ms=story.duration_ms,
        published_at=story.published_at,
        curated=story.curated_at is not None,
        author=AuthorOut(id=author.id, display_name=author.display_name),
        excerpt=await excerpt_for(session, story),
        cover=photo_out(cover) if cover else None,
    )


def _encode_cursor(story: Story) -> str:
    raw = json.dumps([story.published_at.isoformat(), str(story.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        published_at, story_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(published_at), uuid.UUID(story_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "That page link is not valid.") from exc


@router.get("/stories", response_model=FeedPage)
async def feed(
    limit: int = Query(12, ge=1, le=100),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> FeedPage:
    """Published stories, newest first. Pass `next_cursor` back to get the next page."""
    query = select(Story).where(Story.status == StoryStatus.PUBLISHED)
    if cursor:
        published_at, story_id = _decode_cursor(cursor)
        query = query.where(tuple_(Story.published_at, Story.id) < (published_at, story_id))
    query = query.order_by(Story.published_at.desc(), Story.id.desc()).limit(limit + 1)
    stories = list((await session.execute(query)).scalars())
    more = len(stories) > limit
    stories = stories[:limit]
    return FeedPage(
        items=[await card_for(session, s) for s in stories],
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
    out = []
    for place in (await session.execute(select(Place).order_by(Place.sort_order))).scalars():
        photos = (
            await session.execute(
                select(PlacePhoto)
                .where(PlacePhoto.place_slug == place.slug)
                .order_by(PlacePhoto.sort_order)
            )
        ).scalars()
        photos = [photo_out(p) for p in photos]
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
