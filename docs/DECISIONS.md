# Hikaya: decisions and scope

Last updated 2026-10-22. This file is the source of truth for what we are building and why. When a decision changes, change it here first.

## Goal

A one-off, fully working demo for a judging panel. It runs on one laptop with Docker Compose. It is not a launch and it does not need to scale. Anything that only matters at scale is out of scope.

## Product decisions

**Two-tier publishing.**
- A member records or uploads a story. The AI pipeline runs, then automated moderation, then the story is published to the feed and the map.
- Staff approval is only needed for the AI museum (the curated collection).

**Moderation.**
- The language model attaches simple labels: `hate`, `violence`, `sexual`, `other_terrible`. No Azure Content Safety.
- Any label puts the story in status `held` ("under review"). It is not published.
- Staff review the story on one page with a check button and an X button.
  - Check means the label was wrong: the story is approved and published.
  - X means the label was right: the story stays unpublished and the author is asked to edit. The author can edit and resubmit.

**AI museum.** A virtual museum of curated stories. It is a product section, not a separate system: a "Curated" badge on stories, a "Museum" filter chip on Explore, and a featured row on Home. Staff pressing the check button on a candidate adds it.

**Plan flag.** Accounts have a plan (`free` or `premium`). Premium unlocks the AI video. There is a dummy payment page. There is no payment processor.

**Voice.**
- The original audio is always available.
- Narration defaults to a Jordanian-accented Arabic voice. Modern Standard Arabic narration is a later option.
- Staff can clone the voice of a consenting person (team members, or storytellers who opt in). The person sees a consent pop-up, records a 30 to 60 second sample inside the app, and we store the consent record (who, when, wording) with the clone. Cloning is staff-only.

**Animation.** The default is a pan-and-zoom slideshow rendered with FFmpeg. AI video is a premium feature. One or two sample AI videos are pre-made for the demo, and staff can generate more on any story, behind a flag and the spending cap.

## Real and mock

| Real in the demo | Mock in the demo |
| --- | --- |
| Record or upload audio | Like, save, share, comment |
| Transcription, polishing, translation | Follow |
| Jordanian-accent narration | Notifications |
| Slideshow video | Profile and settings editing |
| Map pin, publish to feed and map | Payments (dummy page) |
| Moderation labels and the staff review page | |
| Staff voice cloning | |
| Search and "Explore near me" | |
| Sign-in with seeded accounts | |

Mock means the screen works and shows plausible data but nothing is stored. Mock features can become real later.

## Languages

Content: Jordanian dialect, Modern Standard Arabic (MSA), English. The interface is English for now, built with translation files and right-to-left support so Arabic can be added without a rewrite. Arabic story text displays right-to-left from day one.

Each story keeps three text layers: the verbatim transcript, a lightly polished version in the same language, and translations into English and MSA. Translation targets are never dialect. Narration reads the polished text; if the dialect wording sounds wrong, it falls back to MSA text read by a Jordanian-accent voice.

## AI providers

Every provider sits behind one interface. A setting picks the provider per step, so any of them can be swapped.

| Step | Default | Fallback or alternative |
| --- | --- | --- |
| Speech to text | ElevenLabs Scribe | Azure Speech `ar-JO` |
| Polish, translate, label | Azure (a GPT-class model in Azure AI Foundry) | none planned |
| Narration | ElevenLabs | Azure `ar-JO` neural voices (SanaNeural, TaimNeural) |
| Voice cloning | ElevenLabs instant voice cloning | none |
| Image to video | fal.ai (model chosen after a roughly 1 USD bake-off) | Higgsfield API, Gemini API Veo, any open-source model endpoint |

OmniVoice (open-source text to speech) is not planned for the build. Its weights are non-commercial and it has no Jordanian dialect data. It may be added as an off-by-default test provider after a listening test. See `docs/research/omnivoice.md`.

Research with sources and prices: `docs/research/`.

## Budget and spending safety

