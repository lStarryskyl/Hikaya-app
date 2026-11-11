"""Stories written or pasted as text: no recording, so nothing to transcribe."""

import asyncio
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app import pipeline
from app.config import get_settings
from app.models import Asset, Job, PipelineStep
from app.pipeline import lines_from_text
from app.providers import fake
from app.storage import get_storage
from tests.conftest import CONSENT
from tests.test_pipeline import drain, get_story, layers_by_kind, sign_up, status, story_with_audio

TEXT = "كان جدي يحكي لنا عن البتراء. كنا نجلس حول النار!\n\nهل تعرفون قصة الخزنة؟ سأحكيها لكم"
TEXT_LINES = [
    "كان جدي يحكي لنا عن البتراء.",
    "كنا نجلس حول النار!",
    "هل تعرفون قصة الخزنة؟",
    "سأحكيها لكم",
]


@pytest.fixture(autouse=True)
def fresh_fakes():
    fake.reset()
    yield
    fake.reset()


@pytest.fixture(scope="session")
def tone(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("text-stories") / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=6", "-ac", "1", str(path)],
        check=True,
    )  # fmt: skip
    return path


async def new_story(client, language="jordanian"):
    fields = {"original_language": language} if language else {}
    r = await client.post("/api/v1/stories", json=fields)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def put_text(client, story_id, text):
    return await client.put(f"/api/v1/stories/{story_id}/text", json={"text": text})


# --- splitting into lines ---


def test_text_is_split_into_lines_at_breaks_and_sentence_ends():
    assert lines_from_text(TEXT) == TEXT_LINES
    assert lines_from_text("One. Two?\r\nThree") == ["One.", "Two?", "Three"]
    # A full stop inside a number, or a closing quote after the stop, is not a new line.
    assert lines_from_text('It cost 3.5 dinars. "Too much." He left.') == [
        "It cost 3.5 dinars.",
        '"Too much."',
        "He left.",
    ]
    assert lines_from_text("  \n\n \t ") == []


def test_a_long_line_is_split_at_a_space():
    words = " ".join(["word"] * 200)  # 999 characters and no sentence end
    lines = lines_from_text(words)
    assert len(lines) > 1
    assert all(len(line) <= 300 for line in lines)
    assert " ".join(lines) == words


# --- the pipeline ---


async def test_text_skips_transcription_and_runs_polish_and_translations(client, sessionmaker):
    await sign_up(client)
    story_id = await new_story(client)

    r = await put_text(client, story_id, TEXT)
    assert r.status_code == 200, r.text
    story = r.json()
    assert story["audio"] is None
    verbatim = layers_by_kind(story)["verbatim"]
    assert verbatim["language"] == "jordanian"
    assert [s["text"] for s in verbatim["segments"]] == TEXT_LINES
    # Estimated slots, distinct and in order, so every line stays apart.
    starts = [s["start_ms"] for s in verbatim["segments"]]
    assert starts == sorted(set(starts))
    assert all(s["end_ms"] > s["start_ms"] for s in verbatim["segments"])

    steps, body = await status(client, story_id)
    assert set(steps) == {"polish", "translate_en", "translate_msa"}
    assert steps["polish"]["status"] == "queued"
    assert body["complete"] is False

    await drain(sessionmaker)
    steps, body = await status(client, story_id)
    assert {k: v["status"] for k, v in steps.items()} == {
        "polish": "done",
        "translate_en": "done",
        "translate_msa": "done",
    }
    assert body["complete"] is True
    layers = layers_by_kind(await get_story(client, story_id))
    assert set(layers) == {"verbatim", "polished", "translation_en", "translation_msa"}
    assert len(layers["translation_en"]["segments"]) == len(TEXT_LINES)


async def test_editing_the_words_of_a_text_story_polishes_them_again(client, sessionmaker):
    await sign_up(client)
    story_id = await new_story(client, "english")
    await put_text(client, story_id, "My grandfather told stories. We listened.")
    await drain(sessionmaker)

    r = await client.patch(
        f"/api/v1/stories/{story_id}/layers/verbatim",
        json={"texts": ["My grandmother told stories.", "We listened."]},
    )
    assert r.status_code == 200, r.text
    steps, _ = await status(client, story_id)
    assert steps["polish"]["status"] == "queued"
    await drain(sessionmaker)
    steps, body = await status(client, story_id)
    assert body["complete"] is True


async def test_changing_the_language_of_a_text_story_polishes_the_same_words_again(
    client, sessionmaker
):
    await sign_up(client)
    story_id = await new_story(client)
    await put_text(client, story_id, "My grandfather told stories. We listened.")
    await drain(sessionmaker)

    r = await client.patch(f"/api/v1/stories/{story_id}", json={"original_language": "english"})
    assert r.status_code == 200, r.text
    layers = layers_by_kind(r.json())
    assert set(layers) == {"verbatim"}
    assert layers["verbatim"]["language"] == "english"
    assert [s["text"] for s in layers["verbatim"]["segments"]] == [
        "My grandfather told stories.",
        "We listened.",
    ]

    await drain(sessionmaker)
    steps, body = await status(client, story_id)
    assert set(steps) == {"polish", "translate_msa"}
    assert body["complete"] is True
    assert set(layers_by_kind(await get_story(client, story_id))) == {
        "verbatim",
        "polished",
        "translation_msa",
    }


