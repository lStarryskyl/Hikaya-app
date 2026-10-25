"""Transcription adapters (#13), ElevenLabs Scribe and Azure fast transcription, against
mocked HTTP: no live calls, no real keys."""

import json
from decimal import Decimal

import httpx
import pytest

from app.config import get_settings
from app.errors import UserFacingError
from app.providers import ProviderUnavailable, speech_to_text
from app.providers.speech import AzureSpeechToText, ElevenLabsSpeechToText, segments_from_words
from tests.http_mock import mock_http


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "story.mp3"
    path.write_bytes(b"ID3fake-mp3-bytes")
    return path


@pytest.fixture
def elevenlabs(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stt_provider", "elevenlabs")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "el-test-key")
    return settings


@pytest.fixture
def azure(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stt_provider", "azure")
    monkeypatch.setattr(settings, "azure_speech_key", "az-test-key")
    monkeypatch.setattr(settings, "azure_speech_region", "westeurope")
    monkeypatch.setattr(settings, "azure_speech_endpoint", "")
    return settings


def form_fields(request: httpx.Request) -> dict[str, str]:
    """Plain (non-file) multipart fields of a request."""
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields = {}
    for part in request.content.split(b"--" + boundary):
        if b"filename=" in part or b'name="' not in part:
            continue
        head, _, value = part.partition(b"\r\n\r\n")
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        fields[name] = value.rstrip(b"\r\n").decode()
    return fields


def word(text, start, end, kind="word"):
    return {"text": text, "start": start, "end": end, "type": kind, "logprob": -0.1}


SCRIBE = {
    "language_code": "ara",
    "language_probability": 0.98,
    "text": "كان سيدي يشعل الفانوس. وكل الحارة تعرف.",
    "words": [
        word("كان", 0.10, 0.40),
        word(" ", 0.40, 0.45, "spacing"),
        word("سيدي", 0.45, 0.90),
        word(" ", 0.90, 0.95, "spacing"),
        word("يشعل", 0.95, 1.40),
        word("الفانوس.", 1.45, 2.10),
        word("(laughs)", 2.10, 2.60, "audio_event"),
        word("وكل", 3.50, 3.80),
        word("الحارة", 3.85, 4.30),
        word("تعرف.", 4.35, 4.90),
    ],
}


# --- grouping words into lines ---


def test_words_become_lines_at_sentence_ends_and_pauses():
    lines = segments_from_words(
        [(0, 400, "One"), (450, 900, "two."), (950, 1300, "Three"), (3000, 3400, "four")]
    )
    assert [(s.start_ms, s.end_ms, s.text) for s in lines] == [
        (0, 1300, "One two. Three"),
        (3000, 3400, "four"),
    ]


def test_long_runs_are_split_so_lines_stay_short():
    words = [(i * 500, i * 500 + 400, f"w{i}") for i in range(60)]  # 30 s, no punctuation
    lines = segments_from_words(words)
    assert len(lines) > 1
    assert all(s.end_ms - s.start_ms <= 15_000 for s in lines)
    assert " ".join(s.text for s in lines) == " ".join(w[2] for w in words)


# --- ElevenLabs Scribe ---


def test_the_setting_selects_scribe(elevenlabs):
    assert isinstance(speech_to_text(), ElevenLabsSpeechToText)


def test_scribe_needs_its_key(elevenlabs, monkeypatch):
    monkeypatch.setattr(elevenlabs, "elevenlabs_api_key", "")
    with pytest.raises(ProviderUnavailable, match="ELEVENLABS_API_KEY"):
        speech_to_text()


async def test_scribe_request_and_segments(elevenlabs, monkeypatch, audio):
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=SCRIBE))
    transcript = await speech_to_text().transcribe(audio, "jordanian", 5000)
    (request,) = seen
    assert str(request.url) == "https://api.elevenlabs.io/v1/speech-to-text"
    assert request.headers["xi-api-key"] == "el-test-key"
    fields = form_fields(request)
    assert fields["model_id"] == "scribe_v2"
    assert fields["language_code"] == "ara"
    assert fields["timestamps_granularity"] == "word"
    assert fields["tag_audio_events"] == "false"
    assert fields["diarize"] == "false"
    assert b"ID3fake-mp3-bytes" in request.content
    assert transcript.language == "jordanian"
    assert [s.text for s in transcript.segments] == ["كان سيدي يشعل الفانوس.", "وكل الحارة تعرف."]
    assert (transcript.segments[0].start_ms, transcript.segments[-1].end_ms) == (100, 4900)


async def test_scribe_detects_the_language_when_not_told(elevenlabs, monkeypatch, audio):
    english = {**SCRIBE, "language_code": "eng", "words": [word("Hello.", 0.0, 0.5)]}
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=english))
    transcript = await speech_to_text().transcribe(audio, None, 1000)
    assert "language_code" not in form_fields(seen[0])
    assert transcript.language == "english"


async def test_scribe_detected_arabic_is_taken_as_the_spoken_dialect(
    elevenlabs, monkeypatch, audio
):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=SCRIBE))
    assert (await speech_to_text().transcribe(audio, None, 5000)).language == "jordanian"


@pytest.mark.parametrize(
    "body", [{"text": "no words"}, {"words": "nope"}, {"words": [{"text": "x"}]}, ["list"]]
)
async def test_scribe_malformed_answers_are_refused(elevenlabs, monkeypatch, audio, body):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(UserFacingError, match="unexpected answer"):
        await speech_to_text().transcribe(audio, "english", 1000)


@pytest.mark.parametrize(
    ("status", "message"), [(401, "rejected the key"), (429, "busy"), (503, "unavailable")]
)
async def test_scribe_errors(elevenlabs, monkeypatch, audio, status, message):
    mock_http(monkeypatch, lambda request: httpx.Response(status, json={"detail": "x"}))
    with pytest.raises(UserFacingError, match=message) as caught:
        await speech_to_text().transcribe(audio, "english", 1000)
    assert "el-test-key" not in str(caught.value)


