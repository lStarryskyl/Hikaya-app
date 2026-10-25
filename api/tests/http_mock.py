"""Answer every outgoing httpx request from a test function; nothing reaches the network."""

import httpx


def mock_http(monkeypatch, respond):
    """Route all httpx.AsyncClient traffic to `respond(request) -> httpx.Response`.
    Returns the list of requests seen, in order."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return respond(request)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**{**kwargs, "transport": httpx.MockTransport(handler)}),
    )
    return seen
