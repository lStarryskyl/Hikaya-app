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
from app.pipeline import POLISHED, STALE, TARGET_LAYER, _hash, _is_current, _layer, _queue
from app.providers import MODERATION_LABELS, language_model

STEP = "moderate"
ENGLISH = TARGET_LAYER["english"]


class TextNotReady(Exception):
    pass


async def judged_texts(session: AsyncSession, story: Story) -> list[str]:
    """The polished text, plus the English translation when the story is not in English."""
    polished = await _layer(session, story.id, POLISHED)
    english = await _layer(session, story.id, ENGLISH)
    if polished is None or (story.original_language != "english" and english is None):
        raise TextNotReady
    texts = [s["text"] for s in polished.segments]
    if english is not None:
        texts += [s["text"] for s in english.segments]
    return texts


async def submit(session: AsyncSession, story: Story) -> None:
    """Move the story to `moderating` and queue the check, in the caller's transaction."""
    texts = await judged_texts(session, story)
    input_hash = _hash(STEP, get_settings().llm_provider, json.dumps(texts, ensure_ascii=False))
    story.status = StoryStatus.MODERATING.value
    story.published_at = None
    await _queue(session, story.id, STEP, STEP, input_hash)


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
    async with get_sessionmaker()() as session:
        story = await session.get(Story, uuid.UUID(payload["story_id"]))
        if (
            story is None
            or story.status != StoryStatus.MODERATING
            or not await _is_current(session, payload)
        ):
            return STALE
        texts = await judged_texts(session, story)
        llm = language_model()

        async def run() -> dict:
            return {"labels": await llm.moderate(texts)}

        parts = (json.dumps(texts, ensure_ascii=False),)
        raw = await gateway.call(STEP, llm, parts, sum(len(t) for t in texts), run)
        labels = _validated(raw["labels"])
        if not await _is_current(session, payload, lock=True):
            return STALE
        held = any(v["raised"] for v in labels.values())
        session.add(
            ModerationResult(
                story_id=story.id, labels=labels, held=held, text_hash=payload["input_hash"]
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
