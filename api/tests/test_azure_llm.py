"""The Azure language model (#12) against mocked HTTP: no live calls, no real keys."""

import json
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app import gateway
from app.config import Settings, get_settings
from app.errors import UserFacingError
from app.models import SpendEntry
from app.providers import MODERATION_LABELS, ProviderUnavailable, language_model
from app.providers.azure_llm import AzureLanguageModel
from tests.http_mock import mock_http

ENDPOINT = "https://hikaya-test.openai.azure.com"


@pytest.fixture
def azure(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "azure")
    monkeypatch.setattr(settings, "azure_openai_endpoint", ENDPOINT + "/")
    monkeypatch.setattr(settings, "azure_openai_api_key", "test-key")
    monkeypatch.setattr(settings, "azure_openai_deployment", "hikaya-mini")
    monkeypatch.setattr(settings, "azure_openai_input_usd_per_million", 0.75)
    monkeypatch.setattr(settings, "azure_openai_output_usd_per_million", 4.5)
    return settings


def answer(content: dict | str, prompt_tokens=1000, completion_tokens=500, status=200):
    body = {
        "id": "chatcmpl-1",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content if isinstance(content, str) else json.dumps(content),
                },
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return lambda request: httpx.Response(status, json=body)


def sent(request: httpx.Request) -> dict:
    return json.loads(request.content)


# --- choosing the provider and its keys ---


def test_the_setting_selects_the_azure_adapter(azure):
    assert isinstance(language_model(), AzureLanguageModel)


def test_keys_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "from-env")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "my-deployment")
    settings = Settings(_env_file=None)
    assert settings.azure_openai_api_key == "from-env"
    assert settings.azure_openai_deployment == "my-deployment"


def test_missing_configuration_is_explained_without_calling(azure, monkeypatch):
    monkeypatch.setattr(azure, "azure_openai_api_key", "")
    with pytest.raises(ProviderUnavailable, match="AZURE_OPENAI_API_KEY"):
        language_model()


# --- polishing and translating ---


async def test_polish_sends_one_structured_request_and_keeps_the_lines(azure, monkeypatch):
    seen = mock_http(monkeypatch, answer({"lines": ["سطر أول.", "سطر ثان."]}))
    out = await language_model().polish(["سطر اول", "سطر ثاني"], "jordanian")
    assert out == ["سطر أول.", "سطر ثان."]
    (request,) = seen
    assert str(request.url) == f"{ENDPOINT}/openai/v1/chat/completions"
    assert request.headers["api-key"] == "test-key"
    body = sent(request)
    assert body["model"] == "hikaya-mini"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    # The lines travel as JSON, so their order and count are explicit.
    assert json.loads(body["messages"][-1]["content"])["lines"] == ["سطر اول", "سطر ثاني"]
    assert "Jordanian" in body["messages"][0]["content"]


async def test_a_different_number_of_lines_is_refused(azure, monkeypatch):
    mock_http(monkeypatch, answer({"lines": ["only one"]}))
    with pytest.raises(UserFacingError, match="different number of lines"):
        await language_model().polish(["one", "two"], "english")


async def test_translation_targets_english_or_msa_only(azure, monkeypatch):
    seen = mock_http(monkeypatch, answer({"lines": ["The lantern."]}))
    assert await language_model().translate(["الفانوس"], "jordanian", "english") == ["The lantern."]
    assert "Modern Standard Arabic" not in sent(seen[0])["messages"][0]["content"]
    with pytest.raises(ValueError, match="dialect"):
        await language_model().translate(["text"], "english", "jordanian")
    assert len(seen) == 1  # the refused target never reached Azure


async def test_msa_translation_asks_for_modern_standard_arabic(azure, monkeypatch):
    seen = mock_http(monkeypatch, answer({"lines": ["المصباح."]}))
    await language_model().translate(["The lamp"], "english", "msa")
    assert "Modern Standard Arabic" in sent(seen[0])["messages"][0]["content"]


# --- moderation ---


async def test_moderation_returns_the_four_labels_with_reasons(azure, monkeypatch):
    labels = {label: {"raised": False, "reason": ""} for label in MODERATION_LABELS}
    labels["violence"] = {"raised": True, "reason": "A threat to kill an animal."}
    seen = mock_http(monkeypatch, answer({"labels": labels}))
    out = await language_model().moderate(["He would kill the wolf."])
    assert out["violence"] == {"raised": True, "reason": "A threat to kill an animal."}
    assert set(out) == set(MODERATION_LABELS)
    schema = sent(seen[0])["response_format"]["json_schema"]["schema"]
    assert set(schema["properties"]["labels"]["required"]) == set(MODERATION_LABELS)


# --- broken answers and errors ---


