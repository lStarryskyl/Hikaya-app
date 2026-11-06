"""Screenwriters for narrated videos (docs/DECISIONS.md, "Refined shot scripts and the voice
choice for narrated videos"): they turn a story and its planned shots into one coherent shot
script for the video model, chosen by SCRIPT_PROVIDER.

`gemini` asks Gemini 3.8 Flash (Interactions API, Structured Outputs) for exactly one scene per
planned shot; `fake` keeps each shot's own words and calls nothing.
"""

import base64
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Protocol

import httpx

from app import gateway
from app.config import get_settings
from app.errors import UserFacingError
from app.providers import ProviderUnavailable, gemini

TIMEOUT_SECONDS = 180
LANGUAGES = {"jordanian": "Jordanian Arabic", "msa": "Modern Standard Arabic", "english": "English"}


@dataclass(frozen=True)
class ShotBrief:
    seconds: float
    words: str  # what the narrator says during the shot (English when there is a translation)


@dataclass(frozen=True)
class ScriptRequest:
    title: str
    place: str
    story: str  # the whole story, in English when there is a translation
    shots: list[ShotBrief]
    direction: str  # the staff's direction for the look of the film
    photo: bytes | None  # the WebP photo the film starts from
    spoken_language: str  # jordanian | msa | english
    audio: str  # soundtrack | omni


@dataclass(frozen=True)
class Scene:
    action: str
    camera: str
    sound: str


@dataclass(frozen=True)
class Screenplay:
    cast: str  # every recurring person, described once and kept identical
    setting: str  # the places, the route through them, the period and the light
    narrator: str  # the narrator's voice (used when Omni speaks the words)
    scenes: list[Scene]

    def to_dict(self) -> dict:
        return {
            "cast": self.cast,
            "setting": self.setting,
            "narrator": self.narrator,
            "shots": [asdict(scene) for scene in self.scenes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Screenplay":
        return cls(
            str(data.get("cast", "")),
            str(data.get("setting", "")),
            str(data.get("narrator", "")),
            [
                Scene(str(s.get("action", "")), str(s.get("camera", "")), str(s.get("sound", "")))
                for s in data.get("shots", [])
                if isinstance(s, dict)
            ],
        )


class ScriptWriter(Protocol):
    name: str
    budget: str | None

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        """Expected cost; units are characters of the request."""
        ...

    async def refine(self, request: ScriptRequest) -> Screenplay: ...


class FakeScriptWriter:
    """No call: each shot's scene is its own words, as before scripts were refined."""

    name = "fake_script"
    budget = None

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return Decimal(0)

    async def refine(self, request: ScriptRequest) -> Screenplay:
        return Screenplay("", "", "", [Scene(shot.words, "", "") for shot in request.shots])


SCREENWRITER = """You are the screenwriter for a short narrated film of a heritage story from \
Jordan. An AI video model will make the film one shot at a time: the first shot starts from the \
attached photo, and every later shot starts from the last frame of the shot before it. Write \
the shot script it will follow.

Story: "{title}", set in {place}.
{story}

The narrator's words decide what each shot shows. The shots, in order, with their length and \
the words spoken during them:
{shots}

Staff direction for the look of the film: {direction}

Rules for one continuous, believable film:
- Geography: follow one route through real, plausible places. Each shot starts where the \
previous one ended; never return to a place the film has just left unless the words do, and \
never use a tunnel, door or cut to jump somewhere impossible. If the story moves in time (a \
memory, then today), make the change visible and gradual, for example a slow move into warm \
lamplight, and keep the same place.
- Objects and people: every person and object must be set up before it is used. If tea is \
poured, someone brings or prepares it first, on screen; nothing appears out of nowhere.
- Cast: describe every recurring person once, precisely (age, face, hair, clothes), and keep \
them identical in every shot.
- Each shot: one clear action that shows what its words describe and fits its length, and one \
camera move that continues from where the previous shot ended.
- Sound: describe the natural sounds of each shot (footsteps on stone or sand, cloth, wind, a \
kettle, a match). {audio_note}
- Write plain visual descriptions in English. No on-screen text, captions or logos; nobody \
speaks to the camera.
Answer in JSON with the cast, the setting (the places, route, period and light), the \
narrator's voice (age, warmth, pace) and exactly {count} shots in order."""

AUDIO_NOTES = {
    "soundtrack": "The narration is recorded separately; the sounds you describe will be added "
    "under it later.",
    "omni": "The film's own audio is used: an off-screen narrator speaks the words in {language}, "
    "so describe a narrator's voice that suits the story.",
}


def _schema(count: int) -> dict:
    text = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "cast": {**text, "description": "Every recurring person, precisely, once."},
            "setting": {**text, "description": "The places, the route, the period and light."},
            "narrator": {**text, "description": "The narrator's voice: age, warmth, pace."},
            "shots": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {**text, "description": "What happens, as one action."},
                        "camera": {**text, "description": "One camera move."},
                        "sound": {**text, "description": "The natural sounds of the shot."},
                    },
                    "required": ["action", "camera", "sound"],
                },
            },
        },
        "required": ["cast", "setting", "narrator", "shots"],
    }


