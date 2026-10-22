"""Spending ledger, result cache, live-AI switch and the demo pack, through the worker."""

import io
import subprocess
import tarfile
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text, update

from app import demo_pack
from app.config import get_settings
from app.models import Job, ProviderCacheEntry, SpendEntry
from app.providers import fake
from app.worker import run_one

PASSWORD = "correct horse battery"


@pytest.fixture(scope="session")
def tone(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("gw") / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=6", "-ac", "1", str(path)],
        check=True,
    )
    return path


@pytest.fixture(autouse=True)
def paid_fakes(monkeypatch):
    """The fakes act as paid providers: card for speech, Azure for the language model."""
    fake.reset()
    fake.PAID.update({"transcribe": ("card", "0.40"), "llm": ("azure", "0.10")})
    settings = get_settings()
    monkeypatch.setattr(settings, "live_ai_enabled", True)
    monkeypatch.setattr(settings, "spend_cap_usd_total", 25.0)
    monkeypatch.setattr(settings, "spend_cap_usd_daily", 10.0)
    monkeypatch.setattr(settings, "spend_cap_usd_azure", 50.0)
    yield settings
    fake.reset()


async def drain(sessionmaker):
    while True:
        async with sessionmaker() as s:
            await s.execute(
                update(Job).where(Job.status == "queued").values(run_after=text("now()"))
            )
            await s.commit()
        if not await run_one(sessionmaker):
            return


async def story_with_audio(client, tone, email="salma@example.com"):
    client.cookies.clear()
    await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "display_name": "S"}
    )
    story = (await client.post("/api/v1/stories", json={"original_language": "jordanian"})).json()
    with open(tone, "rb") as f:
        await client.put(
            f"/api/v1/stories/{story['id']}/audio", files={"file": ("t.wav", f, "audio/wav")}
        )
    return story["id"]


async def steps(client, story_id):
    body = (await client.get(f"/api/v1/stories/{story_id}/pipeline")).json()
    return {s["step"]: s for s in body["steps"]}


async def entries(session):
    return (
        (await session.execute(select(SpendEntry).order_by(SpendEntry.created_at))).scalars().all()
    )


async def test_paid_calls_are_recorded_against_their_job(client, sessionmaker, session, tone):
    story_id = await story_with_audio(client, tone)
    await drain(sessionmaker)
    rows = await entries(session)
    assert {(r.operation, r.budget, r.state) for r in rows} == {
        ("transcribe", "card", "committed"),
        ("polish", "azure", "committed"),
        ("translate", "azure", "committed"),
    }
    assert all(r.job_id is not None and r.actual_usd == r.estimated_usd for r in rows)
    jobs = {j.kind: j for j in (await session.execute(select(Job))).scalars()}
    assert jobs["transcribe"].provider_cost_usd == Decimal("0.4000")
    assert all(s["status"] == "done" for s in (await steps(client, story_id)).values())


async def test_a_cache_hit_costs_nothing_and_never_calls_the_provider(
    client, sessionmaker, session, tone
):
    await story_with_audio(client, tone)
    await drain(sessionmaker)
    before = len(await entries(session))
    fake.CALLS.clear()
    # Another member uploads the same recording: everything comes from the cache.
    story_id = await story_with_audio(client, tone, email="other@example.com")
    await drain(sessionmaker)
    assert fake.CALLS == []
    assert len(await entries(session)) == before
    assert all(s["status"] == "done" for s in (await steps(client, story_id)).values())


async def test_live_ai_off_refuses_a_cache_miss_and_allows_a_hit(
    client, sessionmaker, session, tone, paid_fakes
):
    paid_fakes.live_ai_enabled = False
    story_id = await story_with_audio(client, tone)
    await drain(sessionmaker)
    status = await steps(client, story_id)
    assert status["transcribe"]["status"] == "failed"
    assert "Live AI is switched off" in status["transcribe"]["message"]
    assert fake.CALLS == [] and await entries(session) == []

    # Fill the cache with live AI on, then switch it off again: a hit still works.
    paid_fakes.live_ai_enabled = True
    await story_with_audio(client, tone, email="warm@example.com")
    await drain(sessionmaker)
    paid_fakes.live_ai_enabled = False
    later = await story_with_audio(client, tone, email="later@example.com")
    await drain(sessionmaker)
    assert all(s["status"] == "done" for s in (await steps(client, later)).values())


