"""The AI pipeline, driven through the API and the worker with fake providers."""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text, update

from app.models import Job
from app.providers import fake
from app.worker import run_one

PASSWORD = "correct horse battery"


@pytest.fixture(scope="session")
def tones(tmp_path_factory) -> dict[str, Path]:
    """Two different real recordings: 10 s and 6 s."""
    folder = tmp_path_factory.mktemp("pipeline-audio")
    out = {}
    for name, seconds, freq in (("long", 10, 440), ("short", 6, 330)):
        path = folder / f"{name}.wav"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi",
             "-i", f"sine=frequency={freq}:duration={seconds}", "-ac", "1", str(path)],
            check=True,
        )  # fmt: skip
        out[name] = path
    return out


@pytest.fixture(autouse=True)
def fresh_fakes():
    fake.reset()
    yield
    fake.reset()


async def drain(sessionmaker, *, ignore_backoff=True) -> int:
    """Run the worker until nothing is due. Backed-off retries are made due at once."""
    ran = 0
    while True:
        if ignore_backoff:
            async with sessionmaker() as s:
                await s.execute(
                    update(Job).where(Job.status == "queued").values(run_after=text("now()"))
                )
                await s.commit()
        if not await run_one(sessionmaker):
            return ran
        ran += 1


async def sign_up(client, email="salma@example.com"):
    client.cookies.clear()
    r = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "display_name": "Salma"},
    )
    assert r.status_code == 201
    return client.cookies.get("hikaya_session")


async def story_with_audio(client, path, language="jordanian"):
    fields = {"original_language": language} if language else {}
    story = (await client.post("/api/v1/stories", json=fields)).json()
    with open(path, "rb") as f:
        r = await client.put(
            f"/api/v1/stories/{story['id']}/audio", files={"file": (path.name, f, "audio/wav")}
        )
    assert r.status_code == 200, r.text
    return story["id"]


async def get_story(client, story_id):
    r = await client.get(f"/api/v1/stories/{story_id}")
    assert r.status_code == 200
    return r.json()


def layers_by_kind(story):
    return {layer["kind"]: layer for layer in story["layers"]}


async def status(client, story_id):
    r = await client.get(f"/api/v1/stories/{story_id}/pipeline")
    assert r.status_code == 200, r.text
    return {s["step"]: s for s in r.json()["steps"]}, r.json()


# --- the chain ---


async def test_upload_runs_transcribe_polish_and_both_translations(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["long"])

    steps, body = await status(client, story_id)
    assert steps["transcribe"]["status"] == "queued"
    assert body["complete"] is False

    await drain(sessionmaker)
    steps, body = await status(client, story_id)
    assert {k: v["status"] for k, v in steps.items()} == {
        "transcribe": "done",
        "polish": "done",
        "translate_en": "done",
        "translate_msa": "done",
    }
    assert body["complete"] is True

    layers = layers_by_kind(await get_story(client, story_id))
    assert set(layers) == {"verbatim", "polished", "translation_en", "translation_msa"}
    verbatim = layers["verbatim"]["segments"]
    assert len(verbatim) >= 2
    assert verbatim[-1]["end_ms"] <= 10_500
    for kind in ("polished", "translation_en", "translation_msa"):
        segments = layers[kind]["segments"]
        assert [(s["start_ms"], s["end_ms"]) for s in segments] == [
            (s["start_ms"], s["end_ms"]) for s in verbatim
        ]
        assert all(s["text"] for s in segments)
    assert layers["verbatim"]["language"] == "jordanian"
    assert layers["translation_en"]["language"] == "english"
    assert layers["translation_msa"]["language"] == "msa"
    # The fake English translation is real English, not a copy of the Arabic.
    assert layers["translation_en"]["segments"][0]["text"].isascii()


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("english", {"verbatim", "polished", "translation_msa"}),
        ("msa", {"verbatim", "polished", "translation_en"}),
    ],
)
async def test_translation_into_the_original_language_is_skipped(
    client, sessionmaker, tones, language, expected
):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"], language=language)
    await drain(sessionmaker)
    assert set(layers_by_kind(await get_story(client, story_id))) == expected
    steps, body = await status(client, story_id)
    assert body["complete"] is True
    assert len(steps) == len(expected)


