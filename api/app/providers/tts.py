"""Narration voice adapters (#14): ElevenLabs and Azure AI Speech neural voices.

ElevenLabs returns a timing for every character, which becomes a start and end time for
each line, so a whole story is spoken in one call (split into parts only past the
per-request character limit). Azure's REST voice gives no timings, so narration speaks it
line by line and measures each piece (`aligns = False`). Both return MP3. The cost is per
character; voices are settings.
"""

import asyncio
import base64
import binascii
import tempfile
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

import httpx

from app import audio
from app.config import get_settings
from app.errors import UserFacingError
from app.providers import ProviderUnavailable, Speech

TIMEOUT_SECONDS = 180
SEPARATOR = " "  # between lines, so the voice reads them as one flowing text


def _missing(*pairs: tuple[str, str]) -> None:
    missing = [env for env, value in pairs if not value]
    if missing:
        raise ProviderUnavailable("Narration is not configured: set " + ", ".join(missing) + ".")


def _unexpected(service: str) -> UserFacingError:
    return UserFacingError(f"The {service} gave an unexpected answer; try again.")


def _raise_for_status(response: httpx.Response, service: str, key_env: str) -> None:
    status = response.status_code
    if status < 400:
        return
    if status in (401, 403):
        raise ProviderUnavailable(f"The {service} rejected the key; check {key_env}.")
    if status == 404:
        raise ProviderUnavailable(
            f"The {service} could not find the voice; check the voice setting."
        )
    if status == 429:
        raise ProviderUnavailable(f"The {service} is busy; try again shortly.")
    if status in (400, 422):
        raise UserFacingError(f"The {service} refused this text.")
    raise ProviderUnavailable(f"The {service} is unavailable right now.")


async def _duration_ms(mp3: bytes) -> int:
    """How long an MP3 plays, measured with ffprobe."""
    with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
        await asyncio.to_thread(f.write, mp3)
        await asyncio.to_thread(f.flush)
        return await audio.duration_ms(Path(f.name))


class ElevenLabsTextToSpeech:
    """POST https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"""

    name = "elevenlabs"
    budget = "card"
    aligns = True
    service = "ElevenLabs voice service"
    URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"
    OUTPUT_FORMAT = "mp3_44100_128"

    def __init__(self) -> None:
        settings = get_settings()
        _missing(
            ("ELEVENLABS_API_KEY", settings.elevenlabs_api_key),
            ("ELEVENLABS_VOICE_ARABIC", settings.elevenlabs_voice_arabic),
            ("ELEVENLABS_VOICE_ENGLISH", settings.elevenlabs_voice_english),
        )
        self.key = settings.elevenlabs_api_key
        self.voices = {
            "arabic": settings.elevenlabs_voice_arabic,
            "english": settings.elevenlabs_voice_english,
        }
        self.model = settings.elevenlabs_tts_model
        self.max_chars = settings.elevenlabs_tts_max_chars
        self.per_1k = Decimal(str(settings.elevenlabs_tts_usd_per_1k_chars))

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return self.per_1k * Decimal(units) / Decimal(1000)

    def voice_for(self, language: str) -> str:
        return self.voices["english" if language == "english" else "arabic"]

    def _parts(self, texts: list[str]) -> list[list[str]]:
        """Consecutive lines grouped so that each part stays within the character limit."""
        parts: list[list[str]] = [[]]
        for text in texts:
            if len(text) > self.max_chars:
                raise UserFacingError("A line of this story is too long to narrate in one piece.")
            if parts[-1] and len(SEPARATOR.join([*parts[-1], text])) > self.max_chars:
                parts.append([])
            parts[-1].append(text)
        return parts

    async def speak(self, texts: list[str], language: str, voice: str) -> Speech:
        parts = self._parts(texts)
        chunks: list[bytes] = []
        lines: list[tuple[int, int]] = []
        offset = 0
        for part in parts:
            mp3, timings = await self._speak_part(part, voice)
            chunks.append(mp3)
            lines += [(start + offset, end + offset) for start, end in timings]
            if len(parts) > 1:
                # Later parts are timed from where the audio before them ends.
                offset += await _duration_ms(mp3)
        # Lines meet end to end: a pause belongs to the line just spoken, so every moment
        # highlights a line and none lights up before its words begin.
        joined = [
            (0 if i == 0 else start, lines[i + 1][0] if i + 1 < len(lines) else end)
            for i, (start, end) in enumerate(lines)
        ]
        return Speech(audio=b"".join(chunks), lines=joined)

    async def _speak_part(self, part: list[str], voice: str) -> tuple[bytes, list[tuple[int, int]]]:
        text = SEPARATOR.join(part)
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self.URL.format(voice=voice),
                    params={"output_format": self.OUTPUT_FORMAT},
                    headers={"xi-api-key": self.key},
                    json={"text": text, "model_id": self.model},
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"The {self.service} could not be reached.") from exc
        _raise_for_status(response, self.service, "ELEVENLABS_API_KEY")
        try:
            body = response.json()
            mp3 = base64.b64decode(body["audio_base64"], validate=True)
            alignment = body["alignment"]
            characters = alignment["characters"]
            starts = alignment["character_start_times_seconds"]
            ends = alignment["character_end_times_seconds"]
        except (ValueError, KeyError, TypeError, binascii.Error) as exc:
            raise _unexpected(self.service) from exc
        if not mp3 or "".join(characters) != text or not len(starts) == len(ends) == len(text):
            raise _unexpected(self.service)
        timings, at, previous_end = [], 0, 0
        for line in part:
            if line:
                first, last = at, at + len(line) - 1
                timings.append((round(starts[first] * 1000), round(ends[last] * 1000)))
                previous_end = timings[-1][1]
            else:
                # Nothing to say: a zero-length line where the last one ended.
                timings.append((previous_end, previous_end))
            at += len(line) + len(SEPARATOR)
        return mp3, timings


