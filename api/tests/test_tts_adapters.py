"""Narration voice adapters (#14), ElevenLabs and Azure, against mocked HTTP: no live calls,
no real keys."""

import base64
import json
import subprocess
from decimal import Decimal

import httpx
import pytest

from app.config import get_settings
from app.errors import UserFacingError
from app.providers import ProviderUnavailable, text_to_speech
from app.providers.tts import AzureTextToSpeech, ElevenLabsTextToSpeech
from tests.http_mock import mock_http


def mp3(seconds: float) -> bytes:
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=duration={seconds}",
         "-ac", "1", "-c:a", "libmp3lame", "-f", "mp3", "pipe:1"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip


@pytest.fixture(scope="module")
def two_seconds() -> bytes:
    return mp3(2)


@pytest.fixture
def elevenlabs(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "el-test-key")
    monkeypatch.setattr(settings, "elevenlabs_voice_arabic", "voice-ar")
    monkeypatch.setattr(settings, "elevenlabs_voice_english", "voice-en")
    return settings


@pytest.fixture
def azure(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tts_provider", "azure")
    monkeypatch.setattr(settings, "azure_speech_key", "az-test-key")
    monkeypatch.setattr(settings, "azure_speech_region", "westeurope")
    return settings


def aligned(text: str, audio: bytes, seconds_per_char=0.05) -> dict:
    """An ElevenLabs with-timestamps answer: one timing per character of `text`."""
    return {
        "audio_base64": base64.b64encode(audio).decode(),
        "alignment": {
            "characters": list(text),
            "character_start_times_seconds": [i * seconds_per_char for i in range(len(text))],
            "character_end_times_seconds": [(i + 1) * seconds_per_char for i in range(len(text))],
        },
        "normalized_alignment": None,
    }


def answering(audio: bytes):
    def respond(request):
        return httpx.Response(200, json=aligned(json.loads(request.content)["text"], audio))

    return respond


# --- ElevenLabs ---


def test_the_setting_selects_elevenlabs(elevenlabs):
    tts = text_to_speech()
    assert isinstance(tts, ElevenLabsTextToSpeech)
    assert tts.aligns is True and tts.budget == "card"


def test_default_voices_are_settings(elevenlabs):
    tts = text_to_speech()
    assert tts.voice_for("jordanian") == "voice-ar"
    assert tts.voice_for("msa") == "voice-ar"
    assert tts.voice_for("english") == "voice-en"


@pytest.mark.parametrize("missing", ["elevenlabs_api_key", "elevenlabs_voice_arabic"])
def test_missing_key_or_voice_is_named(elevenlabs, monkeypatch, missing):
    monkeypatch.setattr(elevenlabs, missing, "")
    with pytest.raises(ProviderUnavailable, match=missing.upper()):
        text_to_speech()


async def test_elevenlabs_request_audio_and_line_timings(elevenlabs, monkeypatch, two_seconds):
    seen = mock_http(monkeypatch, answering(two_seconds))
    lines = ["كان سيدي يشعل الفانوس.", "وكل الحارة تعرف."]
    speech = await text_to_speech().speak(lines, "jordanian", "voice-ar")
    (request,) = seen
    assert request.url.path == "/v1/text-to-speech/voice-ar/with-timestamps"
    assert request.url.params["output_format"] == "mp3_44100_128"
    assert request.headers["xi-api-key"] == "el-test-key"
    body = json.loads(request.content)
    assert body["model_id"] == "eleven_multilingual_v2"
    assert body["text"] == " ".join(lines)
    assert speech.audio == two_seconds
    # 50 ms per character; line two starts after line one and the space between them, and
    # the pause before it belongs to line one.
    second_start = (len(lines[0]) + 1) * 50
    assert speech.lines == [(0, second_start), (second_start, len(body["text"]) * 50)]


async def test_alignment_that_does_not_match_the_text_is_refused(
    elevenlabs, monkeypatch, two_seconds
):
    def respond(request):
        return httpx.Response(200, json=aligned("something else", two_seconds))

    mock_http(monkeypatch, respond)
    with pytest.raises(UserFacingError, match="unexpected answer"):
        await text_to_speech().speak(["one line"], "english", "voice-en")


@pytest.mark.parametrize(
    "body", [{"audio_base64": "!!not base64!!", "alignment": None}, {"alignment": {}}, []]
)
async def test_elevenlabs_malformed_answers_are_refused(elevenlabs, monkeypatch, body):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(UserFacingError, match="unexpected answer"):
        await text_to_speech().speak(["one line"], "english", "voice-en")


async def test_long_stories_are_spoken_in_parts_and_timed_across_them(
    elevenlabs, monkeypatch, two_seconds
):
    monkeypatch.setattr(elevenlabs, "elevenlabs_tts_max_chars", 30)
    seen = mock_http(monkeypatch, answering(two_seconds))
    lines = ["first line of the story", "second line of it", "third line here"]
    speech = await text_to_speech().speak(lines, "english", "voice-en")
    assert [json.loads(r.content)["text"] for r in seen] == [
        "first line of the story",
        "second line of it",
        "third line here",
    ]
    assert speech.audio == two_seconds * 3
    # Each part starts where the audio before it ends (about 2 s per part).
    assert speech.lines[0][0] == 0
    assert 1900 <= speech.lines[1][0] <= 2200 and 3900 <= speech.lines[2][0] <= 4300
    assert all(a[1] == b[0] for a, b in zip(speech.lines, speech.lines[1:], strict=False))


async def test_a_single_line_over_the_limit_is_refused(elevenlabs, monkeypatch):
    monkeypatch.setattr(elevenlabs, "elevenlabs_tts_max_chars", 10)
    with pytest.raises(UserFacingError, match="too long"):
        await text_to_speech().speak(["this line is far too long"], "english", "voice-en")


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "rejected the key"), (404, "voice"), (429, "busy"), (500, "unavailable")],
)
async def test_elevenlabs_errors(elevenlabs, monkeypatch, status, message):
    mock_http(monkeypatch, lambda request: httpx.Response(status, json={"detail": "x"}))
    with pytest.raises(UserFacingError, match=message) as caught:
        await text_to_speech().speak(["line"], "english", "voice-en")
    assert "el-test-key" not in str(caught.value)


