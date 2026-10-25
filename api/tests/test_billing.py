from app.config import get_settings


async def signup(client, email="premium@example.com"):
    return (
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "premium-test-password",
                "display_name": "Premium Member",
            },
        )
    ).json()


async def test_dummy_checkout_upgrades_only_its_signed_in_owner(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "dummy_checkout_seconds", 0)
    user = await signup(client)
    assert user["plan"] == "free"
    response = await client.post(
        "/api/v1/billing/checkout", json={"request_id": "checkout-1", "scenario": "success"}
    )
    assert response.status_code == 201, response.text
    attempt = response.json()
    assert attempt["status"] == "processing"
    assert (await client.get("/api/v1/auth/me")).json()["plan"] == "free"
    finished = await client.get(f"/api/v1/billing/checkout/{attempt['id']}")
    assert finished.json()["status"] == "succeeded"
    assert (await client.get("/api/v1/auth/me")).json()["plan"] == "premium"
    repeat = await client.post(
        "/api/v1/billing/checkout", json={"request_id": "checkout-1", "scenario": "success"}
    )
    assert repeat.json()["id"] == attempt["id"]
    await client.post("/api/v1/auth/logout")
    await signup(client, "another@example.com")
    assert (await client.get(f"/api/v1/billing/checkout/{attempt['id']}")).status_code == 404
    assert (await client.get("/api/v1/auth/me")).json()["plan"] == "free"


async def test_failed_dummy_payment_does_not_upgrade_membership(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "dummy_checkout_seconds", 0)
    await signup(client)
    attempt = (
        await client.post(
            "/api/v1/billing/checkout", json={"request_id": "fail-1", "scenario": "failure"}
        )
    ).json()
    assert (await client.get(f"/api/v1/billing/checkout/{attempt['id']}")).json()[
        "status"
    ] == "failed"
    assert (await client.get("/api/v1/auth/me")).json()["plan"] == "free"


async def test_premium_samples_are_access_controlled_and_seekable(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "dummy_checkout_seconds", 0)
    samples = (await client.get("/api/v1/video-samples")).json()
    assert len(samples) >= 2
    assert (await client.get(samples[0]["video_url"])).status_code == 401
    await signup(client)
    assert (await client.get(samples[0]["video_url"])).status_code == 403
    attempt = (
        await client.post(
            "/api/v1/billing/checkout", json={"request_id": "sample-1", "scenario": "success"}
        )
    ).json()
    await client.get(f"/api/v1/billing/checkout/{attempt['id']}")
    video = await client.get(samples[0]["video_url"], headers={"Range": "bytes=0-99"})
    assert video.status_code == 206
    assert video.headers["content-type"] == "video/webm"
    assert len(video.content) == 100
