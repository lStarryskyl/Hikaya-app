"""Looking up a story's stored files by kind."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, AssetKind


async def asset_of(session: AsyncSession, story_id: uuid.UUID, kind: AssetKind) -> Asset | None:
    """The story's file of this kind; each kind has at most one."""
    return (
        await session.execute(select(Asset).where(Asset.story_id == story_id, Asset.kind == kind))
    ).scalar_one_or_none()
