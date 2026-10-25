"""Azure OpenAI as the language model (#12): polishing, translation and moderation labels.

Every request asks for Structured Outputs (a strict JSON schema), and the lines travel as a
JSON array, so the answer has exactly one line for each line sent; anything else is refused
rather than guessed at. Translation never targets a dialect. The cost Azure reports (token
usage) is what the spending ledger records.

Uses the v1 API: POST {endpoint}/openai/v1/chat/completions with an `api-key` header and the
deployment name as `model`.
"""

import json
from decimal import Decimal

import httpx

from app import gateway
from app.config import get_settings
from app.errors import UserFacingError
from app.providers import MODERATION_LABELS, ProviderUnavailable

TIMEOUT_SECONDS = 120

# For estimates only: Arabic runs at roughly two characters per token, English at about
# four, so two keeps the reservation on the safe side. Instructions add a fixed amount, and
# reasoning models spend tokens before answering.
CHARS_PER_TOKEN = 2
INSTRUCTION_TOKENS = 400
REASONING_TOKENS = 1024
MODERATION_ANSWER_TOKENS = 300

LANGUAGE_NAMES = {
    "jordanian": "Jordanian Arabic (the spoken Jordanian dialect)",
    "msa": "Modern Standard Arabic",
    "english": "English",
}
# Translation targets are never dialect (docs/DECISIONS.md, "Languages").
TRANSLATION_TARGETS = ("english", "msa")

LINES_SCHEMA = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
    "required": ["lines"],
    "additionalProperties": False,
}
MODERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "object",
            "properties": {
                label: {
                    "type": "object",
                    "properties": {"raised": {"type": "boolean"}, "reason": {"type": "string"}},
                    "required": ["raised", "reason"],
                    "additionalProperties": False,
                }
                for label in MODERATION_LABELS
            },
            "required": list(MODERATION_LABELS),
            "additionalProperties": False,
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}

POLISH = """You lightly clean up a transcript of a spoken heritage story told in {language}.
Fix obvious transcription slips, punctuation and spacing. Keep the speaker's own words,
dialect, voice and meaning; do not translate, summarise, add or remove content.
You receive JSON {{"lines": [...]}} and answer with {{"lines": [...]}} holding exactly one
cleaned line for each line received, in the same order."""

TRANSLATE = """You translate a heritage story from {source} into {target}.
Translate faithfully and naturally; keep names of people and places; do not add commentary.
You receive JSON {{"lines": [...]}} and answer with {{"lines": [...]}} holding exactly one
translated line for each line received, in the same order."""

MODERATE = """You check a community heritage story before it is published.
For each label decide whether the text clearly contains it, with a short reason (one
sentence, in English) when raised and an empty reason when not:
- hate: attacks or demeans people for who they are.
- violence: threats, incitement or graphic violence (a historical or folk account of a
  battle or a hunt is not by itself a threat).
- sexual: sexual content.
- other_terrible: anything else clearly harmful (for example self-harm instructions,
  personal data exposure, harassment of a named private person).
Only raise a label when the text itself clearly warrants it; when in doubt, raise it so a
person reviews it. You receive JSON {{"texts": [...]}}."""


class AzureLanguageModel:
    name = "azure"
    budget = "azure"

    def __init__(self) -> None:
        settings = get_settings()
        missing = [
            env
            for env, value in (
                ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
                ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
                ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
            )
            if not value
        ]
        if missing:
            raise ProviderUnavailable(
                "The Azure language model is not configured: set " + ", ".join(missing) + "."
            )
        self.url = settings.azure_openai_endpoint.rstrip("/") + "/openai/v1/chat/completions"
        self.key = settings.azure_openai_api_key
        self.deployment = settings.azure_openai_deployment
        self.reasoning_effort = settings.azure_openai_reasoning_effort
        self.input_price = Decimal(str(settings.azure_openai_input_usd_per_million))
        self.output_price = Decimal(str(settings.azure_openai_output_usd_per_million))

    # --- cost ---

    def _cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (input_tokens * self.input_price + output_tokens * self.output_price) / Decimal(
            1_000_000
        )

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        """Units are characters of input text."""
        text_tokens = units // CHARS_PER_TOKEN + 1
        answer = MODERATION_ANSWER_TOKENS if operation == "moderate" else text_tokens * 3 // 2
        return self._cost(INSTRUCTION_TOKENS + text_tokens, answer + REASONING_TOKENS)

    # --- the three operations ---

    async def polish(self, texts: list[str], language: str) -> list[str]:
        prompt = POLISH.format(language=LANGUAGE_NAMES.get(language, language))
        return await self._lines(prompt, texts)

    async def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        if target not in TRANSLATION_TARGETS:
            raise ValueError(f"translation never targets a dialect or {target!r}")
        prompt = TRANSLATE.format(
            source=LANGUAGE_NAMES.get(source, source), target=LANGUAGE_NAMES[target]
        )
        return await self._lines(prompt, texts)

    async def moderate(self, texts: list[str]) -> dict[str, dict]:
        answer = await self._ask(MODERATE, {"texts": texts}, "moderation", MODERATION_SCHEMA)
        labels = answer.get("labels")
        if not isinstance(labels, dict) or set(labels) != set(MODERATION_LABELS):
            raise _unexpected()
        out = {}
        for label in MODERATION_LABELS:
            verdict = labels[label]
            if not isinstance(verdict, dict) or not isinstance(verdict.get("raised"), bool):
                raise _unexpected()
            out[label] = {"raised": verdict["raised"], "reason": str(verdict.get("reason", ""))}
        return out

    # --- talking to Azure ---

    async def _lines(self, prompt: str, texts: list[str]) -> list[str]:
        answer = await self._ask(prompt, {"lines": texts}, "lines", LINES_SCHEMA)
        lines = answer.get("lines")
        if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
            raise _unexpected()
        if len(lines) != len(texts):
            raise UserFacingError(
                "The language model returned a different number of lines than it was given."
            )
        return [line.strip() for line in lines]

    async def _ask(self, prompt: str, payload: dict, schema_name: str, schema: dict) -> dict:
        body: dict = {
            "model": self.deployment,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(self.url, headers={"api-key": self.key}, json=body)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("The Azure language model could not be reached.") from exc
        _raise_for_status(response)
        try:
            data = response.json()
            usage = data.get("usage") or {}
            # Count what Azure says it used, even when the answer turns out unusable.
            gateway.report_cost(
                self._cost(
                    int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
                )
            )
            choice = data["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise _unexpected() from exc
        if message.get("refusal"):
            raise UserFacingError("The language model declined this text.")
        if choice.get("finish_reason") == "length":
            raise UserFacingError("The language model's answer was cut off; try again.")
        try:
            answer = json.loads(message.get("content") or "")
        except ValueError as exc:
            raise _unexpected() from exc
        if not isinstance(answer, dict):
            raise _unexpected()
        return answer


def _unexpected() -> UserFacingError:
    return UserFacingError("The language model gave an unexpected answer; try again.")


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    if status in (401, 403):
        raise ProviderUnavailable("Azure rejected the key; check AZURE_OPENAI_API_KEY.")
    if status == 404:
        raise ProviderUnavailable(
            "Azure could not find the deployment; check AZURE_OPENAI_ENDPOINT and "
            "AZURE_OPENAI_DEPLOYMENT."
        )
    if status == 429:
        raise ProviderUnavailable("The Azure language model is busy; try again shortly.")
    if status == 400:
        raise UserFacingError("Azure refused the request (it may have been filtered).")
    raise ProviderUnavailable("The Azure language model is unavailable right now.")
