"""Higgsfield, supported Google Veo GA, and a self-hosted Cog HTTP server."""

import base64
from decimal import Decimal
from urllib.parse import quote, urlparse

import httpx

from app.config import get_settings
from app.errors import UserFacingError
from app.providers.video import download_video, https_host

HIGGSFIELD_MODEL = "bytedance/seedance-2.5/image-to-video"
VEO_MODEL = "veo-3.1-fast-generate-001"
VEO_MODELS = [VEO_MODEL, "veo-3.1-generate-001"]


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
        return Decimal(str(get_settings().video_estimate_usd))

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
            raise UserFacingError(
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
        return Decimal(str(get_settings().video_estimate_usd))

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
            raise UserFacingError(
                "Google could not generate this video. It may have been filtered."
            )
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