def test_elevenlabs_cost_is_per_character(elevenlabs):
    assert text_to_speech().estimate_usd("speak", 1000) == Decimal("0.08")


# --- Azure ---


def test_the_setting_selects_azure(azure):
    tts = text_to_speech()
    assert isinstance(tts, AzureTextToSpeech)
    assert tts.aligns is False and tts.budget == "azure"
    assert tts.voice_for("jordanian") == "ar-JO-SanaNeural"
    assert tts.voice_for("english").startswith("en-US-")


def test_azure_voice_needs_a_key_and_region(azure, monkeypatch):
    monkeypatch.setattr(azure, "azure_speech_region", "")
    with pytest.raises(ProviderUnavailable, match="AZURE_SPEECH_REGION"):
        text_to_speech()


async def test_azure_sends_escaped_ssml_and_returns_mp3(azure, monkeypatch, two_seconds):
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, content=two_seconds))
    speech = await text_to_speech().speak(["Salt & <pepper>"], "english", "en-US-JennyNeural")
    (request,) = seen
    assert str(request.url) == "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1"
    assert request.headers["Ocp-Apim-Subscription-Key"] == "az-test-key"
    assert request.headers["Content-Type"] == "application/ssml+xml"
    assert request.headers["X-Microsoft-OutputFormat"] == "audio-24khz-96kbitrate-mono-mp3"
    ssml = request.content.decode()
    assert "<voice name='en-US-JennyNeural'>" in ssml and "xml:lang='en-US'" in ssml
    assert "Salt &amp; &lt;pepper&gt;" in ssml
    assert speech.audio == two_seconds and speech.lines is None


async def test_azure_arabic_uses_the_jordanian_locale(azure, monkeypatch, two_seconds):
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, content=two_seconds))
    await text_to_speech().speak(["الفانوس"], "msa", "ar-JO-SanaNeural")
    assert "xml:lang='ar-JO'" in seen[0].content.decode()


async def test_an_empty_or_non_audio_answer_is_refused(azure, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b""))
    with pytest.raises(UserFacingError, match="unexpected answer"):
        await text_to_speech().speak(["line"], "english", "en-US-JennyNeural")


@pytest.mark.parametrize(("status", "message"), [(401, "rejected the key"), (429, "busy")])
async def test_azure_errors(azure, monkeypatch, status, message):
    mock_http(monkeypatch, lambda request: httpx.Response(status))
    with pytest.raises(UserFacingError, match=message) as caught:
        await text_to_speech().speak(["line"], "english", "en-US-JennyNeural")
    assert "az-test-key" not in str(caught.value)


def test_azure_cost_is_per_character(azure):
    assert text_to_speech().estimate_usd("speak", 1_000_000) == Decimal("15")


# --- through the worker ---


async def test_a_story_is_narrated_by_elevenlabs_with_its_timings(
    elevenlabs, monkeypatch, client, sessionmaker, tmp_path
):
    from tests.test_moderation import sign_up
    from tests.test_narration import publish, story_with_photo
    from tests.test_story_photos import make_image

    monkeypatch.setattr(elevenlabs, "live_ai_enabled", True)
    seen = mock_http(monkeypatch, answering(mp3(6)))
    tone = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=6", "-ac", "1", str(tone)],
        check=True,
    )
    await sign_up(client)
    story_id = await story_with_photo(
        client, sessionmaker, tone, [make_image(tmp_path / "photo.png")]
    )
    story = await publish(client, sessionmaker, story_id)
    narration = story["narration"]
    assert narration["timing"] == "alignment" and narration["voice"] == "voice-ar"
    assert len(seen) == 1  # the whole text in one call
    assert narration["segments"][0]["start_ms"] == 0
    assert story["slideshow"] is not None  # the slideshow carries the real narration
