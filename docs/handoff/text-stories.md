# Handoff: stories written as text

Status on 2026-11-12: designed, decision recorded, failing tests written. No application code yet.
Read `CLAUDE.md` and the "Stories written as text" section of `docs/DECISIONS.md` first; that
section is the spec. Delete this file and the matching line under "Temporary differences from the
plan" in `docs/DECISIONS.md` when the feature is done.

## Goal

A member can write or paste a story, or load a `.txt` file into a text box, instead of recording
it. The text becomes the story's original words (the `verbatim` layer); transcription is skipped;
polishing, translations, moderation, narration and the slideshow then run as for a recording.

## Where the work is

- Branch `claude/text-stories`, cut from `claude/hopeful-pasteur-nglswr` at `f01ec8d` (the Gemini
  Omni work, not merged into `main` yet). Build on this branch, not on `main`.
- Done: `docs/DECISIONS.md` (bullet under "Creating a story", new section at the end, and a line under
  "Temporary differences from the plan"), `api/tests/test_text_stories.py` (new), and
  `api/tests/test_stories.py`: the "missing" list now expects `"recording or text"` instead of `"audio"`.
- The tests have **not been run yet** (Docker stopped on the machine they were written on).
  Run them first: they should fail with an ImportError on `lines_from_text`. Then implement until
  they pass.

## Backend, step by step

`api/app/pipeline.py`
1. `lines_from_text(text: str) -> list[str]`. For each paragraph in `text.splitlines()`, take
   sentences with `re.compile(r".+?(?:[.!?؟…]+[\"'”’»)\]]*(?=\s|$)|$)")` (a stop only counts when
   whitespace or the end follows, so `3.5` stays whole and a closing quote stays on its sentence),
   strip each, drop empties, and split any line over `MAX_LINE_CHARS = 300` at the last space before
   the limit (hard cut if there is no space). The tests pin the exact output.
2. `_estimated_segments(lines)`: consecutive slots, `max(1500, round(len(line) * 1000 / 15))` ms
   each, starting at 0. Starts must be distinct: `TranscriptEditor.tsx` keys lines by `start_ms`.
3. `start_from_text(session, story, lines)`: delete the story's `TextLayer` and `PipelineStep` rows
   (as `start()` does), add the `verbatim` layer with `language=story.original_language` and the
   estimated segments, `flush`, `_queue_polish`, `commit`.
4. `start()`: today it returns when there is no audio. Instead, when there is no audio, a `verbatim`
   layer exists, there is no `transcribe` step row, `story.original_language` is set and differs from
   the layer's language, call `start_from_text` with the layer's current texts (edits kept). This is
   what makes a language change re-polish a written story (`PATCH /stories/{id}` already calls `start`).
5. `status()`: today `if "transcribe" not in rows: return [], False`. A written story has a `polish`
   row and no `transcribe` row: then report `expected_steps(language)` without `"transcribe"`.
   No rows at all still returns `[], False`.
   Editing the `verbatim` layer already works for written stories (`edit_layer` finds no transcribe
   job, so nothing is busy) and re-queues polishing; a test covers it.

`api/app/stories.py`
6. `PUT /stories/{story_id}/text`, JSON body `{"text": str}` (pydantic `max_length=200_000` as a hard
   bound). In order: `_own_story` (404 for others), `_require_editable` (409), language set or 422
   `"Choose the language of the story first."`, length over `settings.max_story_text_chars` gives 422
   `f"Stories can be up to {limit:,} characters long."`, no lines gives 422
   `"Write or paste the story first."`. Then lock the story (`session.refresh(story, with_for_update=True)`),
   delete its audio `Asset` rows (`_audio_assets`), set `story.duration_ms = None`,
   `await pipeline.start_from_text(...)` (commits), and only then delete the old audio files from
   storage, as `upload_audio` does. Return `to_out(..., private=True, viewer=user)`.
7. `missing_for_publishing`: rename `has_audio` to `has_source`, label `"recording or text"`; the
   caller passes `bool(audio assets) or pipeline.VERBATIM in kinds`.
8. `UploadLimits` and `GET /stories/limits`: add `text_max_chars`.

`api/app/config.py` and `.env.example`
9. `max_story_text_chars: int = Field(20_000, ge=100, le=200_000)` next to the other upload limits;
   `MAX_STORY_TEXT_CHARS=20000` under "Limits and timings" in `.env.example`.

No migration is needed: no schema change.

## Frontend, step by step

10. `web/src/stories.ts`: `setStoryText(id, text)` calling
    `api<StoryRecord>(`/stories/${id}/text`, { method: 'PUT', body: { text } })`; add
    `text_max_chars` to `UploadLimits`.
11. `web/src/pages/CreateStoryPage.tsx`, step 1, below the "Or upload a recording" box: a
    "Write or paste your story" box with a `textarea` (direction and font from `textDirection` /
    `textFont` for the chosen language, a character count against `limits.text_max_chars`), a
    "Load a .txt file" button (hidden `input type="file" accept=".txt,text/plain"`, then
    `await file.text()` into the textarea so the member sees it before saving), and a
    "Use this text" button that calls `ensureDraft()` then `setStoryText` and `setDraft`. Disabled
    until a language is chosen. When the draft has a recording, say that using the text replaces it
    (and the upload box should say a recording replaces the text).
    `canContinue` for step 1: `!!draft?.audio || !!draft?.layers.some((l) => l.kind === 'verbatim')`.
    Resuming (`/create?story=<id>`): go to step 2 for a written story too (no audio, has `verbatim`).
    The language label "Language you speak in the recording" should cover text as well.
12. `web/src/components/TranscriptEditor.tsx`: when the story has no recording (`!story?.audio`),
    show the line number instead of `timestamp(seg.start_ms)`; the estimated times mean nothing.
13. Every new `t()` string needs an entry in `web/src/locales/keys.json` (English text to
    `common.snake_case` key) and in both `en.json` and `ar.json`; `i18n.test.tsx` fails if `en` and
    `ar` keys differ. Write real Arabic.

## Gotchas

- Rule 2: no provider call inside the request. The endpoint only stores text and queues the polish job.
- Tests must run on the fake providers. Do not load a real `.env` into the test process: it may set
  `LIVE_AI_ENABLED=true` and real providers. `api/tests/conftest.py` takes `TEST_DATABASE_URL`
  (default `postgresql+asyncpg://hikaya:hikaya@localhost:5432/hikaya_test`) and migrates it down and up.
- `test_a_text_story_is_published_and_narrated` expects the fake voice to narrate on submit, with
  one narration line per text line. If narration needs something a written story lacks, fix the code,
  not the test, unless `docs/DECISIONS.md` says otherwise.
- Uploading a recording after text already starts over: `start()` sees no `transcribe` row, deletes
  the layers and queues transcription. A test checks this; no change should be needed.

## Done when

- `cd api && pytest` passes in full, and `ruff check . && ruff format --check .` are clean.
- `cd web && npm run typecheck && npm run lint && npm run format:check && npm test && npm run build` pass.
- With the fake providers (`docker compose up --build`): paste Arabic text with `؟` into a new story,
  see the lines and the polished text and translations, publish it, and hear the narration; load a
  `.txt` file into the box; replace a recording with text and text with a recording.
- This file and its line in `docs/DECISIONS.md` are removed, and the "Stories written as text"
  section says what was verified.
