"""Fixes from the review of the provider and voice work: races, costs, video checks."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select, update

from app import gateway
from app.config import get_settings
from app.errors import UserFacingError
from app.models import (
    AuditEvent,
    Job,
    ProviderCacheEntry,
    SpendEntry,
    Story,
    VideoGeneration,
    VoiceClone,
)
from app.providers import fake
from tests.http_mock import mock_http
from tests.test_moderation import drain
from tests.test_voice_lifecycle import (
    as_staff,
    create_voice,
    media,  # noqa: F401  (fixture)
    member_story,
    story,
)

__all__ = ["media"]


@pytest.fixture(autouse=True)
def fresh_fakes():
    fake.reset()
    yield
    fake.reset()


async def cloned_narration_queued(client, sessionmaker, media):  # noqa: F811
    """A member's story with a ready clone chosen as narrator, the narrate job not yet run."""
    published = await member_story(client, sessionmaker, media)
    await as_staff(client, sessionmaker)
    voice = await create_voice(client, media)
    await drain(sessionmaker)
    r = await client.put(
        f"/api/v1/staff/stories/{published['id']}/narrator", json={"voice_id": voice["id"]}
    )
    assert r.status_code == 202
    return published, voice


async def cached_speech_in(session, voice_id="demo-consenting-voice"):
    session.expire_all()
    return [
        e
        for e in (await session.execute(select(ProviderCacheEntry))).scalars()
        if e.operation == "speak" and e.result.get("voice") == voice_id
    ]


# --- revocation while narration is queued or running ---


async def test_a_queued_narration_never_speaks_in_a_revoked_voice(
    client,
    sessionmaker,
    session,
    media,  # noqa: F811
):
    published, voice = await cloned_narration_queued(client, sessionmaker, media)
    await session.execute(
        update(VoiceClone).values(revoked_at=datetime.now(UTC))  # revoked behind the job's back
    )
    await session.commit()
    fake.CALLS.clear()
    await drain(sessionmaker)
    assert not [c for c in fake.CALLS if c[0] == "speak" and c[2] == "demo-consenting-voice"]
    assert await cached_speech_in(session) == []


async def test_speech_made_while_the_voice_was_revoked_is_deleted(
    client,
    sessionmaker,
    session,
    media,
    monkeypatch,  # noqa: F811
):
    published, voice = await cloned_narration_queued(client, sessionmaker, media)
    original = fake.FakeTextToSpeech.speak

    async def speak_then_revoked(self, texts, language, voice_name):
        result = await original(self, texts, language, voice_name)
        async with sessionmaker() as s:  # revoked while the provider was speaking
            await s.execute(update(VoiceClone).values(revoked_at=datetime.now(UTC)))
            await s.commit()
        return result

    monkeypatch.setattr(fake.FakeTextToSpeech, "speak", speak_then_revoked)
    await drain(sessionmaker)
    assert await cached_speech_in(session) == []
    assert (await story(client, published["id"]))["narration"]["narrated_by"] is None


async def test_revoking_renarrates_a_story_still_being_checked(
    client,
    sessionmaker,
    session,
    media,  # noqa: F811
):
    published, voice = await cloned_narration_queued(client, sessionmaker, media)
    await drain(sessionmaker)
    await session.execute(
        update(Story).where(Story.id == uuid.UUID(published["id"])).values(status="moderating")
    )
    await session.commit()
    await client.post(f"/api/v1/staff/voices/{voice['id']}/revoke")
    await drain(sessionmaker)
    again = await story(client, published["id"])
    assert again["narration"] and again["narration"]["narrated_by"] is None


# --- choosing narrators ---


async def test_staff_see_which_voice_narrates_a_story(client, sessionmaker, media):  # noqa: F811
    published, voice = await cloned_narration_queued(client, sessionmaker, media)
    assert (await story(client, published["id"]))["narrator_voice_id"] == voice["id"]
    client.cookies.clear()
    assert (await story(client, published["id"]))["narrator_voice_id"] is None  # not public