# --- one source at a time ---


async def test_text_replaces_a_recording_and_a_recording_replaces_text(
    client, session, sessionmaker, tone
):
    await sign_up(client)
    story_id = await story_with_audio(client, tone)
    await drain(sessionmaker)
    keys = [
        a.storage_key
        for a in (
            await session.execute(select(Asset).where(Asset.story_id == uuid.UUID(story_id)))
        ).scalars()
    ]
    assert keys

    r = await put_text(client, story_id, TEXT)
    assert r.status_code == 200, r.text
    story = r.json()
    assert story["audio"] is None
    assert story["duration_ms"] is None
    assert set(layers_by_kind(story)) == {"verbatim"}  # the recording's text is gone
    assert [s["text"] for s in layers_by_kind(story)["verbatim"]["segments"]] == TEXT_LINES
    steps, _ = await status(client, story_id)
    assert "transcribe" not in steps
    assert not any(get_storage().path(key).exists() for key in keys)
    await drain(sessionmaker)

    with open(tone, "rb") as f:
        r = await client.put(
            f"/api/v1/stories/{story_id}/audio", files={"file": (tone.name, f, "audio/wav")}
        )
    assert r.status_code == 200, r.text
    assert r.json()["layers"] == []  # starts over from transcription
    steps, _ = await status(client, story_id)
    assert steps["transcribe"]["status"] == "queued"


async def test_text_waits_for_a_transcript_being_saved_instead_of_deadlocking(
    client, sessionmaker, tone
):
    """A worker saving a transcript and a member replacing the recording with text take
    their locks in the same order, so one waits for the other."""
    await sign_up(client)
    story_id = await story_with_audio(client, tone)
    async with sessionmaker() as worker:
        row = await worker.get(PipelineStep, (uuid.UUID(story_id), "transcribe"))
        payload = (await worker.get(Job, row.job_id)).payload
        # The worker has its transcript and is about to save it.
        assert await pipeline.is_current(worker, payload, lock=True)
        request = asyncio.create_task(put_text(client, story_id, TEXT))
        await asyncio.sleep(0.5)  # the member's request reaches the story's locks
        await pipeline._save_layer(
            worker, uuid.UUID(story_id), "verbatim", "jordanian", [
                {"start_ms": 0, "end_ms": 1000, "text": "from the recording"}
            ],
        )  # fmt: skip
        await worker.commit()
    r = await asyncio.wait_for(request, timeout=10)
    assert r.status_code == 200, r.text
    verbatim = layers_by_kind(r.json())["verbatim"]
    assert [s["text"] for s in verbatim["segments"]] == TEXT_LINES  # the newer source wins


# --- rules ---


async def test_text_needs_a_language_and_some_words_within_the_limit(client, monkeypatch):
    await sign_up(client)
    no_language = await new_story(client, language=None)
    r = await put_text(client, no_language, TEXT)
    assert r.status_code == 422
    assert "language" in r.json()["detail"]

    story_id = await new_story(client)
    r = await put_text(client, story_id, " \n\t ")
    assert r.status_code == 422
    assert "Write or paste" in r.json()["detail"]

    monkeypatch.setattr(get_settings(), "max_story_text_chars", 10)
    r = await put_text(client, story_id, "This is longer than ten characters.")
    assert r.status_code == 422
    assert "10 characters" in r.json()["detail"]
    limits = (await client.get("/api/v1/stories/limits")).json()
    assert limits["text_max_chars"] == 10


async def test_only_the_author_sets_the_text_and_only_while_editable(client, sessionmaker):
    await sign_up(client, "other@example.com")
    other = await new_story(client)
    await sign_up(client)
    assert (await put_text(client, other, TEXT)).status_code == 404

    story_id = await new_story(client)
    await client.patch(
        f"/api/v1/stories/{story_id}",
        json={"title": "T", "category": "folklore", "place_name": "Petra",
              "latitude": 30.3, "longitude": 35.4},
    )  # fmt: skip
    await put_text(client, story_id, TEXT)
    await drain(sessionmaker)
    assert (await client.post(f"/api/v1/stories/{story_id}/submit", json=CONSENT)).is_success
    assert (await put_text(client, story_id, TEXT)).status_code == 409


# --- publishing ---


async def test_a_text_story_is_published_and_narrated(client, sessionmaker):
    await sign_up(client)
    story_id = await new_story(client)
    await client.patch(
        f"/api/v1/stories/{story_id}",
        json={"title": "T", "category": "folklore", "place_name": "Petra",
              "latitude": 30.3, "longitude": 35.4},
    )  # fmt: skip
    r = await client.post(f"/api/v1/stories/{story_id}/submit", json=CONSENT)
    assert r.status_code == 422
    assert "recording or text" in r.json()["detail"]

    await put_text(client, story_id, TEXT)
    await drain(sessionmaker)
    r = await client.post(f"/api/v1/stories/{story_id}/submit", json=CONSENT)
    assert r.status_code == 200, r.text
    await drain(sessionmaker)  # moderation publishes it; the fake voice narrates it

    client.cookies.clear()
    public = await get_story(client, story_id)
    assert public["status"] == "published"
    assert public["audio"] is None
    assert public["narration"] is not None
    assert len(public["narration"]["segments"]) == len(TEXT_LINES)
