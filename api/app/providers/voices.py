"""Voice cloning adapters, called only by a consent-backed worker job."""

from decimal import Decimal
from pathlib import Path

import httpx

from app.config import get_settings
from app.errors import UserFacingError


class VoiceCloner:
    def __init__(self, name: str):
        if name not in {"fake", "elevenlabs"}:
            raise UserFacingError("The voice cloning provider is not configured.")
        self.name = name
        self.budget = None if name == "fake" else "card"

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return Decimal(str(get_settings().voice_clone_estimate_usd))

    async def clone(self, sample: Path, consent: dict) -> dict:
        if not all(
            consent.get(key) for key in ("speaker_confirmed", "rights_confirmed", "use_confirmed")
        ):
            raise UserFacingError("Voice cloning needs the speaker's consent.")
        if self.name == "fake":
            return {"voice_id": "demo-consenting-voice", "requires_verification": False}
        key = get_settings().elevenlabs_api_key
        if not key:
            raise UserFacingError("The ElevenLabs key is not configured.")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                with sample.open("rb") as audio:
                    response = await client.post(
                        "https://api.elevenlabs.io/v1/voices/add",
                        headers={"xi-api-key": key},
                        data={
                            "name": consent["speaker_name"],
                            "description": (
                                f"Hikaya consent {consent['version']} recorded {consent['at']}"
                            ),
                        },
                        files={"files": ("sample.mp3", audio, "audio/mpeg")},
                    )
                response.raise_for_status()
                result = response.json()
                if not isinstance(result.get("voice_id"), str) or not result["voice_id"]:
                    raise ValueError("missing voice id")
                return {
                    "voice_id": result["voice_id"],
                    "requires_verification": bool(result.get("requires_verification", True)),
                }
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise UserFacingError(
                "Voice cloning could not be confirmed. "
                "Check the provider before submitting another sample."
            ) from exc
