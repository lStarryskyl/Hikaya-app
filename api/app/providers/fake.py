"""Deterministic fake providers for tests and offline demos.

They speak from a small parallel corpus, so a "transcript" in Jordanian Arabic has a real
English and MSA translation. Every call is recorded in CALLS. A kind listed in FAIL_ON
fails, as a provider outage would.
"""

from decimal import Decimal
from pathlib import Path

from app.providers import ProviderUnavailable, Segment, Transcript

# Each row says the same thing in Jordanian Arabic, Modern Standard Arabic and English.
CORPUS: list[dict[str, str]] = [
    {
        "jordanian": "كان سيدي يشعل الفانوس جنب الدرج الحجري كل مسا",
        "msa": "كان جدي يشعل الفانوس بجانب الدرج الحجري كل مساء",
        "english": "My grandfather lit the lantern by the stone stairway every evening",
    },
    {
        "jordanian": "وكل الحارة كانت تعرف إنه النهار خلص",
        "msa": "وكان الحي كله يعرف أن النهار قد انتهى",
        "english": "And the whole quarter knew that the day had ended",
    },
    {
        "jordanian": "ستي كانت تخبز الخبز على الصاج الصبح بكير",
        "msa": "كانت جدتي تخبز الخبز على الصاج في الصباح الباكر",
        "english": "My grandmother baked bread on the saj early in the morning",
    },
    {
        "jordanian": "والجيران ييجوا يشربوا قهوة ويحكوا قصص زمان",
        "msa": "وكان الجيران يأتون ليشربوا القهوة ويرووا قصص الماضي",
        "english": "And the neighbours came to drink coffee and tell old stories",
    },
    {
        "jordanian": "هاي الحكايات لازم ما تضيع",
        "msa": "هذه الحكايات يجب ألا تضيع",
        "english": "These stories must not be lost",
    },
]

SEGMENT_MS = 4000
_TERMINAL = (".", "!", "?", "؟", "。")

CALLS: list[tuple[str, ...]] = []
FAIL_ON: set[str] = set()
# Tests can make a fake behave as a paid provider: {"transcribe" | "llm": (budget, price)}.
PAID: dict[str, tuple[str, str]] = {}


def reset() -> None:
    CALLS.clear()
    FAIL_ON.clear()
    PAID.clear()


class _Priced:
    kind = ""

    @property
    def budget(self) -> str | None:
        return PAID[self.kind][0] if self.kind in PAID else None

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return Decimal(PAID[self.kind][1]) if self.kind in PAID else Decimal("0")


def _check(kind: str) -> None:
    if kind in FAIL_ON:
        raise ProviderUnavailable(
            "The language model is unavailable right now."
            if kind != "transcribe"
            else "The transcription service is unavailable right now."
        )


def _strip(text: str) -> str:
    return text.strip().rstrip("".join(_TERMINAL)).strip()


def _lookup(text: str) -> dict[str, str] | None:
    plain = _strip(text)
    return next((row for row in CORPUS if plain in row.values()), None)


class FakeSpeechToText(_Priced):
    name = "fake"
    kind = "transcribe"

    async def transcribe(self, audio: Path, language: str | None, duration_ms: int) -> Transcript:
        CALLS.append(("transcribe", audio.name, language or "auto"))
        _check("transcribe")
        spoken = language or "jordanian"  # "detects" Jordanian when not told
        count = max(1, min(200, -(-duration_ms // SEGMENT_MS)))
        segments = [
            Segment(
                start_ms=i * SEGMENT_MS,
                end_ms=min((i + 1) * SEGMENT_MS, duration_ms),
                text=CORPUS[i % len(CORPUS)][spoken],
            )
            for i in range(count)
        ]
        return Transcript(language=spoken, segments=segments)


class FakeLanguageModel(_Priced):
    name = "fake"
    kind = "llm"

    async def polish(self, texts: list[str], language: str) -> list[str]:
        CALLS.append(("polish", language, str(len(texts))))
        _check("polish")
        return [t.strip() if t.strip().endswith(_TERMINAL) else f"{t.strip()}." for t in texts]

    async def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        CALLS.append(("translate", source, target, str(len(texts))))
        _check("translate")
        out = []
        for t in texts:
            row = _lookup(t)
            out.append(f"{row[target]}." if row else f"[{target}] {_strip(t)}.")
        return out