class AzureTextToSpeech:
    """POST https://{region}.tts.speech.microsoft.com/cognitiveservices/v1 with SSML."""

    name = "azure"
    budget = "azure"
    aligns = False  # the REST voice gives no timings: narration measures each line
    service = "Azure voice service"
    OUTPUT_FORMAT = "audio-24khz-96kbitrate-mono-mp3"

    def __init__(self) -> None:
        settings = get_settings()
        _missing(
            ("AZURE_SPEECH_KEY", settings.azure_speech_key),
            ("AZURE_SPEECH_REGION", settings.azure_speech_region),
        )
        self.url = (
            f"https://{settings.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1"
        )
        self.key = settings.azure_speech_key
        self.voices = {
            "arabic": settings.azure_tts_voice_arabic,
            "english": settings.azure_tts_voice_english,
        }
        self.arabic_locale = settings.azure_speech_arabic_locale
        self.per_1k = Decimal(str(settings.azure_tts_usd_per_1k_chars))

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return self.per_1k * Decimal(units) / Decimal(1000)

    def voice_for(self, language: str) -> str:
        return self.voices["english" if language == "english" else "arabic"]

    async def speak(self, texts: list[str], language: str, voice: str) -> Speech:
        locale = "en-US" if language == "english" else self.arabic_locale
        ssml = (
            f"<speak version='1.0' xml:lang='{locale}'>"
            f"<voice name='{escape(voice, {chr(39): '&apos;'})}'>"
            f"{escape(SEPARATOR.join(texts))}</voice></speak>"
        )
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self.url,
                    headers={
                        "Ocp-Apim-Subscription-Key": self.key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": self.OUTPUT_FORMAT,
                        "User-Agent": "hikaya",
                    },
                    content=ssml.encode(),
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"The {self.service} could not be reached.") from exc
        _raise_for_status(response, self.service, "AZURE_SPEECH_KEY")
        if not response.content or response.headers.get("content-type", "audio").startswith(
            ("text/", "application/json")
        ):
            raise _unexpected(self.service)
        return Speech(audio=response.content, lines=None)