def screenwriter_prompt(request: ScriptRequest) -> str:
    shots = "\n".join(
        f'Shot {i + 1} ({shot.seconds:.1f} s): "{shot.words}"'
        for i, shot in enumerate(request.shots)
    )
    language = LANGUAGES.get(request.spoken_language, request.spoken_language)
    return SCREENWRITER.format(
        title=request.title,
        place=request.place or "Jordan",
        story=request.story,
        shots=shots,
        direction=request.direction,
        audio_note=AUDIO_NOTES.get(request.audio, AUDIO_NOTES["soundtrack"]).format(
            language=language
        ),
        count=len(request.shots),
    )


def _reported_cost(data: dict) -> None:
    """Record Google's own token count when the answer carries one."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return

    def tokens(*names: str) -> int:
        return sum(int(usage[n]) for n in names if isinstance(usage.get(n), int | float))

    settings = get_settings()
    taken = tokens("input_tokens", "total_input_tokens", "prompt_tokens")
    given = tokens("output_tokens", "total_output_tokens", "candidates_tokens") + tokens(
        "thought_tokens", "total_thought_tokens", "thoughts_tokens"
    )
    if taken or given:
        gateway.report_cost(
            (
                Decimal(taken) * Decimal(str(settings.gemini_script_input_usd_per_million))
                + Decimal(given) * Decimal(str(settings.gemini_script_output_usd_per_million))
            )
            / Decimal(1_000_000)
        )


class GeminiScriptWriter:
    name = "gemini_script"
    budget = "card"

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        """Units are characters of the request: about three a token, plus the photo; the
        answer and the model's thinking are allowed for generously."""
        settings = get_settings()
        taken = Decimal(units // 3 + 1300)
        given = Decimal(6000)
        return (
            taken * Decimal(str(settings.gemini_script_input_usd_per_million))
            + given * Decimal(str(settings.gemini_script_output_usd_per_million))
        ) / Decimal(1_000_000)

    async def refine(self, request: ScriptRequest) -> Screenplay:
        headers = gemini.key_headers()
        inputs: list[dict] = []
        if request.photo:
            inputs.append(
                {
                    "type": "image",
                    "data": base64.b64encode(request.photo).decode(),
                    "mime_type": "image/webp",
                }
            )
        inputs.append({"type": "text", "text": screenwriter_prompt(request)})
        body = {
            "model": get_settings().gemini_script_model,
            "input": inputs,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": _schema(len(request.shots)),
            },
            # The story is not kept at Google once the script is written.
            "store": False,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(gemini.INTERACTIONS_URL, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("The Gemini screenwriter could not be reached.") from exc
        gemini.raise_refusal(response, "The Gemini screenwriter", paid_tier_only=False)
        if response.status_code >= 400:
            raise ProviderUnavailable("The Gemini screenwriter is unavailable right now.")
        try:
            data = response.json()
            _reported_cost(data)
            text = next(
                (
                    part["text"]
                    for step in data["steps"]
                    if step.get("type") == "model_output"
                    for part in step.get("content", [])
                    if part.get("type") == "text"
                ),
                None,
            )
            script = json.loads(text) if text else None
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise UserFacingError("The screenwriter gave an unexpected answer; try again.") from exc
        if not isinstance(script, dict):
            raise UserFacingError("The screenwriter gave an unexpected answer; try again.")
        screenplay = Screenplay.from_dict(script)
        if len(screenplay.scenes) != len(request.shots):
            raise UserFacingError(
                "The screenwriter wrote a different number of shots than planned; try again."
            )
        return screenplay


def script_writer() -> ScriptWriter:
    name = get_settings().script_provider
    if name == "fake":
        return FakeScriptWriter()
    if name == "gemini":
        return GeminiScriptWriter()
    raise UserFacingError("The screenwriter is not connected.")
