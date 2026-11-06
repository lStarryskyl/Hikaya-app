"""Higgsfield, supported Google Veo GA, Gemini Omni Flash (Gemini API) and a self-hosted Cog
HTTP server."""

import base64
import re
from decimal import Decimal
from urllib.parse import quote, urlparse

import httpx

from app.config import get_settings
from app.errors import NotStarted, UserFacingError
from app.providers.video import VideoRejected, download_video, https_host, video_cost

HIGGSFIELD_MODEL = "bytedance/seedance-2.5/image-to-video"
VEO_MODEL = "veo-3.1-fast-generate-001"
VEO_MODELS = [VEO_MODEL, "veo-3.1-generate-001"]
OMNI_MODEL = "gemini-omni-1.2-flash"
OMNI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
# Interaction IDs look like "v1_..."; anything else is refused before it goes in a URL.
OMNI_INTERACTION_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


def decode_data_url(url: str, media: str) -> bytes:
    prefix, separator, encoded = url.partition(",")
    if not separator or not prefix.startswith(f"data:{media}") or not prefix.endswith(";base64"):
        raise UserFacingError("The provider returned an unsupported inline file.")
    if len(encoded) > 140 * 1024 * 1024:
        raise UserFacingError("The generated file is too large.")
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > 100 * 1024 * 1024:
            raise UserFacingError("The generated file is too large.")
        return data
    except ValueError as exc:
        raise UserFacingError("The provider returned an invalid inline file.") from exc


