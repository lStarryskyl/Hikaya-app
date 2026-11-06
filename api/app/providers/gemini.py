"""What the Gemini API providers share (Gemini Omni video, the screenwriter): the Interactions
endpoint, the key header and plain messages for refusals. The key goes in the
`x-goog-api-key` header, never in a URL."""

import httpx

from app.config import get_settings
from app.errors import NotStarted

INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


def key_headers() -> dict:
    key = get_settings().gemini_api_key
    if not key:
        raise NotStarted("The Gemini API key is not configured: set GEMINI_API_KEY.")
    return {"x-goog-api-key": key}


def error_reasons(response: httpx.Response) -> set[str]:
    """The `reason` codes in a Google error body, which the Interactions API sends either as
    {"error": ...} or wrapped in a list."""
    try:
        body = response.json()
    except ValueError:
        return set()
    errors = body if isinstance(body, list) else [body]
    reasons = set()
    for item in errors:
        error = item.get("error") if isinstance(item, dict) else None
        details = error.get("details") if isinstance(error, dict) else None
        for detail in details if isinstance(details, list) else []:
            if isinstance(detail, dict) and isinstance(detail.get("reason"), str):
                reasons.add(detail["reason"])
    return reasons


def raise_refusal(response: httpx.Response, service: str, paid_tier_only: bool) -> None:
    """A plain message for answers that mean Google refused the request outright: nothing was
    started, so nothing was billed (NotStarted)."""
    status = response.status_code
    # Google answers a wrong key with 400 API_KEY_INVALID, not 401.
    if status in (401, 403) or (status == 400 and "API_KEY_INVALID" in error_reasons(response)):
        raise NotStarted(
            "Google rejected the Gemini API key; check GEMINI_API_KEY"
            + (" (Omni Flash needs a key on a paid-tier project)." if paid_tier_only else ".")
        )
    if status == 429:
        raise NotStarted(
            "Google refused the request for quota: "
            + (
                "Omni Flash needs a Gemini API key on the paid tier, or the project's quota is "
                "used up."
                if paid_tier_only
                else "the project's quota is used up; try again later."
            )
        )
    if status in (400, 404):
        raise NotStarted(
            f"{service} refused this request. The prompt or photo may be blocked, "
            "or the model is not available to this key."
        )
