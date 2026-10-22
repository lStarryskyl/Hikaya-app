"""Background worker: claims jobs from Postgres and runs their handlers.

Run with `python -m app.worker`.
"""

import asyncio
import logging
import signal
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import jobs, pipeline
from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.errors import INTERNAL_PREFIX, UserFacingError
from app.handlers import HANDLERS, Handler

log = logging.getLogger("hikaya.worker")

# The pipeline module registers its job handlers when imported; keep the reference explicit.
_REGISTERED_HANDLER_MODULES = (pipeline,)


async def run_one(
    sessionmaker: async_sessionmaker[AsyncSession], handlers: dict[str, Handler] | None = None
) -> bool:
    """Process at most one job. Returns True if a job was claimed."""
    handlers = HANDLERS if handlers is None else handlers
    async with sessionmaker() as session:
        job = await jobs.claim_next(session)
        if job is None:
            return False
        log.info("job %s (%s) attempt %s", job.id, job.kind, job.attempts)
        fn = handlers.get(job.kind)
        if fn is None:
            await jobs.mark_failed(session, job, f"no handler for kind {job.kind!r}")
            return True
        try:
            result = await fn(job.payload)
        except Exception as exc:  # a handler failure must never kill the worker
            log.exception("job %s failed", job.id)
            # A member sees the error text, so only deliberate messages pass through.
            error = (
                str(exc)
                if isinstance(exc, UserFacingError)
                else f"{INTERNAL_PREFIX}{type(exc).__name__}: {exc}"
            )
            await jobs.mark_failed(session, job, error)
            return True
        cost = Decimal(str(result.pop("provider_cost_usd", 0)))
        await jobs.mark_done(session, job.id, result, cost)
        return True


async def run_forever(stop: asyncio.Event) -> None:
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    ticks = 0
    while not stop.is_set():
        if ticks % 30 == 0:
            async with sessionmaker() as session:
                released = await jobs.release_stale(session, settings.job_stale_after_seconds)
                if released:
                    log.warning("released %s stale job(s)", released)
        ticks += 1
        if not await run_one(sessionmaker):
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
            except TimeoutError:
                pass


async def _main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker started")
    try:
        await run_forever(stop)
    finally:
        await dispose_engine()
        log.info("worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(_main())


if __name__ == "__main__":
    main()
