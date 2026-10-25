"""Voice cloning (#18) after consent: states, choosing a cloned narrator, revocation, audit."""

import subprocess

import httpx
import pytest
from sqlalchemy import select, update

from app.config import get_settings
from app.models import AuditEvent, Job, ProviderCacheEntry, Role, VoiceClone
from app.providers import fake
from app.seed_staff import StaffSeed, seed_staff
from app.storage import get_storage
from tests.http_mock import mock_http
from tests.test_moderation import drain, sign_up
from tests.test_narration import publish, story_with_photo
from tests.test_story_photos import make_image

PASSWORD = "voice-test-password"
STAFF = "voice@example.com"


@pytest.fixture(autouse=True)
def fresh_fakes():
    fake.reset()
    yield
    fake.reset()


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    folder = tmp_path_factory.mktemp("voice-lifecycle")
    sample, tone = folder / "sample.wav", folder / "tone.wav"
    for path, seconds in ((sample, 31), (tone, 6)):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=duration={seconds}",
             "-ac", "1", str(path)],
            check=True,
        )  # fmt: skip
    return {"sample": sample, "tone": tone, "photo": make_image(folder / "photo.png")}


async def as_staff(client, sessionmaker, role=Role.REVIEWER):
    await seed_staff(sessionmaker, [StaffSeed(STAFF, PASSWORD, role, "Voice staff")])
    client.cookies.clear()
    await client.post("/api/v1/auth/login", json={"email": STAFF, "password": PASSWORD})


async def create_voice(client, media, name="Um Ahmad", request_id="r1"):
    statement = (await client.get("/api/v1/staff/voices/consent")).json()
    with media["sample"].open("rb") as f:
        r = await client.post(
            "/api/v1/staff/voices",
            data={
                "speaker_name": name,
                "consent_version": statement["version"],
                "speaker_confirmed": "true",
                "rights_confirmed": "true",
                "use_confirmed": "true",
                "request_id": request_id,
            },
            files={"file": ("sample.wav", f, "audio/wav")},
        )
    assert r.status_code == 202, r.text
    return r.json()


async def voice_state(client, voice_id):
    return (await client.get(f"/api/v1/staff/voices/{voice_id}")).json()


async def member_story(client, sessionmaker, media):
    """A member's published story with its default narration."""
    await sign_up(client, "teller@example.com")
    story_id = await story_with_photo(client, sessionmaker, media["tone"], [media["photo"]])
    return await publish(client, sessionmaker, story_id)


async def story(client, story_id):
    return (await client.get(f"/api/v1/stories/{story_id}")).json()


async def audit_actions(session):
    session.expire_all()
    return [
        (e.action, e.target_type)
        for e in (
            await session.execute(select(AuditEvent).order_by(AuditEvent.created_at))
        ).scalars()
    ]


# --- states ---


async def test_a_voice_is_preparing_then_ready(client, sessionmaker, session, media):
    await as_staff(client, sessionmaker)
    voice = await create_voice(client, media)
    assert voice["state"] == "preparing"
    await drain(sessionmaker)
    ready = await voice_state(client, voice["id"])
    assert ready["state"] == "ready" and ready["message"] is None
    assert ("voice_created", "voice") in await audit_actions(session)


async def test_a_failed_clone_shows_the_providers_message(client, sessionmaker, session, media):
    await as_staff(client, sessionmaker)
    voice = await create_voice(client, media)
    await session.execute(update(Job).values(status="failed", error="The voice was rejected."))
    await session.commit()
    failed = await voice_state(client, voice["id"])
    assert failed["state"] == "failed" and failed["message"] == "The voice was rejected."


async def test_a_voice_needing_verification_says_so(client, sessionmaker, session, media):
    await as_staff(client, sessionmaker)
    voice = await create_voice(client, media)
    await drain(sessionmaker)
    await session.execute(update(VoiceClone).values(requires_verification=True))
    await session.commit()
    pending = await voice_state(client, voice["id"])
    assert pending["state"] == "needs_verification"
    assert "verify" in pending["message"]


async def test_cloning_is_refused_when_narration_cannot_use_clones(
    client, sessionmaker, monkeypatch, media
):
    monkeypatch.setattr(get_settings(), "tts_provider", "azure")
    await as_staff(client, sessionmaker)
    statement = (await client.get("/api/v1/staff/voices/consent")).json()
    assert statement["available"] is False and "Azure" in statement["reason"]
    with media["sample"].open("rb") as f:
        r = await client.post(
            "/api/v1/staff/voices",
            data={
                "speaker_name": "X",
                "consent_version": statement["version"],
                "speaker_confirmed": "true",
                "rights_confirmed": "true",
                "use_confirmed": "true",
                "request_id": "r9",
            },
            files={"file": ("sample.wav", f, "audio/wav")},
        )
    assert r.status_code == 409 and "Azure" in r.json()["detail"]


# --- choosing a cloned narrator ---


