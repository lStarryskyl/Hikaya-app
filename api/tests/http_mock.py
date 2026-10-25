"""Answer every outgoing httpx request from a test function; nothing reaches the network."""

import httpx

# The real client, captured once, so calling mock_http twice in a test replaces the
# responder instead of wrapping the first one.
REAL_CLIENT = httpx.AsyncClient


def mock_http(monkeypatch, respond):
    """Route all httpx.AsyncClient traffic to `respond(request) -> httpx.Response`.
    Returns the list of requests seen, in order."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return respond(request)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: REAL_CLIENT(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )
    return seen
