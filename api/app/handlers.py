"""Job handlers, registered by job kind.

A handler takes the job payload and returns a result dict. If it spent provider money, it
includes `provider_cost_usd` in the result and the worker records it on the job.
"""

from collections.abc import Awaitable, Callable

Handler = Callable[[dict], Awaitable[dict]]

HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


@handler("ping")
async def ping(payload: dict) -> dict:
    """Proves the worker is alive and wired to the database."""
    return {"pong": True, "echo": payload.get("echo")}
