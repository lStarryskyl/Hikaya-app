import base64
import json
from decimal import Decimal

import httpx
import pytest

from app.config import get_settings
from app.errors import UserFacingError
from app.providers.video import configurations, provider
from tests.http_mock import mock_http


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


# --- Gemini Omni Flash through the Gemini API (a Google AI Studio key) ---
# Contract: https://ai.google.dev/gemini-api/docs/omni and
# https://ai.google.dev/gemini-api/docs/background-execution (checked 2026-11-06).

OMNI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
OMNI_MODEL = "gemini-omni-1.2-flash"
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "
OMNI_PAYLOAD = {
    "model": OMNI_MODEL,
    "prompt": "Heritage story: Petra.",
    "image_url": "data:image/webp;base64," + base64.b64encode(WEBP).decode(),
    "aspect_ratio": "9:16",
    "seed": 0,
    "request_id": "abc",
}


@pytest.fixture
def omni(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "ai-studio-test-key")
    return settings


def omni_done(video: bytes) -> dict:
    """A finished interaction as the REST API returns it: the video is in the steps."""
    return {
        "id": "v1_abc",
        "status": "completed",
        "model": OMNI_MODEL,
        "object": "interaction",
        "steps": [
            {"type": "user_input", "content": [{"type": "text", "text": "..."}]},
            {"type": "thought", "content": [{"type": "thought", "text": "..."}]},
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "video",
                        "mime_type": "video/mp4",
                        "data": base64.b64encode(video).decode(),
                    }
                ],
            },
        ],
    }


def omni_config() -> dict:
    return next(item for item in configurations() if item["id"] == "gemini_omni")


def test_gemini_omni_is_offered_only_with_a_key_and_live_ai(monkeypatch):
    settings = get_settings()
    assert omni_config()["available"] is False
    assert "GEMINI_API_KEY" in omni_config()["reason"]
    monkeypatch.setattr(settings, "gemini_api_key", "ai-studio-test-key")
    assert omni_config()["available"] is False  # live AI is still off
    monkeypatch.setattr(settings, "live_ai_enabled", True)
    config = omni_config()
    assert config["available"] is True
    assert config["models"] == [OMNI_MODEL]
    assert config["supports_seed"] is False
    assert config.get("supports_aspect", True) is True


async def test_gemini_omni_without_a_key_names_the_setting():
    with pytest.raises(UserFacingError, match="GEMINI_API_KEY"):
        await provider("gemini_omni").submit(OMNI_PAYLOAD)


async def test_gemini_omni_submits_a_background_interaction(omni, monkeypatch):
    accepted = {"id": "v1_abc", "status": "in_progress"}
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=accepted))
    assert await provider("gemini_omni").submit(OMNI_PAYLOAD) == {"interaction": "v1_abc"}
    (request,) = seen
    # The key goes in the header only, never in the URL.
    assert request.method == "POST" and str(request.url) == OMNI_URL
    assert request.headers["x-goog-api-key"] == "ai-studio-test-key"
    body = json.loads(request.content)
    assert body["model"] == OMNI_MODEL
    assert body["background"] is True
    assert body["input"] == [
        {"type": "image", "data": base64.b64encode(WEBP).decode(), "mime_type": "image/webp"},
        {"type": "text", "text": "Heritage story: Petra."},
    ]
    assert body["response_format"] == {
        "type": "video",
        "aspect_ratio": "9:16",
        "resolution": "720p",
        "duration": "6s",
    }
    assert "seed" not in body  # Omni takes no seed


@pytest.mark.parametrize("interaction", ["", "../files/x", "v1 abc", None, 7])
async def test_gemini_omni_refuses_an_interaction_id_it_cannot_use(omni, monkeypatch, interaction):
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(200, json={"id": interaction, "status": "in_progress"}),
    )
    with pytest.raises(UserFacingError, match="interaction"):
        await provider("gemini_omni").submit(OMNI_PAYLOAD)


@pytest.mark.parametrize(
    ("status", "message"),
    [(400, "refused"), (401, "GEMINI_API_KEY"), (403, "GEMINI_API_KEY"), (429, "paid tier")],
)
async def test_gemini_omni_rejections_are_plain(omni, monkeypatch, status, message):
    mock_http(monkeypatch, lambda request: httpx.Response(status, json={"error": {"message": "x"}}))
    with pytest.raises(UserFacingError, match=message) as caught:
        await provider("gemini_omni").submit(OMNI_PAYLOAD)
    assert "ai-studio-test-key" not in str(caught.value)


