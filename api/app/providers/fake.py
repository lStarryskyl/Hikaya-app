"""Deterministic fake providers for tests and offline demos.

They speak from a small parallel corpus, so a "transcript" in Jordanian Arabic has a real
English and MSA translation. Every call is recorded in CALLS. A kind listed in FAIL_ON
fails, as a provider outage would.
"""

import asyncio
from decimal import Decimal
from pathlib import Path

from app.providers import ProviderUnavailable, Segment, Speech, Transcript

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
# Tests can make a fake behave as a paid provider: {"transcribe" | "llm" | "tts": (budget, price)}.
PAID: dict[str, tuple[str, str]] = {}
# Whether the fake voice returns alignment data (a list, so tests can switch it in place).
TTS_ALIGNMENT = [True]


def reset() -> None:
    CALLS.clear()
    FAIL_ON.clear()
    PAID.clear()
    TTS_ALIGNMENT[0] = True


class _Priced:
    kind = ""

    @property
    def budget(self) -> str | None:
        return PAID[self.kind][0] if self.kind in PAID else None

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return Decimal(PAID[self.kind][1]) if self.kind in PAID else Decimal("0")


def _check(kind: str) -> None:
    if kind in FAIL_ON:
        service = {"transcribe": "transcription service", "speak": "voice service"}
        raise ProviderUnavailable(
            f"The {service.get(kind, 'language model')} is unavailable right now."
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


# Words that make the fake moderator raise a label, so tests and rehearsals are predictable.
MODERATION_MARKERS = {
    "hate": ("hateful", "hate speech"),
    "violence": ("kill", "weapon", "threat"),
    "sexual": ("explicit",),
    "other_terrible": ("terrible-test",),
}


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

    async def moderate(self, texts: list[str]) -> dict[str, dict]:
        CALLS.append(("moderate", str(len(texts))))
        _check("moderate")
        joined = " ".join(texts).lower()
        out = {}
        for label, words in MODERATION_MARKERS.items():
            hit = next((w for w in words if w in joined), None)
            out[label] = {
                "raised": hit is not None,
                "reason": f'The text mentions "{hit}".' if hit else "",
            }
        return out


# The fake voice "reads" each line as a quiet tone whose length follows the text, so timings
# and the player behave as they would with a real voice.
MS_PER_CHAR = 60
LINE_MIN_MS, LINE_MAX_MS = 900, 6000


def fake_line_ms(text: str) -> int:
    return max(LINE_MIN_MS, min(LINE_MAX_MS, len(text) * MS_PER_CHAR))


async def _tone_mp3(duration_ms: int) -> bytes:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
        "-i", f"sine=frequency=330:sample_rate=44100:duration={duration_ms / 1000}",
        "-af", "volume=0.2", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "pipe:1",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    out, err = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"fake voice: {err.decode(errors='replace')}")
    return out


class FakeTextToSpeech(_Priced):
    name = "fake"
    kind = "tts"

    @property
    def aligns(self) -> bool:
        return TTS_ALIGNMENT[0]

    def voice_for(self, language: str) -> str:
        return "fake-english" if language == "english" else "fake-jordanian"

    async def speak(self, texts: list[str], language: str, voice: str) -> Speech:
        CALLS.append(("speak", language, voice, str(len(texts))))
        _check("speak")
        lines, at = [], 0
        for text in texts:
            lines.append((at, at + fake_line_ms(text)))
            at += fake_line_ms(text)
        return Speech(audio=await _tone_mp3(at), lines=lines if self.aligns else None)
