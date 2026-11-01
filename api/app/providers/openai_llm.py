"""Direct OpenAI language model, using Hikaya's existing aligned-line contract.

Calls are made only by the worker through the shared cache and card spending ledger.
"""

import json
from decimal import Decimal

import httpx

from app import gateway
from app.config import get_settings
from app.errors import UserFacingError
from app.providers import ProviderUnavailable
from app.providers.azure_llm import AzureLanguageModel

MAX_INPUT_BYTES = 64_000
# Covers the serialized request text, instructions and message framing.
INPUT_TOKEN_BOUND = 68_000


class OpenAILanguageModel(AzureLanguageModel):
    """Reuse the strict segment/moderation validation, with direct OpenAI transport."""

    budget = "card"

    def __init__(self) -> None:
        s = get_settings()
        if not s.openai_api_key.strip():
            raise ProviderUnavailable("The OpenAI language model needs OPENAI_API_KEY.")
        if s.openai_input_usd_per_million <= 0 or s.openai_output_usd_per_million <= 0:
            raise ProviderUnavailable("Configure positive OpenAI token prices before live calls.")
        self.key = s.openai_api_key
        self.deployment = s.openai_model
        # Keep cached outputs separate when the model or output limit changes.
        self.name = f"openai:{s.openai_model}:{s.openai_max_output_tokens}"
        self.max_output = s.openai_max_output_tokens
        self.input_price = Decimal(str(s.openai_input_usd_per_million))
        self.output_price = Decimal(str(s.openai_output_usd_per_million))

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        # A fixed conservative bound avoids under-reserving Arabic/JSON token overhead.
        return self._cost(INPUT_TOKEN_BOUND, self.max_output)

    async def moderate(self, texts: list[str]) -> dict[str, dict]:
        labels = await super().moderate(texts)
        # Existing Azure contract coerces reasons; enforce the raw schema in _ask too.
        return labels

    async def _ask(self, prompt: str, payload: dict, schema_name: str, schema: dict) -> dict:
        serialized = json.dumps(payload, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > MAX_INPUT_BYTES or len(prompt.encode()) > 3000:
            raise UserFacingError("This text is too long for one language-model request.")
        body = {
            "model": self.deployment,
            "store": False,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": serialized},
            ],
            "max_completion_tokens": self.max_output,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        estimate = self.estimate_usd(schema_name, 0)
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.key}"},
                    json=body,
                )
        except httpx.HTTPError as exc:
            # A timed-out request can still be billed: retain its reservation.
            gateway.report_cost(estimate)
            raise ProviderUnavailable("The OpenAI language model could not be reached.") from exc
        if response.status_code >= 300:
            if response.status_code >= 500:
                gateway.report_cost(estimate)
            if response.status_code in (401, 403):
                message = "OpenAI rejected the key or permissions; check OPENAI_API_KEY."
            elif response.status_code == 404:
                message = "OpenAI could not find the configured model; check OPENAI_MODEL."
            elif response.status_code == 429:
                message = "OpenAI is busy or account credit is unavailable; try later."
            else:
                message = "The OpenAI request failed; check the model configuration."
            raise ProviderUnavailable(message)
        reported = False
        try:
            data = response.json()
            usage = data["usage"]
            counts = [usage["prompt_tokens"], usage["completion_tokens"]]
            if any(type(n) is not int or n < 0 for n in counts):
                raise ValueError("Invalid usage")
            gateway.report_cost(self._cost(*counts))
            reported = True
            choice = data["choices"][0]
            message = choice["message"]
            if choice.get("finish_reason") != "stop" or message.get("refusal"):
                raise ValueError("Incomplete or refused output")
            answer = json.loads(message["content"])
            if not isinstance(answer, dict):
                raise ValueError("Invalid output")
            if schema_name == "moderation":
                labels = answer.get("labels")
                if not isinstance(labels, dict) or any(
                    not isinstance(v, dict) or not isinstance(v.get("reason"), str)
                    for v in labels.values()
                ):
                    raise ValueError("Invalid moderation reasons")
            return answer
        except (KeyError, ValueError, IndexError, TypeError) as exc:
            if not reported:
                gateway.report_cost(estimate)
            raise UserFacingError("OpenAI returned an incomplete or unexpected answer.") from exc
