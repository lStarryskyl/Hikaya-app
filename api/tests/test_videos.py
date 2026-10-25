import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Job, Role, Story, VideoGeneration
from app.seed_staff import StaffSeed, seed_staff
from app.worker import run_one
from tests.test_moderation import drain

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
    await drain(sessionmaker)  # submit, then check until the video is ready
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


async def queue_preview(client, session, sessionmaker, monkeypatch):
    import uuid

    monkeypatch.setattr(get_settings(), "enable_ai_video", True)
    monkeypatch.setattr(get_settings(), "video_provider", "fake")
    user = await admin(client, sessionmaker)
    story = Story(
        author_id=uuid.UUID(user["id"]),
        title="A heritage story",
        place_name="Madaba",
        status="published",
        published_at=datetime.now(UTC),
    )
    session.add(story)
    await session.commit()
    response = await client.post(
        "/api/v1/staff/videos",
        json={
            "story_id": str(story.id),
            "provider": "fake",
            "model": "demo",
            "prompt": "Slow camera movement",
            "aspect_ratio": "16:9",
            "seed": 7,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def slow_render(monkeypatch, polls_until_done: int | None):
    """The fake provider says "running" this many times before the video is ready
    (None: never ready). Returns the list of poll times."""
    from app.providers.video import FakeVideo

    calls: list[datetime] = []

    async def poll(self, request):
        calls.append(datetime.now(UTC))
        if polls_until_done is None or len(calls) <= polls_until_done:
            return {"status": "running"}
        return {"status": "done", "video_url": "demo"}

    monkeypatch.setattr(FakeVideo, "poll", poll)
    return calls


async def queued_jobs(session):
    session.expire_all()
    return (
        (await session.execute(select(Job).where(Job.status == "queued").order_by(Job.created_at)))
        .scalars()
        .all()
    )


async def test_a_slow_video_frees_the_worker_between_checks(
    client, session, sessionmaker, monkeypatch
):
    monkeypatch.setattr(get_settings(), "video_poll_seconds", 5)
    calls = slow_render(monkeypatch, polls_until_done=2)
    generation_id = await queue_preview(client, session, sessionmaker, monkeypatch)

    assert await run_one(sessionmaker)  # submits and checks once: still running
    assert len(calls) == 1
    (check,) = await queued_jobs(session)
    assert check.kind == "poll_video"
    # The next check waits; nothing is ready to run, so the worker is free for other work.
    assert check.run_after > datetime.now(UTC)
    assert not await run_one(sessionmaker)
    progress = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert progress["status"] in ("queued", "running")

    await drain(sessionmaker)
    assert len(calls) == 3
    done = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert done["status"] == "done"
    assert (await client.get(done["video_url"])).status_code == 200


async def test_checks_stop_after_the_maximum_wait(client, session, sessionmaker, monkeypatch):
    monkeypatch.setattr(get_settings(), "video_max_wait_seconds", 0)
    slow_render(monkeypatch, polls_until_done=None)
    generation_id = await queue_preview(client, session, sessionmaker, monkeypatch)
    await drain(sessionmaker)
    failed = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert failed["status"] == "failed"
    assert "still processing" in failed["error"]
    assert await queued_jobs(session) == []
    generation = await session.get(VideoGeneration, uuid.UUID(generation_id))
    await session.refresh(generation)
    assert generation.provider_request  # kept, so staff can follow it up


async def test_a_check_is_never_charged_or_cached(client, session, sessionmaker, monkeypatch):
    from app.models import ProviderCacheEntry

    slow_render(monkeypatch, polls_until_done=1)
    await queue_preview(client, session, sessionmaker, monkeypatch)
    await drain(sessionmaker)
    operations = (await session.execute(select(ProviderCacheEntry.operation))).scalars().all()
    assert "video_status" not in operations