async def test_the_total_card_cap_refuses_and_releases(
    client, sessionmaker, session, tone, paid_fakes
):
    paid_fakes.spend_cap_usd_total = 0.30  # below one transcription
    story_id = await story_with_audio(client, tone)
    await drain(sessionmaker)
    status = await steps(client, story_id)
    assert status["transcribe"]["status"] == "failed"
    assert "spending limit" in status["transcribe"]["message"]
    assert fake.CALLS == []
    assert all(r.state == "released" for r in await entries(session))


async def test_the_daily_cap_counts_only_today(client, sessionmaker, session, tone, paid_fakes):
    paid_fakes.spend_cap_usd_daily = 1.0
    session.add_all(
        [
            SpendEntry(provider="x", operation="x", budget="card", estimated_usd=Decimal("0.8"),
                       actual_usd=Decimal("0.8"), state="committed"),
            SpendEntry(provider="x", operation="x", budget="card", estimated_usd=Decimal("5"),
                       actual_usd=Decimal("5"), state="committed",
                       created_at=text("now() - interval '2 days'")),
        ]
    )  # fmt: skip
    await session.commit()
    story_id = await story_with_audio(client, tone)
    await drain(sessionmaker)
    status = await steps(client, story_id)
    assert status["transcribe"]["status"] == "failed"  # 0.8 today + 0.4 > 1.0
    paid_fakes.spend_cap_usd_daily = 2.0
    assert (
        await client.post(f"/api/v1/stories/{story_id}/pipeline/transcribe/retry")
    ).status_code == 200
    await drain(sessionmaker)
    assert (await steps(client, story_id))["transcribe"]["status"] == "done"


async def test_the_azure_cap_is_separate(client, sessionmaker, session, tone, paid_fakes):
    paid_fakes.spend_cap_usd_azure = 0.05  # below one language-model call
    story_id = await story_with_audio(client, tone)
    await drain(sessionmaker)
    status = await steps(client, story_id)
    assert status["transcribe"]["status"] == "done"  # card budget unaffected
    assert status["polish"]["status"] == "failed"
    assert "spending limit" in status["polish"]["message"]


async def test_a_failed_call_releases_its_reservation(client, sessionmaker, session, tone):
    fake.FAIL_ON.add("transcribe")
    await story_with_audio(client, tone)
    await drain(sessionmaker)
    rows = await entries(session)
    assert rows and all(r.state == "released" for r in rows)


async def test_demo_pack_round_trip(client, sessionmaker, session, tone, tmp_path, paid_fakes):
    await story_with_audio(client, tone)
    await drain(sessionmaker)
    pack = tmp_path / "pack.tar.gz"
    exported = await demo_pack.export_pack(sessionmaker, pack)
    assert exported >= 4 and pack.is_file()

    await session.execute(text("TRUNCATE provider_cache"))
    await session.commit()
    assert await demo_pack.import_pack(sessionmaker, pack) == exported
    assert await demo_pack.import_pack(sessionmaker, pack) == 0  # already there

    paid_fakes.live_ai_enabled = False
    fake.CALLS.clear()
    later = await story_with_audio(client, tone, email="stage@example.com")
    await drain(sessionmaker)
    assert fake.CALLS == []
    assert all(s["status"] == "done" for s in (await steps(client, later)).values())
    assert len((await session.execute(select(ProviderCacheEntry))).scalars().all()) == exported


async def test_demo_pack_refuses_unsafe_archives(sessionmaker, tmp_path):
    pack = tmp_path / "evil.tar.gz"
    with tarfile.open(pack, "w:gz") as tar:
        for name, data in (("cache.json", b"[]"), ("../../etc/evil", b"x")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    with pytest.raises(demo_pack.BadPack):
        await demo_pack.import_pack(sessionmaker, pack)
