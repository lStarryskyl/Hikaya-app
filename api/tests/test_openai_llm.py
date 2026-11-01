"""Direct OpenAI contracts; every HTTP call is mocked."""

import json
from decimal import Decimal

import httpx
import pytest

from app import gateway
from app.config import get_settings
from app.errors import UserFacingError
from app.providers import MODERATION_LABELS, ProviderUnavailable, language_model
from tests.http_mock import mock_http


@pytest.fixture
def openai(monkeypatch):
    s = get_settings()
    for name, value in {
        "llm_provider": "openai",
        "openai_api_key": "test-secret",
        "openai_model": "gpt-4.1-mini",
        "openai_input_usd_per_million": 0.4,
        "openai_output_usd_per_million": 1.6,
    }.items():
        monkeypatch.setattr(s, name, value)
    return s


def response(content, *, finish="stop", usage=None):
    return httpx.Response(
        200,
        json={
            "choices": [{"finish_reason": finish, "message": {"content": json.dumps(content)}}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50},
        },
    )


async def test_polish_contract_and_reported_cost(openai, monkeypatch):
    reported = []
    monkeypatch.setattr(gateway, "report_cost", reported.append)
    seen = mock_http(monkeypatch, lambda r: response({"lines": ["أول", "ثان"]}))
    model = language_model()
    assert model.budget == "card"
    assert await model.polish(["اول", "ثاني"], "jordanian") == ["أول", "ثان"]
    request = seen[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-secret"
    body = json.loads(request.content)
    assert body["store"] is False
    assert body["max_completion_tokens"] == openai.openai_max_output_tokens
    assert body["response_format"]["json_schema"]["strict"] is True
    assert reported == [Decimal("0.00012")]
    assert model.estimate_usd("polish", 100) > reported[0]


async def test_translation_never_targets_dialect(openai, monkeypatch):
    seen = mock_http(monkeypatch, lambda r: response({"lines": ["المصباح"]}))
    assert await language_model().translate(["lamp"], "english", "msa") == ["المصباح"]
    with pytest.raises(ValueError, match="dialect"):
        await language_model().translate(["lamp"], "english", "jordanian")
    assert len(seen) == 1


async def test_moderation_keeps_four_labels(openai, monkeypatch):
    labels = {key: {"raised": False, "reason": ""} for key in MODERATION_LABELS}
    labels["other_terrible"] = {"raised": True, "reason": "Private personal data."}
    mock_http(monkeypatch, lambda r: response({"labels": labels}))
    assert await language_model().moderate(["text"]) == labels


@pytest.mark.parametrize("content", [{"lines": ["one"]}, {"lines": [1, 2]}, {"bad": []}])
async def test_invalid_lines_rejected(openai, monkeypatch, content):
    mock_http(monkeypatch, lambda r: response(content))
    with pytest.raises(UserFacingError):
        await language_model().polish(["one", "two"], "english")


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
async def test_http_errors_hide_credentials(openai, monkeypatch, status):
    mock_http(monkeypatch, lambda r: httpx.Response(status, text="test-secret"))
    with pytest.raises(UserFacingError) as exc:
        await language_model().polish(["one"], "english")
    assert "test-secret" not in str(exc.value)


async def test_timeout_retains_conservative_charge(openai, monkeypatch):
    reported = []
    monkeypatch.setattr(gateway, "report_cost", reported.append)

    def fail(request):
        raise httpx.ReadTimeout("timeout", request=request)

    mock_http(monkeypatch, fail)
    model = language_model()
    with pytest.raises(ProviderUnavailable):
        await model.polish(["one"], "english")
    assert reported == [model.estimate_usd("polish", 3)]


async def test_truncated_answer_rejected(openai, monkeypatch):
    mock_http(monkeypatch, lambda r: response({"lines": ["one"]}, finish="length"))
    with pytest.raises(UserFacingError):
        await language_model().polish(["one"], "english")


def test_missing_key_or_rates_fail_closed(openai, monkeypatch):
    monkeypatch.setattr(openai, "openai_api_key", "")
    with pytest.raises(ProviderUnavailable, match="OPENAI_API_KEY"):
        language_model()
    monkeypatch.setattr(openai, "openai_api_key", "test")
    monkeypatch.setattr(openai, "openai_input_usd_per_million", 0)
    with pytest.raises(ProviderUnavailable, match="prices"):
        language_model()


async def test_invalid_moderation_reason_rejected(openai, monkeypatch):
    labels = {key: {"raised": False, "reason": 42} for key in MODERATION_LABELS}
    mock_http(monkeypatch, lambda r: response({"labels": labels}))
    with pytest.raises(UserFacingError):
        await language_model().moderate(["text"])


async def test_openai_uses_shared_card_ledger(openai, monkeypatch, sessionmaker, session):
    from sqlalchemy import select

    from app.models import SpendEntry

    monkeypatch.setattr(openai, "live_ai_enabled", True)
    mock_http(monkeypatch, lambda r: response({"lines": ["Done."]}))
    model = language_model()

    async def run():
        return {"texts": await model.polish(["done"], "english")}

    await gateway.call("polish", model, ("english", '["done"]'), 4, run)
    entry = (await session.execute(select(SpendEntry))).scalar_one()
    assert entry.budget == "card"
    assert entry.state == "committed"
    assert entry.actual_usd == Decimal("0.00012")


async def test_openai_respects_live_switch(openai, monkeypatch, sessionmaker):
    monkeypatch.setattr(openai, "live_ai_enabled", False)
    seen = mock_http(monkeypatch, lambda r: response({"lines": ["Done."]}))
    model = language_model()

    async def run():
        return {"texts": await model.polish(["done"], "english")}

    with pytest.raises(gateway.LiveAIOff):
        await gateway.call("polish", model, ("switch-test",), 4, run)
    assert seen == []