async def test_unknown_language_is_detected_by_transcription(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"], language=None)
    await drain(sessionmaker)
    story = await get_story(client, story_id)
    assert story["original_language"] == "jordanian"
    assert "translation_msa" in layers_by_kind(story)


# --- idempotency ---


async def test_each_input_is_processed_once(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["long"])
    await drain(sessionmaker)
    calls_after_first = list(fake.CALLS)

    # The same recording again changes nothing and runs nothing.
    with open(tones["long"], "rb") as f:
        await client.put(
            f"/api/v1/stories/{story_id}/audio", files={"file": ("again.wav", f, "audio/wav")}
        )
    assert await drain(sessionmaker) == 0
    assert fake.CALLS == calls_after_first
    assert [c[0] for c in calls_after_first].count("transcribe") == 1
    assert [c[0] for c in calls_after_first].count("polish") == 1


async def test_a_new_recording_starts_over(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["long"])
    await drain(sessionmaker)
    before = layers_by_kind(await get_story(client, story_id))["verbatim"]["segments"]

    with open(tones["short"], "rb") as f:
        await client.put(
            f"/api/v1/stories/{story_id}/audio", files={"file": ("short.wav", f, "audio/wav")}
        )
    story = await get_story(client, story_id)
    assert story["layers"] == []  # old text never shows against the new recording
    await drain(sessionmaker)
    after = layers_by_kind(await get_story(client, story_id))["verbatim"]["segments"]
    assert len(after) < len(before)


async def test_changing_the_language_reruns_the_pipeline(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"], language="jordanian")
    await drain(sessionmaker)
    await client.patch(f"/api/v1/stories/{story_id}", json={"original_language": "english"})
    await drain(sessionmaker)
    layers = layers_by_kind(await get_story(client, story_id))
    assert set(layers) == {"verbatim", "polished", "translation_msa"}
    assert layers["verbatim"]["language"] == "english"
    assert layers["verbatim"]["segments"][0]["text"].isascii()


# --- failure and retry ---


async def test_a_failing_step_retries_then_reports_a_plain_message(
    client, sessionmaker, tones, monkeypatch
):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    fake.FAIL_ON.add("polish")
    await drain(sessionmaker)

    steps, body = await status(client, story_id)
    assert steps["transcribe"]["status"] == "done"
    assert steps["polish"]["status"] == "failed"
    assert steps["polish"]["message"] == "The language model is unavailable right now."
    # Steps that never started say so, instead of looking queued forever.
    assert steps["translate_en"]["status"] == "waiting"
    assert body["complete"] is False
    assert [c[0] for c in fake.CALLS].count("polish") == 3  # max attempts

    fake.FAIL_ON.clear()
    r = await client.post(f"/api/v1/stories/{story_id}/pipeline/polish/retry")
    assert r.status_code == 200
    await drain(sessionmaker)
    steps, body = await status(client, story_id)
    assert body["complete"] is True


async def test_unexpected_errors_do_not_leak_details(client, sessionmaker, tones, monkeypatch):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])

    async def broken(*_args, **_kwargs):
        raise RuntimeError("secret internal detail at /srv/keys")

    monkeypatch.setattr(fake.FakeSpeechToText, "transcribe", broken)
    await drain(sessionmaker)
    steps, _ = await status(client, story_id)
    assert steps["transcribe"]["status"] == "failed"
    assert "secret" not in steps["transcribe"]["message"]
    assert steps["transcribe"]["message"] == "Something went wrong in this step. Try again."


async def test_retry_is_only_for_failed_steps(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    path = f"/api/v1/stories/{story_id}/pipeline"
    assert (await client.post(f"{path}/transcribe/retry")).status_code == 409
    await drain(sessionmaker)
    assert (await client.post(f"{path}/polish/retry")).status_code == 409
    assert (await client.post(f"{path}/nonsense/retry")).status_code == 404


async def test_misaligned_provider_output_fails_the_step(client, sessionmaker, tones, monkeypatch):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["long"])

    async def drops_a_line(self, texts, language):
        return texts[:-1]

    monkeypatch.setattr(fake.FakeLanguageModel, "polish", drops_a_line)
    await drain(sessionmaker)
    steps, _ = await status(client, story_id)
    assert steps["polish"]["status"] == "failed"
    assert "line" in steps["polish"]["message"]


# --- editing ---