async def test_staff_narrate_a_story_in_a_ready_cloned_voice(client, sessionmaker, session, media):
    before = await member_story(client, sessionmaker, media)
    await as_staff(client, sessionmaker)
    voice = await create_voice(client, media)
    await drain(sessionmaker)
    r = await client.put(
        f"/api/v1/staff/stories/{before['id']}/narrator", json={"voice_id": voice["id"]}
    )
    assert r.status_code == 202, r.text
    await drain(sessionmaker)
    after = await story(client, before["id"])
    assert after["narration"]["narrated_by"] == "Um Ahmad"
    assert after["narration"]["voice"] == "demo-consenting-voice"
    assert after["narration"]["url"] != before["narration"]["url"]
    assert after["slideshow"]["url"] != before["slideshow"]["url"]  # it carries the narration
    assert ("narration_regenerated", "story") in await audit_actions(session)
    # Back to the default voice.
    await client.put(f"/api/v1/staff/stories/{before['id']}/narrator", json={"voice_id": None})
    await drain(sessionmaker)
    assert (await story(client, before["id"]))["narration"]["narrated_by"] is None


async def test_only_a_ready_voice_can_narrate(client, sessionmaker, media):
    published = await member_story(client, sessionmaker, media)
    await as_staff(client, sessionmaker)
    voice = await create_voice(client, media)  # still preparing
    r = await client.put(
        f"/api/v1/staff/stories/{published['id']}/narrator", json={"voice_id": voice["id"]}
    )
    assert r.status_code == 409


async def test_choosing_a_narrator_is_staff_only_and_not_for_their_own_story(
    client, sessionmaker, media
):
    published = await member_story(client, sessionmaker, media)
    r = await client.put(
        f"/api/v1/staff/stories/{published['id']}/narrator", json={"voice_id": None}
    )
    assert r.status_code == 403  # the member is signed in, not staff
    await as_staff(client, sessionmaker)
    own = await story_with_photo(client, sessionmaker, media["tone"], [media["photo"]])
    r = await client.put(f"/api/v1/staff/stories/{own}/narrator", json={"voice_id": None})
    assert r.status_code == 403


# --- revocation ---


async def test_revoking_removes_the_voice_everywhere(client, sessionmaker, session, media):
    published = await member_story(client, sessionmaker, media)
    await as_staff(client, sessionmaker)
    voice = await create_voice(client, media)
    await drain(sessionmaker)
    await client.put(
        f"/api/v1/staff/stories/{published['id']}/narrator", json={"voice_id": voice["id"]}
    )
    await drain(sessionmaker)
    cloned = await story(client, published["id"])
    storage = get_storage()
    sample_key = (await session.get(VoiceClone, __import__("uuid").UUID(voice["id"]))).sample_key
    spoken = [
        e.file_key
        for e in (await session.execute(select(ProviderCacheEntry))).scalars()
        if e.operation == "speak" and e.result.get("voice") == "demo-consenting-voice"
    ]
    assert spoken and storage.exists(sample_key)

    r = await client.post(f"/api/v1/staff/voices/{voice['id']}/revoke")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "revoked"
    # At once: the cloned narration and its slideshow are gone, and so are the voice's files.
    right_away = await story(client, published["id"])
    assert right_away["narration"] is None and right_away["slideshow"] is None
    assert (await client.get(cloned["narration"]["url"])).status_code == 404
    assert not storage.exists(sample_key)
    assert not any(storage.exists(key) for key in spoken)
    # Then the story is narrated again in the default voice, and the provider voice deleted.
    await drain(sessionmaker)
    restored = await story(client, published["id"])
    assert restored["narration"]["narrated_by"] is None and restored["slideshow"]
    assert ("delete_voice", "demo-consenting-voice") in fake.CALLS
    assert ("voice_revoked", "voice") in await audit_actions(session)
    # A revoked voice cannot be chosen again.
    r = await client.put(
        f"/api/v1/staff/stories/{published['id']}/narrator", json={"voice_id": voice["id"]}
    )
    assert r.status_code == 409


async def test_the_audit_log_names_the_voice(client, sessionmaker, media):
    await as_staff(client, sessionmaker, Role.ADMIN)
    voice = await create_voice(client, media)
    await drain(sessionmaker)
    await client.post(f"/api/v1/staff/voices/{voice['id']}/revoke")
    log = (await client.get("/api/v1/staff/audit")).json()
    assert [(e["action"], e["target"]["title"]) for e in log] == [
        ("voice_revoked", "Um Ahmad"),
        ("voice_created", "Um Ahmad"),
    ]


# --- the ElevenLabs side ---


async def test_elevenlabs_voice_deletion_against_mocked_http(monkeypatch):
    from app.providers.voices import VoiceCloner

    monkeypatch.setattr(get_settings(), "elevenlabs_api_key", "el-key")
    seen = mock_http(monkeypatch, lambda request: httpx.Response(200, json={"status": "ok"}))
    await VoiceCloner("elevenlabs").delete("abc123")
    assert seen[0].method == "DELETE"
    assert str(seen[0].url) == "https://api.elevenlabs.io/v1/voices/abc123"
    assert seen[0].headers["xi-api-key"] == "el-key"


async def test_an_already_deleted_elevenlabs_voice_is_fine(monkeypatch):
    from app.providers.voices import VoiceCloner

    monkeypatch.setattr(get_settings(), "elevenlabs_api_key", "el-key")
    mock_http(monkeypatch, lambda request: httpx.Response(404, json={"detail": "gone"}))
    await VoiceCloner("elevenlabs").delete("abc123")  # no error