class HiggsfieldVideo:
    name = "higgsfield"
    budget = "card"

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return video_cost(units)

    @property
    def headers(self) -> dict:
        settings = get_settings()
        if not settings.higgsfield_key_id or not settings.higgsfield_key_secret:
            raise UserFacingError("Higgsfield credentials are not configured.")
        return {
            "Authorization": f"Key {settings.higgsfield_key_id}:{settings.higgsfield_key_secret}"
        }

    async def submit(self, payload: dict) -> dict:
        hosts = tuple(get_settings().higgsfield_media_hosts)
        image = decode_data_url(payload["image_url"], "image/webp")
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            upload = await client.post(
                "https://api.higgsfield.ai/files/generate-upload-url",
                headers=self.headers,
                json={"content_type": "image/webp"},
            )
            upload.raise_for_status()
            info = upload.json()
            upload_url = https_host(info["upload_url"], hosts)
            # Upload headers belong to storage. Never forward the Higgsfield API key.
            headers = {
                key: value
                for key, value in info.get("upload_headers", {}).items()
                if key.lower() == "content-type" or key.lower().startswith("x-amz-")
            }
            headers.setdefault("Content-Type", "image/webp")
            sent = await client.put(upload_url, headers=headers, content=image)
            sent.raise_for_status()
            response = await client.post(
                f"https://api.higgsfield.ai/{payload['model']}",
                headers={**self.headers, "Idempotency-Key": payload["request_id"]},
                json={
                    "image_url": https_host(info["public_url"], hosts),
                    "prompt": payload["prompt"],
                    "duration": 6,
                    "resolution": "480p",
                    "generate_audio": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            return {
                "request_id": data["request_id"],
                "status_url": https_host(data["status_url"], ("api.higgsfield.ai",)),
            }

    async def poll(self, request: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                https_host(request["status_url"], ("api.higgsfield.ai",)), headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
        if data.get("status") == "completed":
            return {
                "status": "done",
                "video_url": https_host(
                    data["video"]["url"], tuple(get_settings().higgsfield_media_hosts)
                ),
            }
        if data.get("status") in {"failed", "nsfw", "canceled"}:
            raise VideoRejected(
                "Higgsfield could not complete this video. Check the prompt and input photo."
            )
        if data.get("status") not in {"queued", "in_progress"}:
            raise UserFacingError("Higgsfield returned an unknown job status.")
        return {"status": "queued" if data["status"] == "queued" else "running"}

    async def download(self, url: str) -> bytes:
        return await download_video(url, tuple(get_settings().higgsfield_media_hosts))


class GoogleVeo:
    """Veo GA on Google Cloud. Retired Gemini API preview endpoints are never used."""

    name = "gemini"
    budget = "card"

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return video_cost(units)

    @property
    def headers(self) -> dict:
        if not get_settings().google_access_token:
            raise UserFacingError("The Google Cloud access token is not configured or has expired.")
        return {"Authorization": f"Bearer {get_settings().google_access_token}"}

    def model_url(self, model: str) -> str:
        settings = get_settings()
        if model not in VEO_MODELS or not settings.google_cloud_project:
            raise UserFacingError("Choose a configured Google Veo GA model.")
        return f"https://{settings.google_cloud_location}-aiplatform.googleapis.com/v1/projects/{settings.google_cloud_project}/locations/{settings.google_cloud_location}/publishers/google/models/{model}"

    async def submit(self, payload: dict) -> dict:
        image = decode_data_url(payload["image_url"], "image/webp")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.model_url(payload["model"]) + ":predictLongRunning",
                headers=self.headers,
                json={
                    "instances": [
                        {
                            "prompt": payload["prompt"],
                            "image": {
                                "bytesBase64Encoded": base64.b64encode(image).decode(),
                                "mimeType": "image/webp",
                            },
                        }
                    ],
                    "parameters": {
                        "sampleCount": 1,
                        "durationSeconds": 6,
                        "aspectRatio": payload["aspect_ratio"],
                        "seed": payload["seed"],
                        "resolution": "720p",
                        "generateAudio": False,
                    },
                },
            )
            response.raise_for_status()
            name = response.json()["name"]
        settings = get_settings()
        prefix = (
            f"projects/{settings.google_cloud_project}/"
            f"locations/{settings.google_cloud_location}/publishers/google/"
            f"models/{payload['model']}/operations/"
        )
        if not isinstance(name, str) or not name.startswith(prefix):
            raise UserFacingError("Google returned an unexpected operation name.")
        return {"operation": name, "model": payload["model"]}

    async def poll(self, request: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.model_url(request["model"]) + ":fetchPredictOperation",
                headers=self.headers,
                json={"operationName": request["operation"]},
            )
            response.raise_for_status()
            data = response.json()
        if not data.get("done"):
            return {"status": "running"}
        if data.get("error") or not data.get("response", {}).get("videos"):
            raise VideoRejected("Google could not generate this video. It may have been filtered.")
        video = data["response"]["videos"][0]
        if video.get("bytesBase64Encoded"):
            return {
                "status": "done",
                "video_url": "data:video/mp4;base64," + video["bytesBase64Encoded"],
            }
        uri = video.get("gcsUri", "")
        if not uri.startswith("gs://"):
            raise UserFacingError("Google returned no downloadable video.")
        bucket, _, key = uri[5:].partition("/")
        return {
            "status": "done",
            "video_url": (
                f"https://storage.googleapis.com/{quote(bucket, safe='')}/{quote(key, safe='/')}"
            ),
        }

    async def download(self, url: str) -> bytes:
        if url.startswith("data:"):
            return decode_data_url(url, "video/mp4")
        return await download_video(url, ("storage.googleapis.com",), self.headers)


class GeminiOmniVideo:
    """Gemini Omni Flash through the Gemini API's Interactions API, with a Google AI Studio key.

    Submitting creates a background interaction and returns its ID at once; each check reads
    the interaction once, and a finished one carries the video as base64 MP4 in its
    `model_output` step. The key goes in the `x-goog-api-key` header, never in a URL.
    Contract: https://ai.google.dev/gemini-api/docs/omni and
    https://ai.google.dev/gemini-api/docs/background-execution (checked 2026-11-06).
    """

    name = "gemini_omni"
    budget = "card"
    # Shot lengths Omni makes, in seconds (a single clip is 6).
    shot_seconds = (3, 15)

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        """Units are seconds of video; Omni has its own price per second."""
        return Decimal(str(get_settings().gemini_omni_usd_per_second)) * Decimal(units)

    @property
    def headers(self) -> dict:
        key = get_settings().gemini_api_key
        if not key:
            raise NotStarted("The Gemini API key is not configured: set GEMINI_API_KEY.")
        return {"x-goog-api-key": key}

    async def submit(self, payload: dict) -> dict:
        headers = self.headers
        # A single clip is 6 s; a narrated video's shots ask for their own length.
        seconds = payload.get("seconds", 6)
        shortest, longest = self.shot_seconds
        if type(seconds) is not int or not shortest <= seconds <= longest:
            raise NotStarted(f"Gemini Omni makes shots of {shortest} to {longest} seconds.")
        # The opening frame, then (for a later shot of a narrated video) a reference frame of
        # the people; Omni has no field for image roles, so the prompt says which is which.
        images = [payload["image_url"]] + (
            [payload["reference_url"]] if payload.get("reference_url") else []
        )
        body = {
            "model": payload["model"],
            "input": [
                *(
                    {
                        "type": "image",
                        "data": base64.b64encode(decode_data_url(url, "image/webp")).decode(),
                        "mime_type": "image/webp",
                    }
                    for url in images
                ),
                {"type": "text", "text": payload["prompt"]},
            ],
            "response_format": {
                "type": "video",
                "aspect_ratio": payload["aspect_ratio"],
                "resolution": "720p",
                "duration": f"{seconds}s",
            },
            "background": True,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(OMNI_URL, headers=headers, json=body)
        _omni_refusal(response)
        # A server error may still have started a billed render: left uncertain, not retried.
        response.raise_for_status()
        interaction = response.json().get("id")
        if not isinstance(interaction, str) or not OMNI_INTERACTION_ID.match(interaction):
            raise UserFacingError("Google returned an unexpected interaction ID.")
        return {"interaction": interaction}

    async def poll(self, request: dict) -> dict:
        # The finished interaction carries the whole video inline, so allow time to read it.
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(
                f"{OMNI_URL}/{quote(request['interaction'], safe='')}", headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("unexpected interaction")  # checked again next time
        status = data.get("status")
        if status == "in_progress":
            return {"status": "running"}
        if status in {"failed", "cancelled"}:
            raise VideoRejected(
                "Gemini Omni could not generate this video. "
                "Its safety filters may have blocked the prompt or the photo."
            )
        if status != "completed":
            raise UserFacingError("Gemini Omni returned an unknown status.")
        for step in data.get("steps") or []:
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            for part in step.get("content") or []:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "video"
                    and part.get("mime_type") == "video/mp4"
                    and isinstance(part.get("data"), str)
                    and part["data"]
                ):
                    return {"status": "done", "video_url": "data:video/mp4;base64," + part["data"]}
        raise VideoRejected("Gemini Omni finished without a video. It may have been filtered.")

    async def download(self, url: str) -> bytes:
        # Checks return the video inline (Google: GET on an interaction returns base64 data).
        return decode_data_url(url, "video/mp4")


def _google_error_reasons(response: httpx.Response) -> set[str]:
    """The `reason` codes in a Google error body, which the Interactions API sends either as
    {"error": ...} or wrapped in a list."""
    try:
        body = response.json()
    except ValueError:
        return set()
    errors = body if isinstance(body, list) else [body]
    reasons = set()
    for item in errors:
        error = item.get("error") if isinstance(item, dict) else None
        details = error.get("details") if isinstance(error, dict) else None
        for detail in details if isinstance(details, list) else []:
            if isinstance(detail, dict) and isinstance(detail.get("reason"), str):
                reasons.add(detail["reason"])
    return reasons


def _omni_refusal(response: httpx.Response) -> None:
    """A plain message for answers that mean Google refused the submission outright: nothing
    was started, so nothing was billed."""
    status = response.status_code
    # Google answers a wrong key with 400 API_KEY_INVALID, not 401.
    if status in (401, 403) or (
        status == 400 and "API_KEY_INVALID" in _google_error_reasons(response)
    ):
        raise NotStarted(
            "Google rejected the Gemini API key; check GEMINI_API_KEY "
            "(Omni Flash needs a key on a paid-tier project)."
        )
    if status == 429:
        raise NotStarted(
            "Google refused the request for quota: Omni Flash needs a Gemini API key on the "
            "paid tier, or the project's quota is used up."
        )
    if status in (400, 404):
        raise NotStarted(
            "Gemini Omni refused this request. The prompt or photo may be blocked, "
            "or the model is not available to this key."
        )


class CogVideo:
    """A synchronous idempotent Cog prediction runs in the background worker, not HTTP."""

    name = "custom"

    @property
    def budget(self) -> str | None:
        return "card" if get_settings().custom_video_estimate_usd > 0 else None

    def estimate_usd(self, operation: str, units: int) -> Decimal:
        return Decimal(str(get_settings().custom_video_estimate_usd))

    @property
    def base(self) -> str:
        url = get_settings().custom_video_endpoint.rstrip("/")
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise UserFacingError("Set a valid server-side Cog endpoint URL.")
        return url

    async def submit(self, payload: dict) -> dict:
        headers = {}
        if get_settings().custom_video_token:
            headers["Authorization"] = f"Bearer {get_settings().custom_video_token}"
        async with httpx.AsyncClient(timeout=480) as client:
            result = await client.put(
                f"{self.base}/predictions/{payload['request_id']}",
                headers=headers,
                json={
                    "input": {
                        "prompt": payload["prompt"],
                        "image": payload["image_url"],
                        "aspect_ratio": payload["aspect_ratio"],
                        "seed": payload["seed"],
                    }
                },
            )
            result.raise_for_status()
            data = result.json()
        if data.get("status") != "succeeded":
            raise UserFacingError("The self-hosted video endpoint did not finish successfully.")
        output = data.get("output")
        if isinstance(output, list):
            output = output[0] if output else None
        if not isinstance(output, str):
            raise UserFacingError(
                "The self-hosted endpoint must return an MP4 data URL or file URL."
            )
        return {"video_url": output}

    async def poll(self, request: dict) -> dict:
        return {"status": "done", "video_url": request["video_url"]}

    async def download(self, url: str) -> bytes:
        if url.startswith("data:"):
            return decode_data_url(url, "video/mp4")
        # A configured local server can return its own private file URLs. Credentials are
        # never sent to a different origin, and arbitrary input URLs are not accepted.
        if (
            urlparse(url).netloc != urlparse(self.base).netloc
            or urlparse(url).scheme != urlparse(self.base).scheme
        ):
            raise UserFacingError(
                "The self-hosted result must be served by its configured endpoint."
            )
        headers = (
            {"Authorization": f"Bearer {get_settings().custom_video_token}"}
            if get_settings().custom_video_token
            else {}
        )
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 100 * 1024 * 1024:
                        raise UserFacingError("The self-hosted video is too large.")
        return bytes(data)
