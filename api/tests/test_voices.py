import subprocess

import pytest

from app.models import Role
from app.seed_staff import StaffSeed, seed_staff
from app.worker import run_one

PASSWORD = "voice-test-password"


async def staff(client, sessionmaker):
    await seed_staff(
        sessionmaker, [StaffSeed("voice@example.com", PASSWORD, Role.ADMIN, "Voice staff")]
    )
    await client.post(
        "/api/v1/auth/login", json={"email": "voice@example.com", "password": PASSWORD}
    )


@pytest.fixture(scope="session")
def sample(tmp_path_factory):
    path = tmp_path_factory.mktemp("voice") / "sample.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=31", "-ac", "1", str(path)],
        check=True,
    )
    return path


async def test_voice_cloning_is_staff_only(client):
    assert (await client.get("/api/v1/staff/voices")).status_code == 401
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "member@example.com", "password": PASSWORD, "display_name": "Member"},
    )
    assert (await client.get("/api/v1/staff/voices")).status_code == 403


async def test_consent_and_sample_are_saved_before_a_clone_job_runs(client, sessionmaker, sample):
    await staff(client, sessionmaker)
    statement = (await client.get("/api/v1/staff/voices/consent")).json()
    data = {
        "speaker_name": "Test speaker",
        "consent_version": statement["version"],
        "speaker_confirmed": "true",
        "rights_confirmed": "true",
        "use_confirmed": "true",
        "request_id": "test-voice-1",
    }
    with sample.open("rb") as audio:
        response = await client.post(
            "/api/v1/staff/voices", data=data, files={"file": ("sample.wav", audio, "audio/wav")}
        )
    assert response.status_code == 202, response.text
    voice = response.json()
    assert voice["status"] == "queued"
    assert voice["consent"]["text"] == statement["text"]
    assert voice["consent"]["speaker_name"] == "Test speaker"
    assert voice["consent"]["at"]
    assert voice["duration_ms"] == pytest.approx(31000, abs=100)
    assert await run_one(sessionmaker)
    ready = (await client.get(f"/api/v1/staff/voices/{voice['id']}")).json()
    assert ready["status"] == "done"
    assert ready["demo"] is True
    assert (await client.get(ready["sample_url"])).status_code == 200
    await client.post("/api/v1/auth/logout")
    assert (await client.get(ready["sample_url"])).status_code == 401


@pytest.mark.parametrize(
    "override",
    [
        {"consent_version": "old"},
        {"speaker_confirmed": "false"},
        {"rights_confirmed": "false"},
        {"use_confirmed": "false"},
    ],
)
async def test_missing_or_outdated_consent_never_queues_cloning(
    client, sessionmaker, sample, override
):
    await staff(client, sessionmaker)
    statement = (await client.get("/api/v1/staff/voices/consent")).json()
    data = {
        "speaker_name": "Test",
        "consent_version": statement["version"],
        "speaker_confirmed": "true",
        "rights_confirmed": "true",
        "use_confirmed": "true",
        "request_id": "bad-consent",
        **override,
    }
    with sample.open("rb") as audio:
        response = await client.post(
            "/api/v1/staff/voices", data=data, files={"file": ("sample.wav", audio, "audio/wav")}
        )
    assert response.status_code == 422
    assert (await client.get("/api/v1/staff/voices")).json() == []


async def test_live_voice_cloning_is_refused_without_the_live_switch(
    client, sessionmaker, sample, monkeypatch
):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "voice_clone_provider", "elevenlabs")
    monkeypatch.setattr(get_settings(), "live_ai_enabled", False)
    await staff(client, sessionmaker)
    statement = (await client.get("/api/v1/staff/voices/consent")).json()
    data = {
        "speaker_name": "Test speaker",
        "consent_version": statement["version"],
        "speaker_confirmed": "true",
        "rights_confirmed": "true",
        "use_confirmed": "true",
        "request_id": "live-off",
    }
    with sample.open("rb") as audio:
        created = (
            await client.post(
                "/api/v1/staff/voices",
                data=data,
                files={"file": ("sample.wav", audio, "audio/wav")},
            )
        ).json()
    with sample.open("rb") as audio:
        repeated = (
            await client.post(
                "/api/v1/staff/voices",
                data=data,
                files={"file": ("sample.wav", audio, "audio/wav")},
            )
        ).json()
    assert repeated["id"] == created["id"]
    assert await run_one(sessionmaker)
    result = (await client.get(f"/api/v1/staff/voices/{created['id']}")).json()
    assert result["status"] == "failed"
    assert "switched off" in result["error"]
    assert result["voice_id"] is None
