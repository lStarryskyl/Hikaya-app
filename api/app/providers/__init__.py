"""AI providers behind one interface per kind, chosen by setting.

Callers ask for `speech_to_text()`, `language_model()` or `text_to_speech()` and never import a
provider
directly, so switching provider is a setting change, not a code change.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from app.config import get_settings
from app.errors import UserFacingError


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class Transcript:
    language: str  # jordanian | msa | english
    segments: list[Segment]


class SpeechToText(Protocol):
    name: str
    # "card" or "azure" for a paid provider; None for a free one (no ledger, no live switch).
    budget: str | None

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        """Expected cost; units are milliseconds of audio."""
        ...

    async def transcribe(self, audio: Path, language: str | None, duration_ms: int) -> Transcript:
        """Timestamped segments. `language` is the speaker's choice, or None to detect it."""
        ...


class LanguageModel(Protocol):
    name: str
    budget: str | None

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        """Expected cost; units are characters of input text."""
        ...

    async def polish(self, texts: list[str], language: str) -> list[str]:
        """Light clean-up in the same language, one output line per input line."""
        ...

    async def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        """Translation to `english` or `msa`, one output line per input line."""
        ...

    async def moderate(self, texts: list[str]) -> dict[str, dict]:
        """For each label in MODERATION_LABELS: {"raised": bool, "reason": str}."""
        ...


@dataclass(frozen=True)
class Speech:
    audio: bytes  # MP3
    # (start_ms, end_ms) for each input line, from the provider's alignment data; None when
    # the provider offers none.
    lines: list[tuple[int, int]] | None


class TextToSpeech(Protocol):
    name: str
    budget: str | None
    # True when `speak` returns timings per line, so a whole text can be spoken in one call.
    aligns: bool

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        """Expected cost; units are characters of text."""
        ...

    def voice_for(self, language: str) -> str:
        """The voice that reads text in this language (jordanian | msa | english)."""
        ...

    async def speak(self, texts: list[str], language: str, voice: str) -> Speech:
        """The lines read one after another, as one MP3."""
        ...


# Any raised label holds a story for staff review.
MODERATION_LABELS = ("hate", "violence", "sexual", "other_terrible")


class ProviderUnavailable(UserFacingError):
    pass


_NAMES = {"elevenlabs": "ElevenLabs", "azure": "Azure"}


def _not_connected(kind: str, name: str) -> ProviderUnavailable:
    label = _NAMES.get(name, name)
    return ProviderUnavailable(f"The {label} {kind} provider is not connected yet.")


def speech_to_text() -> SpeechToText:
    from app.providers import fake

    name = get_settings().stt_provider
    if name == "fake":
        return fake.FakeSpeechToText()
    raise _not_connected("transcription", name)


def language_model() -> LanguageModel:
    from app.providers import fake

    name = get_settings().llm_provider
    if name == "fake":
        return fake.FakeLanguageModel()
    if name == "azure":
        from app.providers.azure_llm import AzureLanguageModel

        return AzureLanguageModel()
    raise _not_connected("language model", name)


def text_to_speech() -> TextToSpeech:
    from app.providers import fake

    name = get_settings().tts_provider
    if name == "fake":
        return fake.FakeTextToSpeech()
    raise _not_connected("voice", name)
