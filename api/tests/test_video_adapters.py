import base64
import json

import httpx
import pytest

from app.config import get_settings
from app.providers.video import configurations, provider


@pytest.mark.parametrize("name", ["higgsfield", "gemini", "custom"])
async def test_alternative_providers_report_missing_configuration(name):
    config = next(item for item in configurations() if item["id"] == name)
    assert config["available"] is False
    assert config["reason"]


async def test_higgsfield_uploads_media_without_sending_credentials_to_storage(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "higgsfield_key_id", "test-id")
    monkeypatch.setattr(settings, "higgsfield_key_secret", "test-secret")

    def respond(request):
        if request.url.path == "/files/generate-upload-url":
            assert request.headers["Authorization"] == "Key test-id:test-secret"
            return httpx.Response(
                200,
                json={
                    "upload_url": "https://storage.googleapis.com/input.webp",
                    "public_url": "https://storage.googleapis.com/public.webp",
                    "upload_headers": {"Content-Type": "image/webp"},
                },
            )
        if request.method == "PUT":
            assert "Authorization" not in request.headers
            assert request.content == b"image"
            return httpx.Response(200)
        if request.method == "POST":
            data = json.loads(request.content)
            assert data["image_url"] == "https://storage.googleapis.com/public.webp"
            assert request.headers["Idempotency-Key"] == "request-1"
            assert "seed" not in data
            return httpx.Response(
                200,
                json={
                    "request_id": "hf",
                    "status_url": "https://api.higgsfield.ai/requests/hf/status",
                },
            )
        return httpx.Response(
            200,
            json={"status": "completed", "video": {"url": "https://cdn.higgsfield.ai/output.mp4"}},
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    adapter = provider("higgsfield")
    handle = await adapter.submit(
        {
            "model": "bytedance/seedance-2.5/image-to-video",
            "prompt": "Heritage",
            "image_url": "data:image/webp;base64,aW1hZ2U=",
            "request_id": "request-1",
            "aspect_ratio": "16:9",
            "seed": 42,
        }
    )
    assert (await adapter.poll(handle))["video_url"] == "https://cdn.higgsfield.ai/output.mp4"


async def test_google_veo_uses_ga_long_running_operations(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "google_cloud_project", "test-project")
    monkeypatch.setattr(settings, "google_access_token", "test-token")

    def respond(request):
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.url.path.endswith(":predictLongRunning"):
            data = json.loads(request.content)
            assert data["parameters"]["sampleCount"] == 1
            assert data["instances"][0]["image"]["mimeType"] == "image/webp"
            return httpx.Response(
                200,
                json={
                    "name": (
                        "projects/test-project/locations/us-central1/publishers/google/"
                        "models/veo-3.1-fast-generate-001/operations/job"
                    )
                },
            )
        assert request.url.path.endswith(":fetchPredictOperation")
        return httpx.Response(
            200,
            json={
                "done": True,
                "response": {
                    "videos": [
                        {
                            "bytesBase64Encoded": base64.b64encode(b"video").decode(),
                            "mimeType": "video/mp4",
                        }
                    ]
                },
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    adapter = provider("gemini")
    handle = await adapter.submit(
        {
            "model": "veo-3.1-fast-generate-001",
            "prompt": "Heritage",
            "image_url": "data:image/webp;base64,aW1hZ2U=",
            "aspect_ratio": "16:9",
            "seed": 42,
        }
    )
    result = await adapter.poll(handle)
    assert await adapter.download(result["video_url"]) == b"video"


async def test_self_hosted_cog_uses_idempotent_synchronous_predictions(monkeypatch):
    monkeypatch.setattr(get_settings(), "custom_video_endpoint", "http://127.0.0.1:5000")

    def respond(request):
        assert request.method == "PUT"
        assert request.url.path == "/predictions/request1"
        assert "Prefer" not in request.headers
        assert json.loads(request.content)["input"]["image"].startswith("data:image/")
        return httpx.Response(
            200, json={"status": "succeeded", "output": "data:video/mp4;base64,dmlkZW8="}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    adapter = provider("custom")
    handle = await adapter.submit(
        {
            "request_id": "request1",
            "model": "cog",
            "prompt": "Heritage",
            "image_url": "data:image/webp;base64,aW1hZ2U=",
            "aspect_ratio": "16:9",
            "seed": 42,
        }
    )
    assert await adapter.download((await adapter.poll(handle))["video_url"]) == b"video"
