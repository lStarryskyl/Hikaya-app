"""Voice cloning adapters, called only by a consent-backed worker job."""

from decimal import Decimal
from pathlib import Path

import httpx

from app.config import get_settings
from app.errors import UserFacingError


def unavailable_reason() -> str | None:
    """Why cloned voices cannot narrate with the current settings, or None when they can."""
    settings = get_settings()
    if settings.tts_provider == "azure":
        return (
            "Narration uses Azure voices, which cannot read with a cloned voice. "
            "Set TTS_PROVIDER=elevenlabs to clone voices for narration."
        )
    if settings.tts_provider == "elevenlabs" and settings.voice_clone_provider != "elevenlabs":
        return (
            "Narration uses ElevenLabs, so cloned voices must be made there too: "
            "set VOICE_CLONE_PROVIDER=elevenlabs."
        )
    return None


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

    async def delete(self, voice_id: str) -> None:
        """Delete the provider's copy of a revoked voice. Already gone counts as done."""
        if self.name == "fake":
            from app.providers import fake

            fake.CALLS.append(("delete_voice", voice_id))
            return
        key = get_settings().elevenlabs_api_key
        if not key:
            raise UserFacingError("The ElevenLabs key is not configured.")
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.delete(
                    f"https://api.elevenlabs.io/v1/voices/{voice_id}", headers={"xi-api-key": key}
                )
        except httpx.HTTPError as exc:
            raise UserFacingError("ElevenLabs could not be reached to delete the voice.") from exc
        if response.status_code == 404:
            return
        if response.status_code >= 400:
            raise UserFacingError("ElevenLabs did not confirm deleting the voice; it will retry.")
