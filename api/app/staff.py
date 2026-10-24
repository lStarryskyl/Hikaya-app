"""The staff page: held stories and museum candidates, the museum itself, audit and spending.

Every route here is for reviewers and admins; removing a story from the museum, the audit log
and the spend summary are for admins only. Staff never act on their own stories, and every
action writes an audit event in the same transaction as the change it records.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import discover, stories
from app.auth import require_roles
from app.config import get_settings
from app.db import get_session
from app.gateway import ACTIVE
from app.models import AuditAction, AuditEvent, Role, SpendEntry, Story, StoryStatus, User

router = APIRouter(prefix="/staff", tags=["staff"])

staff_only = require_roles(Role.REVIEWER, Role.ADMIN)
admin_only = require_roles(Role.ADMIN)

LIST_LIMIT = 50
AUDIT_LIMIT = 100


class HeldStory(stories.StoryOut):
    # The reviewer wrote it, so another member of staff must decide.
    own: bool


class Candidate(discover.StoryCard):
    own: bool


class ReviewPage(BaseModel):
    held: list[HeldStory]
    # Published, not in the museum, not set aside.
    candidates: list[Candidate]
    museum: list[Candidate]


class RejectIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ActionOut(BaseModel):
    id: uuid.UUID
    status: str
    curated: bool


class PersonOut(BaseModel):
    id: uuid.UUID
    display_name: str


class TargetOut(BaseModel):
    type: str
    id: uuid.UUID
    title: str | None  # None once the story has been deleted


class AuditOut(BaseModel):
    id: uuid.UUID
    action: str
    actor: PersonOut | None
    target: TargetOut
    detail: dict | None
    at: datetime


class ProviderSpend(BaseModel):
    provider: str
    usd: str


class SpendSummary(BaseModel):
    total_usd: str
    today_usd: str
    card_usd: str
    azure_usd: str
    by_provider: list[ProviderSpend]
    card_cap_usd: str
    daily_cap_usd: str
    azure_cap_usd: str


# --- reading ---


async def _cards(session: AsyncSession, rows: list[Story], user: User) -> list[Candidate]:
    cards = await discover.cards_for(session, rows)
    return [
        Candidate(**card.model_dump(), own=row.author_id == user.id)
        for card, row in zip(cards, rows, strict=True)
    ]


@router.get("/review", response_model=ReviewPage)
async def review_page(
    user: User = Depends(staff_only), session: AsyncSession = Depends(get_session)
) -> ReviewPage:
    async def find(*conditions, order) -> list[Story]:
        query = select(Story).where(*conditions).order_by(order).limit(LIST_LIMIT)
        return list((await session.execute(query)).scalars())

    held = await find(Story.status == StoryStatus.HELD, order=Story.updated_at.asc())
    published = Story.status == StoryStatus.PUBLISHED
    candidates = await find(
        published,
        Story.curated_at.is_(None),
        Story.museum_dismissed_at.is_(None),
        order=Story.published_at.desc(),
    )
    museum = await find(published, Story.curated_at.is_not(None), order=Story.curated_at.desc())
    return ReviewPage(
        held=[
            HeldStory(
                **(await stories.to_out(session, s, private=True)).model_dump(),
                own=s.author_id == user.id,
            )
            for s in held
        ],
        candidates=await _cards(session, candidates, user),
        museum=await _cards(session, museum, user),
    )


# --- acting ---


async def _story_for_action(session: AsyncSession, story_id: str, user: User) -> Story:
    """The story, locked until commit so two staff cannot act on it at once."""
    story = await session.get(Story, stories._parse_id(story_id), with_for_update=True)
    if story is None:
        raise HTTPException(404, "Story not found.")
    if story.author_id == user.id:
        raise HTTPException(403, "This is your own story; another member of staff must decide.")
    return story


def _require(story: Story, ok: bool, message: str) -> None:
    if not ok:
        raise HTTPException(409, message)


async def _done(
    session: AsyncSession,
    story: Story,
    user: User,
    action: AuditAction,
    detail: dict | None = None,
) -> ActionOut:
    session.add(
        AuditEvent(
            actor_id=user.id,
            action=action.value,
            target_type="story",
            target_id=story.id,
            detail=detail,
        )
    )
    await session.commit()
    return ActionOut(id=story.id, status=story.status, curated=story.curated_at is not None)


@router.post("/stories/{story_id}/approve", response_model=ActionOut)
async def approve(
    story_id: str, user: User = Depends(staff_only), session: AsyncSession = Depends(get_session)
) -> ActionOut:
    """The label was wrong: publish the held story."""
    story = await _story_for_action(session, story_id, user)
    _require(story, story.status == StoryStatus.HELD, "Only a held story can be approved.")
    now = datetime.now(UTC)
    story.status, story.published_at = StoryStatus.PUBLISHED.value, now
    story.reviewed_at, story.reviewed_by, story.review_note = now, user.id, None
    return await _done(session, story, user, AuditAction.APPROVE)


@router.post("/stories/{story_id}/reject", response_model=ActionOut)
async def reject(
    story_id: str,
    body: RejectIn | None = None,
    user: User = Depends(staff_only),
    session: AsyncSession = Depends(get_session),
) -> ActionOut:
    """Keep the story unpublished and send it back to the author, with an optional note."""
    story = await _story_for_action(session, story_id, user)
    _require(story, story.status == StoryStatus.HELD, "Only a held story can be sent back.")
    note = ((body.note if body else None) or "").strip() or None
    story.status = StoryStatus.NEEDS_EDIT.value
    story.reviewed_at, story.reviewed_by, story.review_note = datetime.now(UTC), user.id, note
    return await _done(session, story, user, AuditAction.REJECT, {"note": note} if note else None)


@router.post("/stories/{story_id}/curate", response_model=ActionOut)
async def curate(
    story_id: str, user: User = Depends(staff_only), session: AsyncSession = Depends(get_session)
) -> ActionOut:
    story = await _story_for_action(session, story_id, user)
    _require(
        story,
        story.status == StoryStatus.PUBLISHED and story.curated_at is None,
        "Only a published story that is not in the museum can be curated.",
    )
    story.curated_at, story.curated_by = datetime.now(UTC), user.id
    story.museum_dismissed_at = story.museum_dismissed_by = None
    return await _done(session, story, user, AuditAction.CURATE)


@router.post("/stories/{story_id}/dismiss", response_model=ActionOut)
async def dismiss(
    story_id: str, user: User = Depends(staff_only), session: AsyncSession = Depends(get_session)
) -> ActionOut:
    """ "Not now": the story leaves the candidates without joining the museum."""
    story = await _story_for_action(session, story_id, user)
    _require(
        story,
        story.status == StoryStatus.PUBLISHED and story.curated_at is None,
        "Only a museum candidate can be set aside.",
    )
    story.museum_dismissed_at, story.museum_dismissed_by = datetime.now(UTC), user.id
    return await _done(session, story, user, AuditAction.DISMISS)


@router.delete("/stories/{story_id}/curation", response_model=ActionOut)
async def uncurate(
    story_id: str, user: User = Depends(admin_only), session: AsyncSession = Depends(get_session)
) -> ActionOut:
    story = await _story_for_action(session, story_id, user)
    _require(story, story.curated_at is not None, "This story is not in the museum.")
    story.curated_at = story.curated_by = None
    return await _done(session, story, user, AuditAction.UNCURATE)


# --- admin: audit and spending ---


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    _: User = Depends(admin_only), session: AsyncSession = Depends(get_session)
) -> list[AuditOut]:
    """The latest staff actions, newest first."""
    rows = (
        await session.execute(
            select(AuditEvent, User, Story)
            .outerjoin(User, User.id == AuditEvent.actor_id)
            .outerjoin(Story, Story.id == AuditEvent.target_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(AUDIT_LIMIT)
        )
    ).all()
    return [
        AuditOut(
            id=event.id,
            action=event.action,
            actor=PersonOut(id=actor.id, display_name=actor.display_name) if actor else None,
            target=TargetOut(
                type=event.target_type, id=event.target_id, title=story.title if story else None
            ),
            detail=event.detail,
            at=event.created_at,
        )
        for event, actor, story in rows
    ]


def _usd(value) -> str:
    return f"{Decimal(value or 0):.2f}"


@router.get("/spend", response_model=SpendSummary)
async def spend_summary(
    _: User = Depends(admin_only), session: AsyncSession = Depends(get_session)
) -> SpendSummary:
    """What paid providers have cost, counted as the ledger counts it against the caps:
    settled calls at their cost, calls in flight at their reservation."""
    spent = func.coalesce(
        func.sum(func.coalesce(SpendEntry.actual_usd, SpendEntry.estimated_usd)), 0
    )
    active = SpendEntry.state.in_(ACTIVE)

    async def total(*conditions) -> Decimal:
        return (await session.execute(select(spent).where(active, *conditions))).scalar_one()

    by_provider = (
        await session.execute(
            select(SpendEntry.provider, spent)
            .where(active)
            .group_by(SpendEntry.provider)
            .order_by(SpendEntry.provider)
        )
    ).all()
    settings = get_settings()
    return SpendSummary(
        total_usd=_usd(await total()),
        today_usd=_usd(await total(SpendEntry.created_at >= func.date_trunc("day", func.now()))),
        card_usd=_usd(await total(SpendEntry.budget == "card")),
        azure_usd=_usd(await total(SpendEntry.budget == "azure")),
        by_provider=[ProviderSpend(provider=p, usd=_usd(v)) for p, v in by_provider],
        card_cap_usd=_usd(settings.spend_cap_usd_total),
        daily_cap_usd=_usd(settings.spend_cap_usd_daily),
        azure_cap_usd=_usd(settings.spend_cap_usd_azure),
    )
