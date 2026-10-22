"""Load the demo: places and photos, storytellers, and seven published stories.

    python -m app.seed_demo

Safe to run on every start: rows are matched by fixed keys and refreshed, and photo
conversions already on disk are reused. Photos whose source file is missing are skipped.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import places
from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.demo_data import PLACES, STORIES, STORYTELLERS, StorySeed
from app.models import PipelineStep, Place, PlacePhoto, Story, TextLayer, User
from app.pipeline import TARGET_LAYER, TARGETS
from app.storage import get_storage

log = logging.getLogger("hikaya.seed_demo")

# Fixed ids, so re-running updates the same stories instead of adding new ones.
STORY_NAMESPACE = uuid.UUID("5d1c0d3e-3a7f-4c55-9b4e-6b1a2f0c9e11")
STORYTELLER_DOMAIN = "storytellers.hikaya.invalid"
NO_PASSWORD = "!"  # never matches: verify_password rejects it, so these accounts cannot sign in
DEFAULT_PHOTO_DIR = Path(__file__).resolve().parent.parent / "seed" / "places"


def story_id(key: str) -> uuid.UUID:
    return uuid.uuid5(STORY_NAMESPACE, key)


def storyteller_email(key: str) -> str:
    return f"{key}@{STORYTELLER_DOMAIN}"


def _punctuate(text: str) -> str:
    return text if text.endswith((".", "!", "?", "؟")) else f"{text}."


def _layers(seed: StorySeed) -> dict[str, tuple[str, list[str]]]:
    """kind -> (language, texts)."""
    original = [line[seed.language] for line in seed.lines]
    out = {
        "verbatim": (seed.language, original),
        "polished": (seed.language, [_punctuate(t) for t in original]),
    }
    for target in TARGETS[seed.language]:
        out[TARGET_LAYER[target]] = (target, [_punctuate(line[target]) for line in seed.lines])
    return out


def _timing(count: int, duration_ms: int) -> list[tuple[int, int]]:
    step = duration_ms // count
    return [(i * step, duration_ms if i == count - 1 else (i + 1) * step) for i in range(count)]


async def _seed_places(session: AsyncSession, photo_dir: Path) -> set[str]:
    storage = get_storage()
    available: set[str] = set()
    for order, seed in enumerate(PLACES):
        place = await session.get(Place, seed.slug) or Place(slug=seed.slug)
        place.name, place.latitude, place.longitude = seed.name, seed.latitude, seed.longitude
        place.sort_order = order
        session.add(place)
        await session.flush()
        for photo_order, (slug, caption) in enumerate(seed.photos):
            source = places.find_source(photo_dir, slug)
            if source is None:
                log.warning("No source file for photo %s in %s; skipped.", slug, photo_dir)
                continue
            widths = await places.convert(source, slug, storage)
            photo = await session.get(PlacePhoto, slug) or PlacePhoto(slug=slug)
            photo.place_slug, photo.caption = seed.slug, caption
            photo.sort_order, photo.widths = photo_order, widths
            session.add(photo)
            available.add(slug)
        present = [slug for slug, _ in seed.photos if slug in available]
        place.cover_photo_slug = (
            seed.cover if seed.cover in available else next(iter(present), None)
        )
    await session.flush()
    return available


async def _seed_storytellers(session: AsyncSession) -> dict[str, uuid.UUID]:
    ids = {}
    for seed in STORYTELLERS:
        email = storyteller_email(seed.key)
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, display_name=seed.display_name, password_hash=NO_PASSWORD)
            session.add(user)
        user.display_name, user.password_hash = seed.display_name, NO_PASSWORD
        await session.flush()
        ids[seed.key] = user.id
    return ids


async def _seed_stories(
    session: AsyncSession, authors: dict[str, uuid.UUID], photos: set[str]
) -> None:
    now = datetime.now(UTC)
    for seed in STORIES:
        sid = story_id(seed.key)
        story = await session.get(Story, sid) or Story(id=sid)
        story.author_id = authors[seed.storyteller]
        story.title, story.category = seed.title, seed.category
        story.place_slug = seed.place
        story.place_name = next(p.name for p in PLACES if p.slug == seed.place)
        story.latitude, story.longitude = seed.latitude, seed.longitude
        story.original_language, story.duration_ms = seed.language, seed.duration_ms
        story.status = "published"
        # Relative to today, so "recently added" stays true for the demo whenever it runs.
        story.published_at = now - timedelta(days=seed.published_days_ago)
        story.cover_photo_slug = seed.cover if seed.cover in photos else None
        if seed.curated:
            story.curated_at = story.curated_at or story.published_at
        else:
            story.curated_at = None
        session.add(story)
        await session.flush()

        await session.execute(delete(TextLayer).where(TextLayer.story_id == sid))
        await session.execute(delete(PipelineStep).where(PipelineStep.story_id == sid))
        timing = _timing(len(seed.lines), seed.duration_ms)
        for kind, (language, texts) in _layers(seed).items():
            session.add(
                TextLayer(
                    story_id=sid,
                    kind=kind,
                    language=language,
                    segments=[
                        {"start_ms": start, "end_ms": end, "text": text}
                        for (start, end), text in zip(timing, texts, strict=True)
                    ],
                )
            )


async def seed_demo(
    sessionmaker: async_sessionmaker[AsyncSession], photo_dir: Path = DEFAULT_PHOTO_DIR
) -> None:
    async with sessionmaker() as session:
        photos = await _seed_places(session, photo_dir)
        authors = await _seed_storytellers(session)
        await _seed_stories(session, authors, photos)
        await session.commit()
    log.info(
        "Demo data ready: %d places, %d photos, %d stories.", len(PLACES), len(photos), len(STORIES)
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not get_settings().seed_demo_data:
        log.info("SEED_DEMO_DATA is off; nothing to load.")
    else:
        await seed_demo(get_sessionmaker())
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