def test_scribe_cost_is_per_audio_hour(elevenlabs):
    stt = speech_to_text()
    assert stt.budget == "card"
    assert stt.estimate_usd("transcribe", 3_600_000) == Decimal("0.22")


# --- Azure fast transcription ---

AZURE = {
    "durationMilliseconds": 5200,
    "combinedPhrases": [{"text": "..."}],
    "phrases": [
        {
            "offsetMilliseconds": 120,
            "durationMilliseconds": 2000,
            "text": "كان سيدي يشعل الفانوس.",
            "locale": "ar-JO",
            "confidence": 0.9,
            "words": [],
        },
        {
            "offsetMilliseconds": 3500,
            "durationMilliseconds": 1400,
            "text": "وكل الحارة تعرف.",
            "locale": "ar-JO",
            "confidence": 0.9,
            "words": [],
        },
    ],
}


def test_the_setting_selects_azure_speech(azure):
    assert isinstance(speech_to_text(), AzureSpeechToText)


def test_azure_speech_needs_a_key_and_a_region_or_endpoint(azure, monkeypatch):
    monkeypatch.setattr(azure, "azure_speech_region", "")
    with pytest.raises(ProviderUnavailable, match="AZURE_SPEECH_REGION"):
        speech_to_text()
    monkeypatch.setattr(
        azure, "azure_speech_endpoint", "https://hikaya.cognitiveservices.azure.com"
    )
    assert speech_to_text()
    monkeypatch.setattr(azure, "azure_speech_key", "")
    with pytest.raises(ProviderUnavailable, match="AZURE_SPEECH_KEY"):
        speech_to_text()


async def test_azure_request_and_segments(azure, monkeypatch, audio):
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=AZURE))
    transcript = await speech_to_text().transcribe(audio, "jordanian", 5200)
    (request,) = seen
    assert request.url.host == "westeurope.api.cognitive.microsoft.com"
    assert request.url.path == "/speechtotext/transcriptions:transcribe"
    assert request.url.params["api-version"] == "2025-10-15"
    assert request.headers["Ocp-Apim-Subscription-Key"] == "az-test-key"
    definition = json.loads(form_fields(request)["definition"])
    assert definition["locales"] == ["ar-JO"]
    assert definition["profanityFilterMode"] == "None"
    assert transcript.language == "jordanian"
    assert [(s.start_ms, s.end_ms, s.text) for s in transcript.segments] == [
        (120, 2120, "كان سيدي يشعل الفانوس."),
        (3500, 4900, "وكل الحارة تعرف."),
    ]


async def test_azure_identifies_the_language_when_not_told(azure, monkeypatch, audio):
    english = {**AZURE, "phrases": [{**AZURE["phrases"][0], "locale": "en-US", "text": "Hi."}]}
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=english))
    transcript = await speech_to_text().transcribe(audio, None, 5200)
    assert json.loads(form_fields(seen[0])["definition"])["locales"] == ["ar-JO", "en-US"]
    assert transcript.language == "english"


async def test_azure_uses_a_resource_endpoint_when_given(azure, monkeypatch, audio):
    monkeypatch.setattr(
        azure, "azure_speech_endpoint", "https://hikaya.cognitiveservices.azure.com/"
    )
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=AZURE))
    await speech_to_text().transcribe(audio, "english", 5200)
    assert seen[0].url.host == "hikaya.cognitiveservices.azure.com"


@pytest.mark.parametrize("body", [{"phrases": "x"}, {"phrases": [{"text": "no times"}]}, []])
async def test_azure_malformed_answers_are_refused(azure, monkeypatch, audio, body):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(UserFacingError, match="unexpected answer"):
        await speech_to_text().transcribe(audio, "english", 1000)


@pytest.mark.parametrize(("status", "message"), [(401, "rejected the key"), (429, "busy")])
async def test_azure_errors(azure, monkeypatch, audio, status, message):
    mock_http(monkeypatch, lambda request: httpx.Response(status, json={"error": {"code": "x"}}))
    with pytest.raises(UserFacingError, match=message) as caught:
        await speech_to_text().transcribe(audio, "english", 1000)
    assert "az-test-key" not in str(caught.value)


def test_azure_cost_is_per_audio_hour_on_the_azure_budget(azure):
    stt = speech_to_text()
    assert stt.budget == "azure"
    assert stt.estimate_usd("transcribe", 3_600_000) == Decimal("0.36")


# --- through the worker ---


async def test_an_upload_is_transcribed_by_scribe_in_the_worker(
    elevenlabs, monkeypatch, client, sessionmaker, tmp_path
):
    import subprocess

    from tests.test_moderation import drain, sign_up

    monkeypatch.setattr(elevenlabs, "live_ai_enabled", True)
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=SCRIBE))
    tone = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=5", "-ac", "1", str(tone)],
        check=True,
    )
    await sign_up(client)
    story = (await client.post("/api/v1/stories", json={"original_language": "jordanian"})).json()
    with open(tone, "rb") as f:
        await client.put(
            f"/api/v1/stories/{story['id']}/audio", files={"file": ("t.wav", f, "audio/wav")}
        )
    await drain(sessionmaker)
    layers = (await client.get(f"/api/v1/stories/{story['id']}")).json()["layers"]
    verbatim = next(la for la in layers if la["kind"] == "verbatim")
    assert [s["text"] for s in verbatim["segments"]] == [
        "كان سيدي يشعل الفانوس.",
        "وكل الحارة تعرف.",
    ]
    assert len(seen) == 1  # the language model steps stayed on the fake
