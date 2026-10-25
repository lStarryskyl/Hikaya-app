"""Transcription adapters (#13): ElevenLabs Scribe and Azure AI Speech fast transcription.

Both return timestamped lines (segments) for the player to highlight. Scribe returns words,
which are grouped into lines at sentence ends, pauses and a maximum length; Azure returns
phrases, which are used as they come. The cost is per hour of audio.
"""

import json
from decimal import Decimal
from pathlib import Path

import httpx

from app.config import get_settings
from app.errors import UserFacingError
from app.providers import ProviderUnavailable, Segment, Transcript

TIMEOUT_SECONDS = 300
MS_PER_HOUR = Decimal(3_600_000)

# Grouping words into lines.
SENTENCE_END = (".", "!", "?", "؟", "…")
PAUSE_MS = 800
MIN_SENTENCE_MS = 1500
MAX_LINE_MS = 12_000


def segments_from_words(words: list[tuple[int, int, str]]) -> list[Segment]:
    """(start_ms, end_ms, text) words in order -> lines that read naturally and stay short."""
    lines: list[Segment] = []
    current: list[tuple[int, int, str]] = []

    def close() -> None:
        if current:
            text = " ".join(w[2] for w in current).strip()
            lines.append(Segment(start_ms=current[0][0], end_ms=current[-1][1], text=text))
            current.clear()

    for start, end, text in words:
        if current and (start - current[-1][1] >= PAUSE_MS or end - current[0][0] > MAX_LINE_MS):
            close()
        current.append((start, end, text))
        if text.endswith(SENTENCE_END) and end - current[0][0] >= MIN_SENTENCE_MS:
            close()
    close()
    return lines


def _unexpected(service: str) -> UserFacingError:
    return UserFacingError(f"The {service} gave an unexpected answer; try again.")


def _raise_for_status(response: httpx.Response, service: str, key_env: str) -> None:
    status = response.status_code
    if status < 400:
        return
    if status in (401, 403):
        raise ProviderUnavailable(f"The {service} rejected the key; check {key_env}.")
    if status == 429:
        raise ProviderUnavailable(f"The {service} is busy; try again shortly.")
    if status in (400, 413, 415, 422):
        raise UserFacingError(f"The {service} could not read this recording.")
    raise ProviderUnavailable(f"The {service} is unavailable right now.")


def _missing(*pairs: tuple[str, str]) -> None:
    missing = [env for env, value in pairs if not value]
    if missing:
        raise ProviderUnavailable(
            "Transcription is not configured: set " + ", ".join(missing) + "."
        )


class ElevenLabsSpeechToText:
    """POST https://api.elevenlabs.io/v1/speech-to-text (multipart), word timestamps."""

    name = "elevenlabs"
    budget = "card"
    service = "ElevenLabs transcription service"
    URL = "https://api.elevenlabs.io/v1/speech-to-text"
    # Our languages -> ISO 639-3; Scribe has no separate code for a dialect.
    CODES = {"jordanian": "ara", "msa": "ara", "english": "eng"}

    def __init__(self) -> None:
        settings = get_settings()
        _missing(("ELEVENLABS_API_KEY", settings.elevenlabs_api_key))
        self.key = settings.elevenlabs_api_key
        self.model = settings.elevenlabs_stt_model
        self.per_hour = Decimal(str(settings.elevenlabs_stt_usd_per_hour))

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return self.per_hour * Decimal(units) / MS_PER_HOUR

    async def transcribe(self, audio: Path, language: str | None, duration_ms: int) -> Transcript:
        data = {
            "model_id": self.model,
            "timestamps_granularity": "word",
            "tag_audio_events": "false",
            "diarize": "false",
        }
        if language:
            data["language_code"] = self.CODES.get(language, "ara")
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                with audio.open("rb") as f:
                    response = await client.post(
                        self.URL,
                        headers={"xi-api-key": self.key},
                        data=data,
                        files={"file": (audio.name, f, "audio/mpeg")},
                    )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"The {self.service} could not be reached.") from exc
        _raise_for_status(response, self.service, "ELEVENLABS_API_KEY")
        try:
            body = response.json()
            words = [
                (round(float(w["start"]) * 1000), round(float(w["end"]) * 1000), w["text"].strip())
                for w in body["words"]
                if w.get("type", "word") == "word" and w["text"].strip()
            ]
            detected = body.get("language_code", "")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise _unexpected(self.service) from exc
        # A detected Arabic recording is taken as the spoken dialect, the app's default.
        spoken = language or ("english" if str(detected).startswith("en") else "jordanian")
        return Transcript(language=spoken, segments=segments_from_words(words))


class AzureSpeechToText:
    """Azure AI Speech fast transcription (synchronous REST), phrase timestamps."""

    name = "azure"
    budget = "azure"
    service = "Azure transcription service"
    API_VERSION = "2025-10-15"

    def __init__(self) -> None:
        settings = get_settings()
        _missing(("AZURE_SPEECH_KEY", settings.azure_speech_key))
        if not settings.azure_speech_endpoint:
            _missing(("AZURE_SPEECH_REGION", settings.azure_speech_region))
        base = settings.azure_speech_endpoint.rstrip("/") or (
            f"https://{settings.azure_speech_region}.api.cognitive.microsoft.com"
        )
        self.url = f"{base}/speechtotext/transcriptions:transcribe"
        self.key = settings.azure_speech_key
        self.arabic = settings.azure_speech_arabic_locale
        self.per_hour = Decimal(str(settings.azure_stt_usd_per_hour))

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return self.per_hour * Decimal(units) / MS_PER_HOUR

    def _locales(self, language: str | None) -> list[str]:
        if language == "english":
            return ["en-US"]
        if language in ("jordanian", "msa"):
            return [self.arabic]
        return [self.arabic, "en-US"]  # several locales: Azure identifies the language

    async def transcribe(self, audio: Path, language: str | None, duration_ms: int) -> Transcript:
        definition = {"locales": self._locales(language), "profanityFilterMode": "None"}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                with audio.open("rb") as f:
                    response = await client.post(
                        self.url,
                        params={"api-version": self.API_VERSION},
                        headers={"Ocp-Apim-Subscription-Key": self.key},
                        data={"definition": json.dumps(definition)},
                        files={"audio": (audio.name, f, "audio/mpeg")},
                    )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"The {self.service} could not be reached.") from exc
        _raise_for_status(response, self.service, "AZURE_SPEECH_KEY")
        try:
            phrases = response.json()["phrases"]
            segments = [
                Segment(
                    start_ms=int(p["offsetMilliseconds"]),
                    end_ms=int(p["offsetMilliseconds"]) + int(p["durationMilliseconds"]),
                    text=str(p["text"]).strip(),
                )
                for p in phrases
                if str(p.get("text", "")).strip()
            ]
            locales = [str(p.get("locale", "")) for p in phrases]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise _unexpected(self.service) from exc
        english = sum(loc.startswith("en") for loc in locales)
        spoken = language or ("english" if english > len(locales) / 2 else "jordanian")
        return Transcript(language=spoken, segments=segments)
