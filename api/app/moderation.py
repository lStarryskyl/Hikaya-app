"""Automated moderation when a member submits a story.

The language model judges the polished text and, for Arabic stories, the English
translation. No raised label publishes the story at once; any raised label holds it for
staff (two-tier publishing, docs/DECISIONS.md). The check is a pipeline step ("moderate"),
so a failure shows in the story's progress and can be retried.
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import gateway
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import UserFacingError
from app.handlers import handler
from app.models import ModerationResult, Story, StoryStatus
from app.pipeline import (
    POLISHED,
    STALE,
    TARGET_LAYER,
    get_layer,
    is_current,
    queue_step,
    step_done,
    step_hash,
)
from app.providers import MODERATION_LABELS, language_model

STEP = "moderate"
ENGLISH = TARGET_LAYER["english"]


class TextNotReady(UserFacingError):
    """The text to judge is missing or still being worked on."""


async def judged_texts(session: AsyncSession, story: Story) -> list[str]:
    """The polished text, plus the English translation when the story is not in English."""
    polished = await get_layer(session, story.id, POLISHED)
    english = await get_layer(session, story.id, ENGLISH)
    if polished is None or (story.original_language != "english" and english is None):
        raise TextNotReady("The story needs its polished text and English translation first.")
    texts = [s["text"] for s in polished.segments]
    if english is not None:
        texts += [s["text"] for s in english.segments]
    return texts


async def submit(session: AsyncSession, story: Story) -> None:
    """Move the story to `moderating` and queue the check, in the caller's transaction."""
    if story.original_language != "english" and not await step_done(
        session, story.id, "translate_en"
    ):
        # An older translation would be judged in place of the text the member now has.
        raise TextNotReady("Wait for the English translation to finish, then submit again.")
    texts = await judged_texts(session, story)
    input_hash = step_hash(STEP, get_settings().llm_provider, json.dumps(texts, ensure_ascii=False))
    story.status = StoryStatus.MODERATING.value
    story.published_at = None
    # Every submission is checked, even when the text is the same as last time.
    await queue_step(session, story.id, STEP, STEP, input_hash, always=True)


def _validated(verdicts: dict) -> dict[str, dict]:
    out = {}
    for label in MODERATION_LABELS:
        verdict = verdicts.get(label)
        if not isinstance(verdict, dict) or not isinstance(verdict.get("raised"), bool):
            raise UserFacingError("The moderation check returned an incomplete answer.")
        out[label] = {"raised": verdict["raised"], "reason": str(verdict.get("reason", ""))}
    return out


@handler(STEP)
async def moderate(payload: dict) -> dict:
    story_id = uuid.UUID(payload["story_id"])
    # Read what to judge, then let the transaction go: the provider call can take a while.
    async with get_sessionmaker()() as session:
        story = await session.get(Story, story_id)
        if (
            story is None
            or story.status != StoryStatus.MODERATING
            or not await is_current(session, payload)
        ):
            return STALE
        texts = await judged_texts(session, story)
    llm = language_model()

    async def run() -> dict:
        return {"labels": await llm.moderate(texts)}

    parts = (json.dumps(texts, ensure_ascii=False),)
    raw = await gateway.call(STEP, llm, parts, sum(len(t) for t in texts), run)
    labels = _validated(raw["labels"])

    async with get_sessionmaker()() as session:
        # Lock the story and the step, so a staff decision or a new submission made while
        # the provider answered is never overwritten.
        story = await session.get(Story, story_id, with_for_update=True, populate_existing=True)
        if (
            story is None
            or story.status != StoryStatus.MODERATING
            or not await is_current(session, payload, lock=True)
        ):
            return STALE
        held = any(v["raised"] for v in labels.values())
        session.add(
            ModerationResult(
                story_id=story.id,
                labels=labels,
                held=held,
                texts=texts,
                text_hash=payload["input_hash"],
            )
        )
        if held:
            story.status = StoryStatus.HELD.value
        else:
            story.status = StoryStatus.PUBLISHED.value
            story.published_at = datetime.now(UTC)
        await session.commit()
        return {"held": held}


async def latest(session: AsyncSession, story_id: uuid.UUID) -> ModerationResult | None:
    return (
        await session.execute(
            select(ModerationResult)
            .where(ModerationResult.story_id == story_id)
            .order_by(ModerationResult.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def latest_for(
    session: AsyncSession, story_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ModerationResult]:
    """The latest result of each story, in one query."""
    if not story_ids:
        return {}
    rows = await session.execute(
        select(ModerationResult)
        .where(ModerationResult.story_id.in_(story_ids))
        .order_by(ModerationResult.created_at.desc())
    )
    out: dict[uuid.UUID, ModerationResult] = {}
    for r in rows.scalars():
        out.setdefault(r.story_id, r)  # newest first, so the first one seen is the latest
    return out