async def test_a_clone_is_not_sent_to_a_provider_that_cannot_use_it(
    client,
    sessionmaker,
    session,
    media,
    monkeypatch,  # noqa: F811
):
    published, voice = await cloned_narration_queued(client, sessionmaker, media)
    await drain(sessionmaker)
    monkeypatch.setattr(get_settings(), "tts_provider", "azure")
    from app import media as media_module

    async with sessionmaker() as s:
        await media_module.queue(s, await s.get(Story, uuid.UUID(published["id"])))
        await s.commit()
    job = (
        (
            await session.execute(
                select(Job).where(Job.kind == "narrate").order_by(Job.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    assert job.payload["voice"] is None and job.payload["voice_clone_id"] is None


# --- verification and the provider's own message ---


async def test_staff_mark_a_voice_verified_after_the_provider_step(
    client,
    sessionmaker,
    session,
    media,  # noqa: F811
):
    await as_staff(client, sessionmaker)
    voice = await create_voice(client, media)
    await drain(sessionmaker)
    await session.execute(update(VoiceClone).values(requires_verification=True))
    await session.commit()
    r = await client.post(f"/api/v1/staff/voices/{voice['id']}/verified")
    assert r.status_code == 200 and r.json()["state"] == "ready"
    actions = [e.action for e in (await session.execute(select(AuditEvent))).scalars()]
    assert "voice_verified" in actions


async def test_elevenlabs_clone_request_and_its_own_error_message(monkeypatch, tmp_path):
    from app.providers.voices import VoiceCloner

    monkeypatch.setattr(get_settings(), "elevenlabs_api_key", "el-key")
    sample = tmp_path / "sample.mp3"
    sample.write_bytes(b"ID3sample")
    consent = {
        "speaker_confirmed": True,
        "rights_confirmed": True,
        "use_confirmed": True,
        "speaker_name": "Um Ahmad",
        "version": "v",
        "at": "2026-10-26T00:00:00+00:00",
    }
    seen = mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"voice_id": "abc", "requires_verification": True}
        ),
    )
    result = await VoiceCloner("elevenlabs").clone(sample, consent)
    assert result == {"voice_id": "abc", "requires_verification": True}
    assert str(seen[0].url) == "https://api.elevenlabs.io/v1/voices/add"
    assert seen[0].headers["xi-api-key"] == "el-key"
    assert b'name="name"' in seen[0].content and b"Um Ahmad" in seen[0].content
    assert b"ID3sample" in seen[0].content

    detail = {
        "detail": {"status": "voice_limit_reached", "message": "You have reached your voice limit."}
    }
    mock_http(monkeypatch, lambda request: httpx.Response(400, json=detail))
    with pytest.raises(UserFacingError, match="voice limit") as caught:
        await VoiceCloner("elevenlabs").clone(sample, consent)
    assert "el-key" not in str(caught.value)


# --- Azure tokens billed for an unusable answer ---


async def test_tokens_for_a_refused_answer_are_still_counted(session, monkeypatch):
    settings = get_settings()
    for name, value in (
        ("llm_provider", "azure"),
        ("live_ai_enabled", True),
        ("azure_openai_endpoint", "https://x.openai.azure.com"),
        ("azure_openai_api_key", "k"),
        ("azure_openai_deployment", "d"),
    ):
        monkeypatch.setattr(settings, name, value)
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": None, "refusal": "No"}}
                ],
                "usage": {"prompt_tokens": 2000, "completion_tokens": 1000},
            },
        ),
    )
    from app.providers import language_model

    model = language_model()

    async def run():
        return {"texts": await model.polish(["x"], "english")}

    with pytest.raises(UserFacingError):
        await gateway.call("polish", model, ("english", "", '["x"]'), 1, run)
    entry = (await session.execute(select(SpendEntry))).scalar_one()
    assert entry.state == "committed" and entry.actual_usd == Decimal("0.0060")


# --- narration timing with an empty line ---


async def test_an_empty_line_keeps_timings_in_order(monkeypatch):
    from tests.test_tts_adapters import aligned, mp3

    settings = get_settings()
    for name, value in (
        ("tts_provider", "elevenlabs"),
        ("elevenlabs_api_key", "k"),
        ("elevenlabs_voice_arabic", "a"),
        ("elevenlabs_voice_english", "e"),
    ):
        monkeypatch.setattr(settings, name, value)
    audio = mp3(1)
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200, json=aligned(json.loads(request.content)["text"], audio)
        ),
    )
    from app.providers import text_to_speech

    speech = await text_to_speech().speak(["", "one", "", "two"], "english", "e")
    starts = [start for start, _ in speech.lines]
    assert len(speech.lines) == 4 and starts == sorted(starts) and starts[0] == 0
    assert all(end >= start for start, end in speech.lines)


# --- video checks ---


async def queue_fake_video(client, session, sessionmaker, monkeypatch):
    from tests.test_videos import queue_preview

    return await queue_preview(client, session, sessionmaker, monkeypatch)


async def test_a_failed_download_is_checked_again_not_abandoned(
    client, session, sessionmaker, monkeypatch
):
    from app.providers.video import FakeVideo

    attempts = []
    original = FakeVideo.download

    async def flaky(self, url):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("blip")
        return await original(self, url)

    monkeypatch.setattr(FakeVideo, "download", flaky)
    generation_id = await queue_fake_video(client, session, sessionmaker, monkeypatch)
    await drain(sessionmaker)
    done = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert done["status"] == "done" and len(attempts) == 2


async def test_the_maximum_wait_counts_from_when_the_video_was_queued(
    client, session, sessionmaker, monkeypatch
):
    from tests.test_videos import slow_render

    monkeypatch.setattr(get_settings(), "video_max_wait_seconds", 600)
    slow_render(monkeypatch, polls_until_done=None)
    generation_id = await queue_fake_video(client, session, sessionmaker, monkeypatch)
    # Queued long ago (as if earlier attempts had used up the wait): no fresh window.
    await session.execute(
        update(VideoGeneration).values(created_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await session.commit()
    await drain(sessionmaker)
    failed = (await client.get(f"/api/v1/staff/videos/{generation_id}")).json()
    assert failed["status"] == "failed" and "still processing" in failed["error"]


def test_video_cost_can_be_per_second(monkeypatch):
    from app.providers.video import provider

    monkeypatch.setattr(get_settings(), "fal_key", "k")
    monkeypatch.setattr(get_settings(), "video_usd_per_second", 0.05)
    assert provider("fal").estimate_usd("video_submit", 6) == Decimal("0.30")
    monkeypatch.setattr(get_settings(), "video_usd_per_second", 0.0)
    assert provider("fal").estimate_usd("video_submit", 6) == Decimal("1.0")
