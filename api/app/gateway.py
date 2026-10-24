"""The one door every provider call goes through: cache, live-AI switch, spending ledger.

    result = await gateway.call("polish", provider, key_parts, units, run)

1. A cached result for the same operation, provider and input is returned at once: no
   cost, no provider call, whatever the live-AI switch says. A result that is a file (speech)
   is stored at `file_key`; a hit whose file has gone missing runs again.
2. A free provider (the fakes) just runs.
3. A paid provider needs LIVE_AI_ENABLED, then a reservation of its estimated cost that
   fits the caps; the reservation is committed after the call or released if it fails.
"""

import asyncio
import hashlib
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import UserFacingError
from app.models import ProviderCacheEntry, SpendEntry
from app.storage import get_storage

# Set by the worker around each job, so ledger rows and job costs know their job.
CURRENT_JOB: ContextVar[uuid.UUID | None] = ContextVar("current_job", default=None)
JOB_COST: ContextVar[list[Decimal] | None] = ContextVar("job_cost", default=None)

ACTIVE = ("reserved", "committed")


class LiveAIOff(UserFacingError):
    def __init__(self) -> None:
        super().__init__(
            "Live AI is switched off and this result is not saved yet. "
            "Load the demo pack, or switch live AI on."
        )


class SpendingLimit(UserFacingError):
    def __init__(self, which: str) -> None:
        super().__init__(f"The {which} spending limit has been reached, so this step was not run.")


def cache_key(operation: str, provider: str, parts: tuple[str, ...]) -> str:
    return hashlib.sha256("\x1f".join((operation, provider, *parts)).encode()).hexdigest()


async def _reserve(provider: str, operation: str, budget: str, estimate: Decimal) -> uuid.UUID:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        # One reservation at a time, so two workers cannot both squeeze under a cap.
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('hikaya-spend'))"))
        spent = func.coalesce(
            func.sum(func.coalesce(SpendEntry.actual_usd, SpendEntry.estimated_usd)), 0
        )
        active = (SpendEntry.budget == budget) & SpendEntry.state.in_(ACTIVE)
        total = (await session.execute(select(spent).where(active))).scalar_one()
        today = (
            await session.execute(
                select(spent).where(
                    active, SpendEntry.created_at >= func.date_trunc("day", func.now())
                )
            )
        ).scalar_one()
        over = None
        if budget == "card":
            if total + estimate > Decimal(str(settings.spend_cap_usd_total)):
                over = "total"
            elif today + estimate > Decimal(str(settings.spend_cap_usd_daily)):
                over = "daily"
        elif total + estimate > Decimal(str(settings.spend_cap_usd_azure)):
            over = "Azure"
        entry = SpendEntry(
            provider=provider,
            operation=operation,
            budget=budget,
            estimated_usd=estimate,
            state="released" if over else "reserved",
            job_id=CURRENT_JOB.get(),
        )
        session.add(entry)
        await session.commit()
        if over:
            raise SpendingLimit(over)
        return entry.id


async def _settle(entry_id: uuid.UUID, state: str, actual: Decimal | None) -> None:
    async with get_sessionmaker()() as session:
        entry = await session.get(SpendEntry, entry_id)
        entry.state, entry.actual_usd = state, actual
        await session.commit()


async def _store(
    key: str, operation: str, provider: str, result: dict, file_key: str | None
) -> None:
    async with get_sessionmaker()() as session:
        insert = pg_insert(ProviderCacheEntry).values(
            key=key, operation=operation, provider=provider, result=result, file_key=file_key
        )
        # A file result is stored again when its file went missing and was made anew.
        await session.execute(
            insert.on_conflict_do_update(
                index_elements=["key"], set_={"result": result, "file_key": file_key}
            )
            if file_key
            else insert.on_conflict_do_nothing(index_elements=["key"])
        )
        await session.commit()


async def call(
    operation: str,
    provider,
    parts: tuple[str, ...],
    units: int,
    run: Callable[[], Awaitable[dict]],
    *,
    file_key: str | None = None,
) -> dict:
    """Run `run()` (which returns a JSON-able dict) at most once per input, within budget.
    `file_key` is for `call_file`."""
    key = cache_key(operation, provider.name, parts)
    async with get_sessionmaker()() as session:
        hit = await session.get(ProviderCacheEntry, key)
        if hit is not None and (hit.file_key is None or get_storage().exists(hit.file_key)):
            return hit.result

    budget = provider.budget
    if budget is None:
        result = await run()
        await _store(key, operation, provider.name, result, file_key)
        return result

    if not get_settings().live_ai_enabled:
        raise LiveAIOff
    estimate = provider.estimate_usd(operation, units)
    entry_id = await _reserve(provider.name, operation, budget, estimate)
    try:
        result = await run()
    except BaseException:
        await _settle(entry_id, "released", None)
        raise
    # Providers report no exact bill per call, so the estimate is recorded as the cost.
    await _settle(entry_id, "committed", estimate)
    costs = JOB_COST.get()
    if costs is not None:
        costs.append(estimate)
    await _store(key, operation, provider.name, result, file_key)
    return result


async def call_file(
    operation: str,
    provider,
    parts: tuple[str, ...],
    units: int,
    run: Callable[[], Awaitable[tuple[dict, bytes]]],
    extension: str,
) -> tuple[dict, str]:
    """`call` for a result that is a file (such as speech): `run()` returns the JSON-able part
    and the file's bytes; the file is cached in storage next to the result. Returns the result
    and the file's storage key."""
    storage = get_storage()
    file_key = f"cache/{operation}/{cache_key(operation, provider.name, parts)}{extension}"

    async def run_and_save() -> dict:
        result, data = await run()
        await asyncio.to_thread(storage.write_bytes, file_key, data)
        return result

    result = await call(operation, provider, parts, units, run_and_save, file_key=file_key)
    return result, file_key
