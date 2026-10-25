from datetime import UTC, datetime

import pytest

from app.config import get_settings
from app.models import Role, Story
from app.seed_staff import StaffSeed, seed_staff
from app.worker import run_one

PASSWORD = "video-test-password"


async def admin(client, sessionmaker):
    await seed_staff(
        sessionmaker, [StaffSeed("video@example.com", PASSWORD, Role.ADMIN, "Video staff")]
    )
    return (
        await client.post(
            "/api/v1/auth/login", json={"email": "video@example.com", "password": PASSWORD}
        )
    ).json()


async def test_video_console_rejects_nonstaff(client):
    assert (await client.get("/api/v1/staff/videos/config")).status_code == 401
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "member@example.com", "password": PASSWORD, "display_name": "Member"},
    )
    assert (await client.get("/api/v1/staff/videos/config")).status_code == 403


async def test_staff_can_queue_a_demo_preview_and_read_progress(
    client, session, sessionmaker, monkeypatch
):
    monkeypatch.setattr(get_settings(), "enable_ai_video", True)
    monkeypatch.setattr(get_settings(), "video_provider", "fake")
    user = await admin(client, sessionmaker)
    import uuid

    story = Story(
        author_id=uuid.UUID(user["id"]),
        title="A heritage story",
        place_name="Madaba",
        status="published",
        published_at=datetime.now(UTC),
    )
    session.add(story)
    await session.commit()
    payload = {
        "story_id": str(story.id),
        "provider": "fake",
        "model": "demo",
        "prompt": "Slow camera movement",
        "aspect_ratio": "16:9",
        "seed": 42,
    }
    response = await client.post("/api/v1/staff/videos", json=payload)
    assert response.status_code == 202, response.text
    generation = response.json()
    assert generation["status"] == "queued"
    assert "Madaba" in generation["prompt"]
    repeated = (await client.post("/api/v1/staff/videos", json=payload)).json()
    assert repeated["id"] == generation["id"]
    assert await run_one(sessionmaker)
    completed = (await client.get(f"/api/v1/staff/videos/{generation['id']}")).json()
    assert completed["status"] == "done"
    assert completed["demo"] is True
    assert (await client.get(completed["video_url"])).status_code == 200
    await client.post("/api/v1/auth/logout")
    assert (await client.get(completed["video_url"])).status_code == 401


async def test_generation_flag_and_provider_configuration_are_enforced(
    client, sessionmaker, monkeypatch
):
    await admin(client, sessionmaker)
    monkeypatch.setattr(get_settings(), "enable_ai_video", False)
    response = await client.post(
        "/api/v1/staff/videos",
        json={
            "story_id": "00000000-0000-0000-0000-000000000001",
            "provider": "fake",
            "model": "demo",
        },
    )
    assert response.status_code == 503
    config = (await client.get("/api/v1/staff/videos/config")).json()
    assert config["enabled"] is False
    assert not next(provider for provider in config["providers"] if provider["id"] == "fal")[
        "available"
    ]


async def test_fal_adapter_submits_and_polls_the_documented_queue(monkeypatch):
    import httpx

    from app.providers.video import FAL_MODEL, FalVideo

    monkeypatch.setattr(get_settings(), "fal_key", "test-only-key")
    requests = []

    def respond(request):
        import json

        requests.append(request)
        assert request.headers["Authorization"] == "Key test-only-key"
        if request.method == "POST":
            arguments = json.loads(request.content)
            assert arguments["image_url"].startswith("data:image/webp;base64,")
            assert arguments["enable_safety_checker"] is True
            return httpx.Response(
                200,
                json={
                    "request_id": "req",
                    "status_url": "https://queue.fal.run/fal-ai/wan/requests/req/status",
                    "response_url": "https://queue.fal.run/fal-ai/wan/requests/req",
                },
            )
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        return httpx.Response(200, json={"video": {"url": "https://v3.fal.media/video.mp4"}})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    adapter = FalVideo()
    request = await adapter.submit(
        {
            "model": FAL_MODEL,
            "image_url": "data:image/webp;base64,AAAA",
            "prompt": "Heritage",
            "aspect_ratio": "16:9",
            "seed": 42,
        }
    )
    result = await adapter.poll(request)
    assert result == {"status": "done", "video_url": "https://v3.fal.media/video.mp4"}
    assert len(requests) == 3


async def test_uncertain_paid_submission_keeps_its_reservation_counted(session):
    from decimal import Decimal

    from sqlalchemy import select

    from app import gateway
    from app.config import get_settings
    from app.models import SpendEntry

    settings = get_settings()
    old = settings.live_ai_enabled
    settings.live_ai_enabled = True

    class Paid:
        name = "fal-test"
        budget = "card"

        def estimate_usd(self, operation, units):
            return Decimal("1.00")

    async def uncertain():
        raise TimeoutError("uncertain")

    try:
        with pytest.raises(TimeoutError):
            await gateway.call(
                "video_submit", Paid(), ("test-uncertain",), 6, uncertain, charge_on_failure=True
            )
        entry = (
            await session.execute(select(SpendEntry).where(SpendEntry.provider == "fal-test"))
        ).scalar_one()
        assert entry.state == "committed"
        assert entry.actual_usd == Decimal("1.00")
    finally:
        settings.live_ai_enabled = old