async def test_gemini_omni_server_error_on_submit_stays_uncertain(omni, monkeypatch):
    # A 5xx may still have started a billed render: the job reports it as unconfirmed.
    mock_http(monkeypatch, lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await provider("gemini_omni").submit(OMNI_PAYLOAD)


async def test_gemini_omni_checks_once_and_returns_the_finished_video(omni, monkeypatch):
    answers = [{"id": "v1_abc", "status": "in_progress"}, omni_done(b"mp4-bytes")]
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=answers[len(seen) - 1]))
    adapter = provider("gemini_omni")
    assert await adapter.poll({"interaction": "v1_abc"}) == {"status": "running"}
    result = await adapter.poll({"interaction": "v1_abc"})
    assert result["status"] == "done"
    assert await adapter.download(result["video_url"]) == b"mp4-bytes"
    assert [(request.method, str(request.url)) for request in seen] == [
        ("GET", f"{OMNI_URL}/v1_abc")
    ] * 2
    assert all(request.headers["x-goog-api-key"] == "ai-studio-test-key" for request in seen)


@pytest.mark.parametrize(
    "answer",
    [
        {"id": "v1_abc", "status": "failed"},
        {"id": "v1_abc", "status": "cancelled"},
        {
            "id": "v1_abc",
            "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": "no"}]}],
        },
        {"id": "v1_abc", "status": "completed"},
        {"id": "v1_abc", "status": "something_new"},
    ],
)
async def test_gemini_omni_failed_or_empty_interactions_fail_plainly(omni, monkeypatch, answer):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=answer))
    with pytest.raises(UserFacingError):
        await provider("gemini_omni").poll({"interaction": "v1_abc"})


async def test_gemini_omni_check_that_cannot_reach_google_tries_again(omni, monkeypatch):
    # An HTTP error on a check is "status unavailable": the job checks again next time.
    mock_http(monkeypatch, lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await provider("gemini_omni").poll({"interaction": "v1_abc"})


async def test_gemini_omni_downloads_only_inline_video(omni):
    with pytest.raises(UserFacingError):
        await provider("gemini_omni").download("https://example.com/video.mp4")


def test_gemini_omni_has_its_own_rate(omni, monkeypatch):
    # The generic video rates do not apply: Omni's price is per second at 720p.
    monkeypatch.setattr(omni, "video_usd_per_second", 0.04)
    monkeypatch.setattr(omni, "video_estimate_usd", 1.0)
    adapter = provider("gemini_omni")
    assert adapter.budget == "card"
    assert adapter.estimate_usd("video_submit", 6) == Decimal("0.48")
    monkeypatch.setattr(omni, "gemini_omni_usd_per_second", 0.07)
    assert adapter.estimate_usd("video_submit", 6) == Decimal("0.42")


# Google's answer to a wrong key, as seen live on 2026-11-06: 400 (not 401), wrapped in a list.
OMNI_KEY_INVALID = [
    {
        "error": {
            "code": 400,
            "message": "API key not valid. Please pass a valid API key.",
            "status": "INVALID_ARGUMENT",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "API_KEY_INVALID",
                    "domain": "googleapis.com",
                }
            ],
        }
    }
]


@pytest.mark.parametrize("body", [OMNI_KEY_INVALID, OMNI_KEY_INVALID[0]])
async def test_gemini_omni_wrong_key_is_named_not_blamed_on_the_prompt(omni, monkeypatch, body):
    mock_http(monkeypatch, lambda request: httpx.Response(400, json=body))
    with pytest.raises(UserFacingError, match="GEMINI_API_KEY") as caught:
        await provider("gemini_omni").submit(OMNI_PAYLOAD)
    assert "blocked" not in str(caught.value)


@pytest.mark.parametrize(("seconds", "asked"), [(15, "15s"), (3, "3s"), (None, "6s")])
async def test_gemini_omni_asks_for_the_shot_length(omni, monkeypatch, seconds, asked):
    accepted = {"id": "v1_abc", "status": "in_progress"}
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json=accepted))
    payload = dict(OMNI_PAYLOAD) if seconds is None else {**OMNI_PAYLOAD, "seconds": seconds}
    await provider("gemini_omni").submit(payload)
    assert json.loads(seen[0].content)["response_format"]["duration"] == asked


@pytest.mark.parametrize("seconds", [2, 16, "15"])
async def test_gemini_omni_refuses_a_length_it_cannot_make(omni, monkeypatch, seconds):
    seen = mock_http(monkeypatch, lambda request: httpx.Response(500))
    with pytest.raises(UserFacingError, match="3 to 15"):
        await provider("gemini_omni").submit({**OMNI_PAYLOAD, "seconds": seconds})
    assert seen == []


async def test_gemini_omni_failure_names_googles_reason(omni, monkeypatch):
    failed = {
        "id": "v1_abc",
        "status": "failed",
        "errors": [{"code": "INVALID_ARGUMENT", "message": "There was a problem processing."}],
    }
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=failed))
    with pytest.raises(UserFacingError, match="INVALID_ARGUMENT: There was a problem") as caught:
        await provider("gemini_omni").poll({"interaction": "v1_abc"})
    assert "safety" not in str(caught.value)
