"""Durable video provider requests. Credentials and provider traffic stay server-side."""

from decimal import Decimal
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.errors import UserFacingError

FAL_MODEL = "fal-ai/wan/v2.2-a14b/image-to-video"


class VideoProvider(Protocol):
    name: str
    budget: str | None

    def estimate_usd(self, operation: str, units: int) -> Decimal: ...
    async def submit(self, payload: dict) -> dict: ...
    async def poll(self, request: dict) -> dict: ...
    async def download(self, url: str) -> bytes: ...


def https_host(url: str, hosts: tuple[str, ...]) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        raise UserFacingError("The provider returned an invalid result URL.")
    if not any(parsed.hostname == host or parsed.hostname.endswith("." + host) for host in hosts):
        raise UserFacingError("The provider returned an unexpected result host.")
    return url


async def download_video(url: str, hosts: tuple[str, ...], headers: dict | None = None) -> bytes:
    url = https_host(url, hosts)
    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
        async with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 100 * 1024 * 1024:
                    raise UserFacingError("The generated video is too large to download.")
    if not data:
        raise UserFacingError("The provider returned an empty video.")
    return bytes(data)


class FakeVideo:
    name = "fake"
    budget = None

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return Decimal(0)

    async def submit(self, payload: dict) -> dict:
        return {"request_id": "demo"}

    async def poll(self, request: dict) -> dict:
        return {"status": "done", "video_url": "demo"}

    async def download(self, url: str) -> bytes:
        return (Path(__file__).resolve().parents[2] / "seed/videos/wan-light.webm").read_bytes()


class FalVideo:
    name = "fal"
    budget = "card"

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return Decimal(str(get_settings().video_estimate_usd))

    @property
    def headers(self) -> dict:
        if not get_settings().fal_key:
            raise UserFacingError("The fal.ai key is not configured.")
        return {"Authorization": f"Key {get_settings().fal_key}"}

    async def submit(self, payload: dict) -> dict:
        arguments = {
            "image_url": payload["image_url"],
            "prompt": payload["prompt"],
            "aspect_ratio": payload["aspect_ratio"],
            "seed": payload["seed"],
            "resolution": "480p",
            "num_frames": 81,
            "frames_per_second": 16,
            "enable_safety_checker": True,
            "enable_output_safety_checker": True,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"https://queue.fal.run/{payload['model']}", headers=self.headers, json=arguments
            )
            response.raise_for_status()
            data = response.json()
        return {
            "request_id": data["request_id"],
            "status_url": https_host(data["status_url"], ("queue.fal.run",)),
            "response_url": https_host(data["response_url"], ("queue.fal.run",)),
        }

    async def poll(self, request: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            status = await client.get(
                https_host(request["status_url"], ("queue.fal.run",)), headers=self.headers
            )
            status.raise_for_status()
            data = status.json()
            if data.get("status") != "COMPLETED":
                if data.get("status") not in {"IN_QUEUE", "IN_PROGRESS"}:
                    raise UserFacingError("The video provider returned an unknown job status.")
                return {"status": "queued" if data["status"] == "IN_QUEUE" else "running"}
            if data.get("error"):
                raise UserFacingError("The video provider could not generate this prompt.")
            result = await client.get(
                https_host(request["response_url"], ("queue.fal.run",)), headers=self.headers
            )
            result.raise_for_status()
            url = result.json()["video"]["url"]
            return {"status": "done", "video_url": https_host(url, ("fal.media",))}

    async def download(self, url: str) -> bytes:
        return await download_video(url, ("fal.media",))


class FreeVideoRead:
    """Status and result retrieval never submit inference or reserve another payment."""

    budget = None

    def __init__(self, name: str):
        self.name = name


def provider(name: str) -> VideoProvider:
    if name == "fake":
        return FakeVideo()
    if name == "fal":
        return FalVideo()
    from app.providers.video_alternatives import CogVideo, GoogleVeo, HiggsfieldVideo

    if name == "higgsfield":
        return HiggsfieldVideo()
    if name == "gemini":
        return GoogleVeo()
    if name == "custom":
        return CogVideo()
    raise UserFacingError("This video provider is not connected.")


def configurations() -> list[dict]:
    from app.providers.video_alternatives import HIGGSFIELD_MODEL, VEO_MODELS

    settings = get_settings()
    custom = urlparse(settings.custom_video_endpoint)
    return [
        {
            "id": "fake",
            "label": "Offline demo",
            "models": ["demo"],
            "available": True,
            "reason": "",
        },
        {
            "id": "fal",
            "label": "fal.ai",
            "models": [FAL_MODEL],
            "available": bool(settings.fal_key and settings.live_ai_enabled),
            "reason": "Set FAL_KEY and LIVE_AI_ENABLED to use fal.ai.",
        },
        {
            "id": "higgsfield",
            "label": "Higgsfield",
            "models": [HIGGSFIELD_MODEL],
            "available": bool(
                settings.higgsfield_key_id
                and settings.higgsfield_key_secret
                and settings.live_ai_enabled
            ),
            "supports_seed": False,
            "supports_aspect": False,
            "reason": (
                "Set Higgsfield credentials and LIVE_AI_ENABLED. "
                "Framing follows the input photo; seed is unsupported."
            ),
        },
        {
            "id": "gemini",
            "label": "Google Veo (GA)",
            "models": VEO_MODELS,
            "available": bool(
                settings.google_cloud_project
                and settings.google_access_token
                and settings.live_ai_enabled
            ),
            "reason": (
                "Set GOOGLE_CLOUD_PROJECT, GOOGLE_ACCESS_TOKEN and LIVE_AI_ENABLED. "
                "Gemini API Veo previews are retired."
            ),
        },
        {
            "id": "custom",
            "label": "Self-hosted Cog",
            "models": ["cog"],
            "available": bool(
                custom.scheme in {"http", "https"}
                and custom.hostname
                and not custom.username
                and not custom.password
                and not custom.query
                and not custom.fragment
                and settings.live_ai_enabled
            ),
            "reason": (
                "Set CUSTOM_VIDEO_ENDPOINT and LIVE_AI_ENABLED for a compatible Cog predictor."
            ),
        },
    ]