@pytest.mark.parametrize(
    "content",
    ["not json at all", {"wrong": []}, {"lines": "a string"}, {"lines": [1, 2]}],
)
async def test_malformed_answers_are_refused(azure, monkeypatch, content):
    mock_http(monkeypatch, answer(content))
    with pytest.raises(UserFacingError, match="unexpected answer"):
        await language_model().polish(["one", "two"], "english")


async def test_a_refusal_is_reported(azure, monkeypatch):
    def respond(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": None, "refusal": "No."}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1},
            },
        )

    mock_http(monkeypatch, respond)
    with pytest.raises(UserFacingError, match="declined"):
        await language_model().polish(["one"], "english")


async def test_a_cut_off_answer_is_refused(azure, monkeypatch):
    def respond(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "length", "message": {"content": '{"lines": ["a'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1},
            },
        )

    mock_http(monkeypatch, respond)
    with pytest.raises(UserFacingError, match="cut off"):
        await language_model().polish(["one"], "english")


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "rejected the key"), (404, "deployment"), (429, "busy"), (500, "unavailable")],
)
async def test_http_errors_say_what_happened_without_the_key(azure, monkeypatch, status, message):
    mock_http(monkeypatch, lambda request: httpx.Response(status, json={"error": {"code": "x"}}))
    with pytest.raises(UserFacingError, match=message) as caught:
        await language_model().polish(["one"], "english")
    assert "test-key" not in str(caught.value)


async def test_a_network_failure_is_unavailable(azure, monkeypatch):
    def respond(request):
        raise httpx.ConnectError("down", request=request)

    mock_http(monkeypatch, respond)
    with pytest.raises(ProviderUnavailable):
        await language_model().polish(["one"], "english")


# --- cost ---


def test_the_estimate_is_per_token_and_covers_the_answer(azure):
    model = language_model()
    small, large = model.estimate_usd("polish", 1_000), model.estimate_usd("polish", 10_000)
    assert Decimal("0") < small < large
    # 10,000 characters is a few thousand tokens in and out: cents, not dollars.
    assert large < Decimal("0.25")


async def test_the_ledger_records_the_cost_azure_reports(azure, monkeypatch, sessionmaker, session):
    monkeypatch.setattr(azure, "live_ai_enabled", True)
    mock_http(monkeypatch, answer({"lines": ["Done."]}, prompt_tokens=2000, completion_tokens=1000))
    model = language_model()

    async def run():
        return {"texts": await model.polish(["done"], "english")}

    await gateway.call("polish", model, ("english", "", '["done"]'), 4, run)
    entry = (await session.execute(select(SpendEntry))).scalar_one()
    assert entry.budget == "azure" and entry.state == "committed"
    # 2,000 x $0.75/M + 1,000 x $4.50/M
    assert entry.actual_usd == Decimal("0.0060")


# --- through the worker ---


async def test_a_story_goes_through_the_pipeline_on_azure(
    azure, monkeypatch, client, sessionmaker, tmp_path
):
    import subprocess

    from tests.test_moderation import drain, sign_up, submit

    monkeypatch.setattr(azure, "live_ai_enabled", True)

    def respond(request):
        body = sent(request)
        payload = json.loads(body["messages"][-1]["content"])
        system = body["messages"][0]["content"]
        if "texts" in payload:
            labels = {label: {"raised": False, "reason": ""} for label in MODERATION_LABELS}
            return answer({"labels": labels})(request)
        tag = "EN" if "into English" in system else "MSA" if "into Modern" in system else "POL"
        return answer({"lines": [f"{tag}: {line}" for line in payload["lines"]]})(request)

    seen = mock_http(monkeypatch, respond)
    tone = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=6", "-ac", "1", str(tone)],
        check=True,
    )
    await sign_up(client)
    story = (
        await client.post(
            "/api/v1/stories",
            json={
                "title": "Azure",
                "category": "folklore",
                "place_name": "Salt",
                "latitude": 32.0,
                "longitude": 35.7,
                "original_language": "jordanian",
            },
        )
    ).json()
    with open(tone, "rb") as f:
        await client.put(
            f"/api/v1/stories/{story['id']}/audio", files={"file": ("t.wav", f, "audio/wav")}
        )
    await drain(sessionmaker)
    layers = {
        la["kind"]: la
        for la in (await client.get(f"/api/v1/stories/{story['id']}")).json()["layers"]
    }
    assert layers["polished"]["segments"][0]["text"].startswith("POL: ")
    assert layers["translation_en"]["segments"][0]["text"].startswith("EN: POL: ")
    assert layers["translation_msa"]["segments"][0]["text"].startswith("MSA: POL: ")
    await submit(client, story["id"])
    await drain(sessionmaker)
    assert (await client.get(f"/api/v1/stories/{story['id']}")).json()["status"] == "published"
    assert len(seen) == 4  # polish, two translations, moderation
