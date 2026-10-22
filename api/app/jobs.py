"""Postgres-backed job queue.

Producers call `enqueue` with an idempotency key, so a retried request never creates a second
job (and so never bills a provider twice). The worker claims one job at a time with
`FOR UPDATE SKIP LOCKED`, so several workers can run without picking the same job.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobStatus


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict | None = None,
    *,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
    run_after: datetime | None = None,
    commit: bool = True,
) -> Job:
    """Add a job. With an idempotency key, a repeat call returns the existing job.

    `commit=False` leaves the transaction open, so the caller can record what the job is
    for in the same commit (a worker must never see the job without that record).
    """
    values: dict = {"kind": kind, "payload": payload or {}, "max_attempts": max_attempts}
    if idempotency_key is not None:
        values["idempotency_key"] = idempotency_key
    if run_after is not None:
        values["run_after"] = run_after

    stmt = pg_insert(Job).values(**values)
    if idempotency_key is not None:
        stmt = stmt.on_conflict_do_nothing(index_elements=["idempotency_key"])
    job = (await session.execute(stmt.returning(Job))).scalar_one_or_none()
    if job is None:
        job = (
            await session.execute(select(Job).where(Job.idempotency_key == idempotency_key))
        ).scalar_one()
    if commit:
        await session.commit()
    return job


async def requeue(session: AsyncSession, job_id) -> bool:
    """Give a failed job a fresh set of attempts. False if it was not failed."""
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.FAILED)
        .values(
            status=JobStatus.QUEUED,
            attempts=0,
            run_after=func.now(),
            error=None,
            finished_at=None,
            locked_at=None,
        )
    )
    await session.commit()
    return (result.rowcount or 0) == 1


async def claim_next(session: AsyncSession) -> Job | None:
    """Atomically take the oldest due job and mark it running. None when the queue is empty."""
    due = (
        select(Job.id)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= func.now())
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    stmt = (
        update(Job)
        .where(Job.id == due)
        .values(status=JobStatus.RUNNING, locked_at=func.now(), attempts=Job.attempts + 1)
        .returning(Job)
        # populate_existing: if this session already holds the job, return the fresh row
        # (status running, attempts bumped) instead of the stale cached object.
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    await session.commit()
    return job


async def mark_done(
    session: AsyncSession, job_id, result: dict, cost_usd: Decimal = Decimal("0")
) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status=JobStatus.DONE,
            result=result,
            provider_cost_usd=cost_usd,
            finished_at=func.now(),
            locked_at=None,
            error=None,
        )
    )
    await session.commit()


async def mark_failed(session: AsyncSession, job: Job, error: str) -> None:
    """Retry with a growing delay until attempts run out, then fail for good."""
    if job.attempts < job.max_attempts:
        delay = timedelta(seconds=5 * 2**job.attempts)
        values = {
            "status": JobStatus.QUEUED,
            "run_after": datetime.now(UTC) + delay,
            "error": error,
            "locked_at": None,
        }
    else:
        values = {
            "status": JobStatus.FAILED,
            "error": error,
            "finished_at": func.now(),
            "locked_at": None,
        }
    await session.execute(update(Job).where(Job.id == job.id).values(**values))
    await session.commit()


async def release_stale(session: AsyncSession, stale_after_seconds: int) -> int:
    """Put jobs back in the queue when a worker died while running them."""
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    stale = (Job.status == JobStatus.RUNNING) & (Job.locked_at < cutoff)
    retry = await session.execute(
        update(Job)
        .where(stale, Job.attempts < Job.max_attempts)
        .values(status=JobStatus.QUEUED, locked_at=None, error="worker lost")
    )
    dead = await session.execute(
        update(Job)
        .where(stale, Job.attempts >= Job.max_attempts)
        .values(
            status=JobStatus.FAILED, locked_at=None, finished_at=func.now(), error="worker lost"
        )
    )
    await session.commit()
    return (retry.rowcount or 0) + (dead.rowcount or 0)