async def test_editing_the_transcript_reruns_what_depends_on_it(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    await drain(sessionmaker)
    verbatim = layers_by_kind(await get_story(client, story_id))["verbatim"]["segments"]
    texts = [s["text"] for s in verbatim]
    texts[0] = "كان جدي يشعل الفانوس كل مسا"

    r = await client.patch(f"/api/v1/stories/{story_id}/layers/verbatim", json={"texts": texts})
    assert r.status_code == 200, r.text
    steps, _ = await status(client, story_id)
    assert steps["polish"]["status"] == "queued"

    await drain(sessionmaker)
    layers = layers_by_kind(await get_story(client, story_id))
    assert layers["verbatim"]["edited"] is True
    assert layers["verbatim"]["segments"][0]["text"] == texts[0]
    assert layers["polished"]["segments"][0]["text"].startswith(texts[0])
    # Timestamps never move when text is edited.
    assert [s["start_ms"] for s in layers["verbatim"]["segments"]] == [
        s["start_ms"] for s in verbatim
    ]


async def test_editing_the_polished_text_reruns_only_translations(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    await drain(sessionmaker)
    polished = layers_by_kind(await get_story(client, story_id))["polished"]["segments"]
    texts = [s["text"] for s in polished]
    texts[0] = "نص منقح جديد."
    fake.CALLS.clear()
    r = await client.patch(f"/api/v1/stories/{story_id}/layers/polished", json={"texts": texts})
    assert r.status_code == 200
    await drain(sessionmaker)
    kinds = [c[0] for c in fake.CALLS]
    assert "transcribe" not in kinds and "polish" not in kinds
    assert kinds.count("translate") == 2
    layers = layers_by_kind(await get_story(client, story_id))
    assert layers["polished"]["segments"][0]["text"] == "نص منقح جديد."


async def test_editing_a_translation_is_kept_and_runs_nothing(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    await drain(sessionmaker)
    layer = layers_by_kind(await get_story(client, story_id))["translation_en"]
    texts = [s["text"] for s in layer["segments"]]
    texts[0] = "My grandfather lit the lantern every evening."
    await client.patch(f"/api/v1/stories/{story_id}/layers/translation_en", json={"texts": texts})
    assert await drain(sessionmaker) == 0
    saved = layers_by_kind(await get_story(client, story_id))["translation_en"]
    assert saved["segments"][0]["text"] == texts[0]
    assert saved["edited"] is True


async def test_a_stale_result_never_overwrites_newer_text(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    assert await run_one(sessionmaker)  # transcribe only; the first polish is now queued
    verbatim = layers_by_kind(await get_story(client, story_id))["verbatim"]["segments"]
    texts = [s["text"] for s in verbatim]
    texts[0] = "نسخة معدلة من السطر الأول"
    await client.patch(f"/api/v1/stories/{story_id}/layers/verbatim", json={"texts": texts})
    await drain(sessionmaker)  # the old polish job runs first and must be discarded
    polished = layers_by_kind(await get_story(client, story_id))["polished"]["segments"]
    assert polished[0]["text"].startswith("نسخة معدلة")


@pytest.mark.parametrize(
    "texts_for",
    [
        lambda texts: texts[:-1],
        lambda texts: texts + ["extra"],
        lambda texts: ["x" * 2001] + texts[1:],
    ],
)
async def test_edits_must_keep_one_text_per_line(client, sessionmaker, tones, texts_for):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    await drain(sessionmaker)
    layer = layers_by_kind(await get_story(client, story_id))["verbatim"]
    texts = texts_for([s["text"] for s in layer["segments"]])
    r = await client.patch(f"/api/v1/stories/{story_id}/layers/verbatim", json={"texts": texts})
    assert r.status_code == 422


async def test_only_the_author_edits_and_retries(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    await drain(sessionmaker)
    texts = [
        s["text"] for s in layers_by_kind(await get_story(client, story_id))["verbatim"]["segments"]
    ]
    await sign_up(client, "other@example.com")
    path = f"/api/v1/stories/{story_id}"
    assert (await client.patch(f"{path}/layers/verbatim", json={"texts": texts})).status_code == 404
    assert (await client.get(f"{path}/pipeline")).status_code == 404
    assert (await client.post(f"{path}/pipeline/transcribe/retry")).status_code == 404
    client.cookies.clear()
    assert (await client.get(f"{path}/pipeline")).status_code == 404


async def test_unknown_layer_is_404(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    r = await client.patch(f"/api/v1/stories/{story_id}/layers/translation_fr", json={"texts": []})
    assert r.status_code == 404
    # A layer that exists for the language but has not been made yet.
    r = await client.patch(f"/api/v1/stories/{story_id}/layers/polished", json={"texts": []})
    assert r.status_code == 409


# --- publishing ---


async def test_publishing_waits_for_the_transcript(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    await client.patch(
        f"/api/v1/stories/{story_id}",
        json={"title": "T", "category": "folklore", "place_name": "Madaba",
              "latitude": 31.7, "longitude": 35.8},
    )  # fmt: skip
    r = await client.post(f"/api/v1/stories/{story_id}/submit")
    assert r.status_code == 422
    assert "transcript" in r.json()["detail"]
    await drain(sessionmaker)
    r = await client.post(f"/api/v1/stories/{story_id}/submit")
    assert r.status_code == 200

    client.cookies.clear()
    public = await get_story(client, story_id)
    assert {layer["kind"] for layer in public["layers"]} == {
        "verbatim",
        "polished",
        "translation_en",
        "translation_msa",
    }
    # Pipeline progress is for the author and staff, not the public.
    assert (await client.get(f"/api/v1/stories/{story_id}/pipeline")).status_code == 404


async def test_going_back_to_an_earlier_text_runs_again(client, sessionmaker, tones):
    """Edit A -> B -> A: the polished text must follow A again, not stay on B."""
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    await drain(sessionmaker)
    original = [
        s["text"] for s in layers_by_kind(await get_story(client, story_id))["verbatim"]["segments"]
    ]
    edited = ["سطر معدل"] + original[1:]
    path = f"/api/v1/stories/{story_id}/layers/verbatim"
    await client.patch(path, json={"texts": edited})
    await drain(sessionmaker)
    await client.patch(path, json={"texts": original})
    await drain(sessionmaker)
    polished = layers_by_kind(await get_story(client, story_id))["polished"]["segments"]
    assert polished[0]["text"].startswith(original[0])


async def test_switching_language_back_brings_the_transcript_back(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"], language="jordanian")
    await drain(sessionmaker)
    for language in ("english", "jordanian"):
        await client.patch(f"/api/v1/stories/{story_id}", json={"original_language": language})
        await drain(sessionmaker)
    story = await get_story(client, story_id)
    assert set(layers_by_kind(story)) == {
        "verbatim",
        "polished",
        "translation_en",
        "translation_msa",
    }
    _, body = await status(client, story_id)
    assert body["complete"] is True


async def test_a_result_that_finishes_after_the_input_changed_is_dropped(
    client, sessionmaker, tones, monkeypatch
):
    """The input changes while the provider is still working on the old input."""
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    assert await run_one(sessionmaker)  # transcribe; polish is queued next
    verbatim = [
        s["text"] for s in layers_by_kind(await get_story(client, story_id))["verbatim"]["segments"]
    ]
    original_polish = fake.FakeLanguageModel.polish

    async def slow_polish(self, texts, language):
        # While the provider "works", the author edits the original words.
        await client.patch(
            f"/api/v1/stories/{story_id}/layers/verbatim",
            json={"texts": ["تعديل أثناء العمل"] + verbatim[1:]},
        )
        return await original_polish(self, texts, language)

    monkeypatch.setattr(fake.FakeLanguageModel, "polish", slow_polish)
    assert await run_one(sessionmaker)  # the old polish finishes late
    monkeypatch.setattr(fake.FakeLanguageModel, "polish", original_polish)
    assert "polished" not in layers_by_kind(await get_story(client, story_id))
    await drain(sessionmaker)
    polished = layers_by_kind(await get_story(client, story_id))["polished"]["segments"]
    assert polished[0]["text"].startswith("تعديل أثناء العمل")


async def test_a_version_cannot_be_edited_while_it_is_being_made(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    await drain(sessionmaker)
    layers = layers_by_kind(await get_story(client, story_id))
    texts = [s["text"] for s in layers["polished"]["segments"]]
    await client.patch(
        f"/api/v1/stories/{story_id}/layers/polished", json={"texts": ["تغيير."] + texts[1:]}
    )
    # The translations are now queued again, so they cannot be edited until they finish.
    en = [s["text"] for s in layers["translation_en"]["segments"]]
    r = await client.patch(f"/api/v1/stories/{story_id}/layers/translation_en", json={"texts": en})
    assert r.status_code == 409


async def test_steps_of_a_published_story_cannot_be_retried(client, sessionmaker, tones):
    await sign_up(client)
    story_id = await story_with_audio(client, tones["short"])
    fake.FAIL_ON.add("translate")
    await drain(sessionmaker)
    fake.FAIL_ON.clear()
    await client.patch(
        f"/api/v1/stories/{story_id}",
        json={"title": "T", "category": "folklore", "place_name": "Madaba",
              "latitude": 31.7, "longitude": 35.8},
    )  # fmt: skip
    assert (await client.post(f"/api/v1/stories/{story_id}/submit")).status_code == 200
    r = await client.post(f"/api/v1/stories/{story_id}/pipeline/translate_en/retry")
    assert r.status_code == 409