- A total of about 25 USD of card-paid spending for the whole test: ElevenLabs, video, and anything else outside Azure. Azure has its own separate budget.
- The code keeps a spending ledger. It reserves the estimated cost before every paid call and refuses the call when a cap would be exceeded. The caps are settings.
- Every STT, language-model and TTS result is cached by a hash of its input, so repeated runs cost nothing.
- Every provider call goes through one gateway (`api/app/gateway.py`). In order: a cached result for the same operation, provider and input is returned at once (no cost, no call, whatever the live switch says); a free provider just runs; a paid provider needs `LIVE_AI_ENABLED=true` and a reservation that fits the caps, which is committed after the call or released if it fails. Refused calls are kept in the ledger as released rows, so attempts stay visible.
- Caps: `SPEND_CAP_USD_TOTAL` and `SPEND_CAP_USD_DAILY` for the card budget, `SPEND_CAP_USD_AZURE` for Azure. The ledger records the estimate as the cost, because providers do not report a bill per call.
- Demo pack: run the demo stories once with live AI on, then `python -m app.demo_pack export`; on the demo laptop, `python -m app.demo_pack import`. The pack lives in `demo-pack/`, which is git-ignored because it can contain recordings.
- Live AI calls are off by default during the demo. The demo stories use pre-generated outputs. A toggle turns live AI on.
- API keys live only in `.env`, which is never committed. This repository is public.

## Infrastructure

Docker Compose with four containers: `db` (plain PostgreSQL 16), `api` (FastAPI), `worker` (polls a job table in Postgres), `web` (the React app).

Not used: PostGIS, Redis, Celery, MinIO. Map pins need only latitude and longitude, "nearby" uses a distance formula in SQL, media is stored on local disk behind a storage interface, and background jobs use Postgres row locking. If any of these are ever needed, the interfaces let them slot in.

## Sign-in

Email and password. Sign-up creates a `member` with no email verification. Roles are `member`, `reviewer` and `admin`; sign-up can never choose one.

- The browser keeps an httpOnly, SameSite=Lax cookie holding a random token. The database stores only the token's hash, so sign-out and expiry end the session at once (7 days by default).
- Passwords are hashed with scrypt (standard library, no extra dependency).
- Staff accounts are created when the API starts, from `SEED_ADMIN_*` and `SEED_REVIEWER_*` in `.env`. An existing account keeps its password.
- Known limits, accepted for a local demo: no login rate limit, no password reset, and sign-up says when an email is already taken. No TOTP and no Google sign-in yet.

## Temporary differences from the plan

These exist on purpose while the build is in progress. Each closes with the ticket named.

- Transcription, polishing, translation and narration use fake providers by default; the real ones arrive with #12, #13 and #14, and the defaults then return to ElevenLabs and Azure as above.

## Demo data

