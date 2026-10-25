"""Public reads for Home, Feed and Explore: the feed, map pins and places."""

import base64
import binascii
import hashlib
import json
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Text, cast, column, func, or_, select, true, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app import search
from app.db import get_session
from app.models import Category, Place, PlacePhoto, Story, StoryStatus, TextLayer, User
from app.photos import covers_for
from app.pipeline import POLISHED, TARGET_LAYER
from app.places import PhotoOut, photo_out
from app.stories import AuthorOut
from app.tags import normalize_tag

router = APIRouter(tags=["discover"])

RECENT_DAYS = 14
PinKind = Literal["featured", "recent", "ordinary"]
# A card's excerpt is the first English line, else the first polished line.
EXCERPT_LAYERS = (TARGET_LAYER["english"], POLISHED)


class StoryCard(BaseModel):
    tags: list[str] = []
    distance_km: float | None = None
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
    # How many stories match, across all pages.
    total: int
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
            tags=s.tags,
            place_name=s.place_name,
            latitude=s.latitude,
            longitude=s.longitude,
            duration_ms=s.duration_ms,
            published_at=s.published_at,
            curated=s.curated_at is not None,
            author=AuthorOut(id=s.author_id, display_name=authors[s.author_id].display_name),
            excerpt=excerpt(s.id),
            cover=covers[s.id],
        )
        for s in stories
    ]


class DiscoveryFilters:
    """The same validated filters drive cards, totals and map pins."""

    def __init__(
        self,
        q: str = Query("", max_length=200),
        category: Annotated[list[Category] | None, Query()] = None,
        tag: Annotated[list[str] | None, Query(max_length=10)] = None,
        curated: bool = False,
        latitude: float | None = Query(None, ge=-90, le=90),
        longitude: float | None = Query(None, ge=-180, le=180),
        radius_km: float | None = Query(None, ge=1, le=500),
    ):
        if (latitude is None) != (longitude is None) or (
            radius_km is not None and latitude is None
        ):
            raise HTTPException(422, "Nearby search needs both latitude and longitude.")
        self.q = q.strip()
        self.category = sorted(set(category or []))
        try:
            self.tags = sorted({normalize_tag(t) for t in (tag or [])})
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        self.curated = curated
        self.latitude, self.longitude = latitude, longitude
        self.radius = (radius_km or 25) if latitude is not None else None

    @property
    def fingerprint(self) -> str:
        data = [
            self.q,
            self.category,
            self.tags,
            self.curated,
            self.latitude,
            self.longitude,
            self.radius,
        ]
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()[:24]

    def distance(self):
        if self.latitude is None:
            return None
        # Clamp the haversine term: floating point rounding must not make asin invalid.
        a = func.power(func.sin(func.radians(Story.latitude - self.latitude) / 2), 2)
        a += (
            func.cos(func.radians(self.latitude))
            * func.cos(func.radians(Story.latitude))
            * func.power(func.sin(func.radians(Story.longitude - self.longitude) / 2), 2)
        )
        return 12742.0 * func.asin(func.sqrt(func.least(1.0, func.greatest(0.0, a))))

    def query(self):
        query = select(Story).where(
            Story.status == StoryStatus.PUBLISHED, Story.published_at.is_not(None)
        )
        if self.curated:
            query = query.where(Story.curated_at.is_not(None))
        if self.category:
            query = query.where(Story.category.in_(self.category))
        if self.tags:
            query = query.where(Story.tags.contains(self.tags))
        if self.q:
            # Search the actual segment texts, not JSON keys or timestamps.
            segments = func.jsonb_array_elements(TextLayer.segments).table_valued(column("value"))
            text_match = (
                select(1)
                .select_from(TextLayer)
                .join(segments, true())
                .where(
                    TextLayer.story_id == Story.id,
                    cast(segments.c.value.op("->>")("text"), Text).icontains(
                        self.q, autoescape=True
                    ),
                )
                .exists()
            )
            author_match = (
                select(1)
                .where(
                    User.id == Story.author_id, User.display_name.icontains(self.q, autoescape=True)
                )
                .exists()
            )
            # Other word forms too (Arabic and English stemming), on indexed columns.
            layer_words = (
                select(1)
                .where(TextLayer.story_id == Story.id, search.layer_matches(self.q))
                .exists()
            )
            query = query.where(
                or_(
                    Story.title.icontains(self.q, autoescape=True),
                    Story.place_name.icontains(self.q, autoescape=True),
                    author_match,
                    text_match,
                    search.story_matches(self.q),
                    layer_words,
                )
            )
        if self.latitude is not None:
            query = query.where(
                Story.latitude.is_not(None),
                Story.longitude.is_not(None),
                self.distance() <= self.radius,
            )
        return query


def _encode_cursor(story: Story, filters: DiscoveryFilters, distance: float | None) -> str:
    raw = [filters.fingerprint, story.published_at.isoformat(), str(story.id), distance]
    return base64.urlsafe_b64encode(json.dumps(raw).encode()).decode()


def _decode_cursor(cursor: str, filters: DiscoveryFilters):
    try:
        fingerprint, published_at, story_id, distance = json.loads(
            base64.b64decode(cursor.encode(), altchars=b"-_", validate=True)
        )
        when = datetime.fromisoformat(published_at)
        if when.tzinfo is None or fingerprint != filters.fingerprint:
            raise ValueError("cursor does not match filters")
        if filters.latitude is not None:
            if (
                not isinstance(distance, (int, float))
                or not math.isfinite(distance)
                or distance < 0
            ):
                raise ValueError("invalid distance")
        elif distance is not None:
            raise ValueError("unexpected distance")
        return when, uuid.UUID(story_id), distance
    except (ValueError, TypeError, binascii.Error, OverflowError) as exc:
        raise HTTPException(422, "That page link is not valid for this search.") from exc


@router.get("/stories", response_model=FeedPage)
async def feed(
    limit: int = Query(12, ge=1, le=100),
    cursor: str | None = Query(None, max_length=1000),
    filters: DiscoveryFilters = Depends(),
    session: AsyncSession = Depends(get_session),
) -> FeedPage:
    query = filters.query()
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    distance = filters.distance()
    if cursor:
        published_at, story_id, cursor_distance = _decode_cursor(cursor, filters)
        after = tuple_(Story.published_at, Story.id) < (published_at, story_id)
        if distance is not None:
            after = or_(distance > cursor_distance, (distance == cursor_distance) & after)
        query = query.where(after)
    order = [Story.published_at.desc(), Story.id.desc()]
    if distance is not None:
        query = query.add_columns(distance.label("distance_km"))
        order.insert(0, distance.asc())
    rows = (await session.execute(query.order_by(*order).limit(limit + 1))).all()
    more = len(rows) > limit
    rows = rows[:limit]
    cards = await cards_for(session, [row[0] for row in rows])
    if distance is not None:
        for card, row in zip(cards, rows, strict=True):
            card.distance_km = row[1]
    return FeedPage(
        items=cards,
        next_cursor=_encode_cursor(
            rows[-1][0], filters, rows[-1][1] if distance is not None else None
        )
        if more
        else None,
        total=total,
    )


@router.get("/map/pins", response_model=list[PinOut])
async def map_pins(
    filters: DiscoveryFilters = Depends(), session: AsyncSession = Depends(get_session)
) -> list[PinOut]:
    now = datetime.now(UTC)
    stories = (
        await session.execute(
            filters.query().where(Story.latitude.is_not(None), Story.longitude.is_not(None))
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
