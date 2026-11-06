"""The screenwriter that refines a narrated video's shot list (docs/DECISIONS.md, "Refined shot
scripts and the voice choice for narrated videos"), against mocked HTTP: no live calls."""

import base64
import json
from decimal import Decimal

import httpx
import pytest

from app.config import get_settings
from app.errors import NotStarted, UserFacingError
from app.providers import ProviderUnavailable
from app.providers.script import (
    FakeScriptWriter,
    GeminiScriptWriter,
    ScriptRequest,
    ShotBrief,
    script_writer,
)
from tests.http_mock import mock_http

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
PHOTO = b"RIFF\x00\x00\x00\x00WEBPVP8 photo"
REQUEST = ScriptRequest(
    title="The Lantern Man",
    place="Amman",
    story="My grandfather lit the lantern. The neighbours came for coffee.",
    shots=[
        ShotBrief(12.3, "My grandfather lit the lantern."),
        ShotBrief(8.6, "The neighbours came."),
    ],
    direction="Warm evening light",
    photo=PHOTO,
    spoken_language="jordanian",
    audio="soundtrack",
)
SCRIPT = {
    "cast": "Grandfather: a lean man in his seventies, white moustache, grey qumbaz, red keffiyeh.",
    "setting": "A stone stairway in old Amman at dusk, then the doorstep at its top.",
    "narrator": "A warm, unhurried Jordanian man in his fifties.",
    "shots": [
        {
            "action": "Grandfather climbs the stairway and lights the lantern on its post.",
            "camera": "Slow push-in from the foot of the stairs.",
            "sound": "Leather soles on worn stone, a match striking, a soft hiss of kerosene.",
        },
        {
            "action": "At the top, neighbours carry a brass coffee pot to the doorstep.",
            "camera": "The camera follows him up the last steps.",
            "sound": "Cups clinking, low voices, a kettle.",
        },
    ],
}


def completed(script: dict) -> dict:
    return {
        "id": "v1_script",
        "status": "completed",
        "steps": [
            {"type": "thought", "content": [{"type": "thought", "text": "..."}]},
            {"type": "model_output", "content": [{"type": "text", "text": json.dumps(script)}]},
        ],
    }


@pytest.fixture
def gemini(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "script_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "ai-studio-test-key")
    return settings


def test_the_setting_chooses_the_writer(gemini, monkeypatch):
    assert isinstance(script_writer(), GeminiScriptWriter)
    assert script_writer().budget == "card"
    monkeypatch.setattr(gemini, "script_provider", "fake")
    assert isinstance(script_writer(), FakeScriptWriter)
    assert script_writer().budget is None


async def test_the_fake_writer_follows_the_story_words():
    screenplay = await FakeScriptWriter().refine(REQUEST)
    assert [scene.action for scene in screenplay.scenes] == [s.words for s in REQUEST.shots]


async def test_gemini_writes_one_coherent_scene_per_shot(gemini, monkeypatch):
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=completed(SCRIPT)))
    screenplay = await script_writer().refine(REQUEST)
    (request,) = seen
    assert str(request.url) == URL  # the key goes in the header only
    assert request.headers["x-goog-api-key"] == "ai-studio-test-key"
    body = json.loads(request.content)
    assert body["model"] == "gemini-3.8-flash"
    assert body["store"] is False  # the story is not kept at Google
    assert "background" not in body
    image, text = body["input"]
    assert base64.b64decode(image["data"]) == PHOTO and image["mime_type"] == "image/webp"
    prompt = text["text"]
    for needed in (
        "The Lantern Man",
        "Amman",
        "My grandfather lit the lantern.",
        "Shot 2 (8.6 s)",
        "Warm evening light",
        # The rules that keep the film coherent.
        "never return to a place",
        "set up before it is used",
        "identical in every shot",
    ):
        assert needed in prompt, needed
    schema = body["response_format"]
    assert (schema["type"], schema["mime_type"]) == ("text", "application/json")
    assert schema["schema"]["properties"]["shots"]["minItems"] == 2
    assert schema["schema"]["properties"]["shots"]["maxItems"] == 2
    assert screenplay.cast.startswith("Grandfather:")
    assert [scene.sound for scene in screenplay.scenes][0].startswith("Leather soles")
    assert screenplay.to_dict() == SCRIPT


async def test_a_script_with_the_wrong_number_of_shots_is_refused(gemini, monkeypatch):
    short = {**SCRIPT, "shots": SCRIPT["shots"][:1]}
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=completed(short)))
    with pytest.raises(UserFacingError, match="shot"):
        await script_writer().refine(REQUEST)


@pytest.mark.parametrize("answer", [{"id": "x", "status": "completed", "steps": []}, ["x"]])
async def test_an_unreadable_script_is_refused(gemini, monkeypatch, answer):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=answer))
    with pytest.raises(UserFacingError):
        await script_writer().refine(REQUEST)


@pytest.mark.parametrize(("status", "kind", "message"), [
    (401, NotStarted, "GEMINI_API_KEY"),
    (429, NotStarted, "quota"),
    (400, NotStarted, "refused"),
    (503, ProviderUnavailable, "unavailable"),
])  # fmt: skip
async def test_refusals_and_outages_are_plain(gemini, monkeypatch, status, kind, message):
    mock_http(monkeypatch, lambda request: httpx.Response(status, json={"error": {}}))
    with pytest.raises(kind, match=message) as caught:
        await script_writer().refine(REQUEST)
    assert "ai-studio-test-key" not in str(caught.value)


async def test_without_a_key_nothing_is_sent(gemini, monkeypatch):
    monkeypatch.setattr(gemini, "gemini_api_key", "")
    seen = mock_http(monkeypatch, lambda request: httpx.Response(500))
    with pytest.raises(NotStarted, match="GEMINI_API_KEY"):
        await script_writer().refine(REQUEST)
    assert seen == []


def test_the_estimate_follows_the_configured_prices(gemini, monkeypatch):
    writer = script_writer()
    base = writer.estimate_usd("script", 3000)
    assert Decimal("0.005") < base < Decimal("0.1")
    monkeypatch.setattr(gemini, "gemini_script_output_usd_per_million", 7.5)
    assert writer.estimate_usd("script", 3000) > base