- `python -m app.seed_demo` (run on every API start; `SEED_DEMO_DATA=false` turns it off) loads six places with their photo galleries, seven storytellers and seven published stories. Rows have fixed keys, so a re-run refreshes them instead of adding copies.
- Storyteller accounts cannot sign in. Seeded stories have text in every version but no recording yet; a recording can be added with the demo pack (#8).
- Publication dates are set relative to the day the seed runs, so "recently added" pins stay recent for the demo.
- The Arabic lines of the seed stories are placeholders for a native speaker to review. The place photos are not cleared for licensing, and one carries a stock watermark (see `api/seed/places/README.md`).
- Map pins: a story in the museum is "featured", one published in the last 14 days is "recent", any other is "ordinary".
- Likes, saves, comments, reflections, follows, notifications, the visit planner and profile editing stay mock. They live in the browser only, in `web/src/demo/mockEngagement.ts`, and nothing is stored.

## Moderation

- Submitting moves a story to `moderating` and queues the check as a pipeline step, so a failure shows in its progress and can be retried. The language model labels the polished text and the English translation for `hate`, `violence`, `sexual` and `other_terrible`, each with a short reason.
- No raised label publishes the story at once; any raised label puts it in `held`. Every check is stored with its labels and the exact text it judged. Submitting waits until the latest English translation has finished, so an older translation is never judged, and every submission is checked, even when the text has not changed. A staff decision made while a check runs is never overwritten.
- Staff send a story back with a note (`needs_edit`, #11); the author edits and resubmits, which runs the check again. Held and needs-edit stories are visible only to the author and staff, and moderation details are never shown to anyone else.
- "My stories" lists every story of the member with its status, why it was held, and the reviewer's note. The author can delete a story in any status; its rows, queued jobs and files are removed.
- The fake language model raises labels on marker words (for example "kill" for violence, "hateful" for hate), so rehearsals and tests are predictable.

## Creating a story

- Recording uses the browser's own recorder (WebM/Opus, Ogg/Opus or MP4/AAC, whichever the browser supports) and the page names the real format. Blocked, missing, busy or unsupported microphones each get a plain message, and uploading a file always remains possible.
- Photos are optional: uploads (PNG, JPEG or WebP, up to 15 MB and 40 megapixels each, read by their content) are stored as WebP at three widths; members can also pick photos from a place gallery. Up to 12 photos, in an order the member sets; the first is the cover. Removing a gallery pick never deletes the shared place photo. The page reads the limits from the API, so they are set in one place.
- The pin is set by clicking the map; typing a known place drops a starting pin there. The place name is free text.
- Publishing needs agreement to the rights statement served by the API. The statement has a version; the story stores the version agreed to and when. Changing the wording means a new version.

## Media

- Every upload is kept untouched. Playback uses a constant-bitrate mono MP3 copy of the same recording, because every browser (including open-source Chromium, which has no AAC) plays MP3 and every speech provider accepts it.
- Place photos are served as WebP at 480, 960 and 1600 pixels wide; pages pick a size with `srcset`.
- FFmpeg reads each upload with the demuxer for its declared type and only the `file` protocol, so it never guesses a format from the content.

## Narration and slideshow

- Narration starts when the member submits, alongside the moderation check, so reviewers hear held stories too and no voice credit goes on drafts. (The spec said "once the text is ready"; changed on 2026-10-23 with the owner's agreement.) The story is published without waiting for either; the player shows what exists, and the author and staff see their progress there, with a retry for a failed one in any status.
- The narration reads the polished text by default, or the MSA translation if the member chooses it on the last step of Create Story. For an MSA story the polished text already is MSA. Arabic text is read by a Jordanian-accent voice, as above.
- Narration timings come from the voice provider's alignment data when it offers them (the whole text in one call). Otherwise each line is spoken on its own, measured and joined. Each narration records its provider, voice, language, source, the text of each line, and how its timings were made.
- Every spoken piece is cached as a file by a hash of its input, so the same text is never paid for twice, and the demo pack carries the files. A narration copies its file, so deleting a story never removes a cached result. Files are written whole (to a partial name, then moved), so a half-written file is never served.
- The slideshow carries the narration, as the product spec says ("moves slowly over the narration"), so it is made once the narration is ready and lasts as long as it. It is a 1280×720 H.264 and AAC MP4 at 25 frames a second: each photo holds for an equal share with a slow zoom or pan and a short fade. It uses the story's photos in order, or its place photo when it has none, and is skipped when there is no picture at all. A missing photo fails the step rather than quietly leaving the photo out.
- Resubmitting re-runs only what changed: narration when the text it reads or the source choice changed, the slideshow when the narration or the photos changed. Text is edited only while a story is a draft or sent back, so an edit takes effect on the next submission.
- The player switches between the storyteller's recording and the narration, continuing at the same line, and highlights lines with the timings of whichever is playing, the slideshow included. The open-source Chromium used in CI cannot decode H.264, so the browser test checks that the slideshow is on the page and served, and the API tests check that the file itself decodes.
- The seeded demo stories are text only, so they have no narration or slideshow yet.

## Text pipeline

- The member chooses the spoken language before uploading. Transcription starts as soon as the recording is uploaded; polishing follows, then the translations, each as its own job.
- Each step records a hash of its input. A new recording or a new language starts over from transcription and clears the old text. Editing the original words re-runs polishing and the translations; editing the polished text re-runs only the translations; editing a translation re-runs nothing. Re-running a later version replaces edits made to it, and the editor says so. A version cannot be edited while it is being remade. A result made from outdated input is dropped, and an input that returns to an earlier value runs again.
- Publishing needs the original words, the polished text and, for an Arabic story, the English translation (moderation reads it). The MSA translation may still be running, unless the narration reads it.
- Failed steps show a plain message; unexpected errors never show their internal detail. A failed step can be retried from the Transcript step.

## Defaults I assumed (confirm or change)

- Story creation is real (record or upload, AI steps, publish). Only the social interactions and the AI video samples are mock.
- The demo plays pre-generated AI outputs, and live AI is a toggle that is off by default.
- Transcription defaults to ElevenLabs Scribe, with Azure as the fallback. Three short test clips (Jordanian dialect, MSA, English) can flip the default.
- The default narrator voice is chosen by a short listening test between a Jordanian-tagged ElevenLabs voice, a clone of a consenting Jordanian team member, and Azure `ar-JO`.

## Out of scope

AI persona chat, reels, the 360 viewer, analytics dashboards, the visit planner (no document defines it), real payments, Google sign-in, TOTP, email verification, scaling.
