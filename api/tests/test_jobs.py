import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text

from app import jobs
from app.handlers import HANDLERS
from app.models import Job, JobStatus
from app.worker import run_one


async def _get(session, job_id) -> Job:
    session.expire_all()
    return (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()


async def test_enqueue_creates_a_queued_job(session):
    job = await jobs.enqueue(session, "ping", {"echo": "hi"})
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 0
    assert job.payload == {"echo": "hi"}


async def test_same_idempotency_key_gives_the_same_job(session):
    first = await jobs.enqueue(session, "ping", idempotency_key="story-1:transcribe")
    again = await jobs.enqueue(session, "ping", idempotency_key="story-1:transcribe")
    assert first.id == again.id
    count = (await session.execute(text("SELECT count(*) FROM jobs"))).scalar_one()
    assert count == 1


async def test_claim_takes_the_oldest_due_job_once(session):
    older = await jobs.enqueue(session, "ping")
    await jobs.enqueue(session, "ping")
    claimed = await jobs.claim_next(session)
    assert claimed.id == older.id
    assert claimed.status == JobStatus.RUNNING
    assert claimed.attempts == 1
    assert claimed.locked_at is not None


async def test_claim_returns_none_when_the_queue_is_empty(session):
    assert await jobs.claim_next(session) is None


async def test_jobs_scheduled_for_later_are_not_claimed(session):
    await jobs.enqueue(session, "ping", run_after=datetime.now(UTC) + timedelta(hours=1))
    assert await jobs.claim_next(session) is None


async def test_two_workers_never_claim_the_same_job(sessionmaker, session):
    await jobs.enqueue(session, "ping")
    await jobs.enqueue(session, "ping")

    async def claim():
        async with sessionmaker() as s:
            return await jobs.claim_next(s)

    first, second = await asyncio.gather(claim(), claim())
    assert first is not None and second is not None
    assert first.id != second.id


async def test_one_job_goes_to_exactly_one_of_two_workers(sessionmaker, session):
    await jobs.enqueue(session, "ping")

    async def claim():
        async with sessionmaker() as s:
            return await jobs.claim_next(s)

    results = await asyncio.gather(claim(), claim(), claim())
    assert sum(r is not None for r in results) == 1


async def test_worker_runs_the_ping_handler(sessionmaker, session):
    job = await jobs.enqueue(session, "ping", {"echo": "salaam"})
    assert await run_one(sessionmaker) is True
    done = await _get(session, job.id)
    assert done.status == JobStatus.DONE
    assert done.result == {"pong": True, "echo": "salaam"}
    assert done.finished_at is not None


async def test_worker_reports_when_there_is_nothing_to_do(sessionmaker):
    assert await run_one(sessionmaker) is False


async def test_provider_cost_is_recorded_on_the_job(sessionmaker, session):
    async def spender(_payload):
        return {"ok": True, "provider_cost_usd": 0.5}

    job = await jobs.enqueue(session, "spend")
    await run_one(sessionmaker, {"spend": spender})
    done = await _get(session, job.id)
    assert done.provider_cost_usd == Decimal("0.5")
    assert "provider_cost_usd" not in done.result


async def test_failed_job_is_retried_then_fails_for_good(sessionmaker, session):
    async def broken(_payload):
        raise RuntimeError("provider is down")

    job = await jobs.enqueue(session, "broken", max_attempts=2)

    await run_one(sessionmaker, {"broken": broken})
    first = await _get(session, job.id)
    assert first.status == JobStatus.QUEUED
    assert first.attempts == 1
    assert first.run_after > datetime.now(UTC)
    assert "provider is down" in first.error

    # Skip the retry delay, then run the last attempt.
    await session.execute(text("UPDATE jobs SET run_after = now()"))
    await session.commit()
    await run_one(sessionmaker, {"broken": broken})
    last = await _get(session, job.id)
    assert last.status == JobStatus.FAILED
    assert last.attempts == 2
    assert last.finished_at is not None


async def test_unknown_job_kind_fails_instead_of_crashing(sessionmaker, session):
    job = await jobs.enqueue(session, "no-such-kind", max_attempts=1)
    assert await run_one(sessionmaker, HANDLERS) is True
    failed = await _get(session, job.id)
    assert failed.status == JobStatus.FAILED
    assert "no handler" in failed.error


async def test_stale_running_jobs_go_back_to_the_queue(session):
    job = await jobs.enqueue(session, "ping")
    await jobs.claim_next(session)
    await session.execute(text("UPDATE jobs SET locked_at = now() - interval '1 hour'"))
    await session.commit()
    assert await jobs.release_stale(session, stale_after_seconds=600) == 1
    back = await _get(session, job.id)
    assert back.status == JobStatus.QUEUED
    assert back.locked_at is None


async def test_the_worker_survives_a_database_error(sessionmaker, monkeypatch):
    """A failing claim (database restarting) must not end the worker loop."""
    import asyncio

    from app import worker

    calls = 0

    async def flaky(maker, handlers=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("database restarting")
        if calls >= 3:
            stop.set()
        return False

    stop = asyncio.Event()
    monkeypatch.setattr(worker, "run_one", flaky)
    monkeypatch.setattr(worker.get_settings(), "worker_poll_seconds", 0.01)
    await asyncio.wait_for(worker.run_forever(stop, sessionmaker), timeout=5)
    assert calls >= 3
