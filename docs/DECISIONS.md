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

Content: Jordanian dialect, Modern Standard Arabic (MSA), English. The interface supports English and Arabic, with translation catalogues, a persisted language switch and document-level right-to-left layout. Story language stays independent of interface language. Arabic story text displays right-to-left from day one.

Each story keeps three text layers: the verbatim transcript, a lightly polished version in the same language, and translations into English and MSA. Translation targets are never dialect. Narration reads the polished text; if the dialect wording sounds wrong, it falls back to MSA text read by a Jordanian-accent voice.

## AI providers

Every provider sits behind one interface. A setting picks the provider per step, so any of them can be swapped.

| Step | Default | Fallback or alternative |
| --- | --- | --- |
| Speech to text | ElevenLabs Scribe | Azure Speech `ar-JO` |
| Polish, translate, label | Azure (a GPT-class model in Azure AI Foundry) | none planned |
| Narration | ElevenLabs | Azure `ar-JO` neural voices (SanaNeural, TaimNeural) |
| Voice cloning | ElevenLabs instant voice cloning | none |
| Image to video | fal.ai (model chosen after a roughly 1 USD bake-off) | Higgsfield API, Google Cloud Veo, Gemini Omni Flash (Gemini API key), any open-source model endpoint |

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
- Staff send a story back with a note (`needs_edit`); the author edits and resubmits, which runs the check again. Held and needs-edit stories are visible only to the author and staff, and moderation details are never shown to anyone else.
- "My stories" lists every story of the member with its status, why it was held, and the reviewer's note. The author can delete a story in any status; its rows, queued jobs and files are removed.
- The fake language model raises labels on marker words (for example "kill" for violence, "hateful" for hate), so rehearsals and tests are predictable.

## Staff review and the museum

- Reviewers and admins share one staff page: held stories (labels, reasons, the text judged, the recording and the narration) with Publish and Send back (an optional note the author sees), and museum candidates (published, not curated, not set aside) with Add to museum and Not now. Admins also remove stories from the museum and see the spend summary and the log of staff actions.
- Staff never act on their own stories; the page says so, and the API refuses it. Each action locks the story, so two staff cannot act on it at once, and writes an audit event (actor, action, target, time, and the note when there is one) in the same transaction. Audit events are kept when the story is deleted.
- "Not now" sets a candidate aside; the staff page does not offer it again (the API can still curate it, which clears that). Removing a story from the museum also sets it aside, so it does not come straight back as a candidate.
- The museum is curation, not a separate system: a Curated badge, a Museum chip on Explore, and the Home featured row, which shows only curated stories (and says so when there are none). The public feed takes `curated=true` and says how many stories match in total, so the Museum chip and the museum count are complete however many stories exist.
- The spend summary counts the ledger as the caps do: settled calls at their cost, calls in flight at their reservation, released reservations not at all. It shows the total, the card budget's spending today (what the daily cap counts), the card and Azure budgets against their limits, and each provider. The caps and the summary share one definition of what counts.

## Creating a story

- Recording uses the browser's own recorder (WebM/Opus, Ogg/Opus or MP4/AAC, whichever the browser supports) and the page names the real format. Blocked, missing, busy or unsupported microphones each get a plain message, and uploading a file always remains possible.
- Photos are optional: uploads (PNG, JPEG or WebP, up to 15 MB and 40 megapixels each, read by their content) are stored as WebP at three widths; members can also pick photos from a place gallery. Up to 12 photos, in an order the member sets; the first is the cover. Removing a gallery pick never deletes the shared place photo. The page reads the limits from the API, so they are set in one place.
- The pin is set by clicking the map; typing a known place drops a starting pin there. The place name is free text.
- Publishing needs agreement to the rights statement served by the API. The statement has a version; the story stores the version agreed to and when. Changing the wording means a new version.

## Media

- Every upload is kept untouched. Playback uses a constant-bitrate mono MP3 copy of the same recording, because every browser (including open-source Chromium, which has no AAC) plays MP3 and every speech provider accepts it.
- Place photos are served as WebP at 480, 960 and 1600 pixels wide; pages pick a size with `srcset`.
- FFmpeg reads each upload with the demuxer for its declared type and only the `file` protocol, so it never guesses a format from the content.

## Real providers

- Every provider stays on its fake until its keys are in `.env`, it is chosen by setting, and `LIVE_AI_ENABLED=true`. A missing key is reported by name when the provider is chosen, and nothing is called.
- `scripts/prepare-env.sh` writes a `.env` from `.env.example` ready for ElevenLabs: transcription, narration and voice cloning on ElevenLabs, live AI on (within the caps), and the two staff accounts with random passwords. It never overwrites an existing `.env`. The key and the two voice IDs are then filled in by hand. `.env.example` itself keeps the fakes and live AI off.
- A voice ID ElevenLabs does not know (malformed IDs get a 400 before the key is checked, unknown ones a 404) fails narration with the name of the setting that holds it, or says it is a cloned voice that may have been deleted there, instead of blaming the text.
- The Azure language model (`LLM_PROVIDER=azure`) uses the Azure OpenAI v1 API with Structured Outputs: the lines go and come back as a JSON array with exactly one line each, and any other count, malformed answer, refusal or cut-off answer fails the step with a plain message instead of being guessed at. Translation never targets a dialect. The ledger records the cost Azure reports (token usage at the configured price per million tokens); the reservation before the call is a deliberately high estimate.

- Transcription (`STT_PROVIDER`): ElevenLabs Scribe (`scribe_v2`, word timestamps, card budget) or Azure AI Speech fast transcription (`ar-JO` or `en-US`, phrase timestamps, Azure budget). Scribe's words are grouped into lines at sentence ends, pauses of 0.8 s and at most 12 s, so the player highlights readable lines; Azure's phrases are used as they come. With no language chosen, both detect it; detected Arabic is taken as Jordanian, the app's default, since neither tells a dialect from MSA. Audio events (laughter and the like) are left out. The cost is per audio hour.

- Narration voices (`TTS_PROVIDER`): ElevenLabs (card budget) returns a timing for every character, which becomes each line's start and end, so a whole story is spoken in one call, or in parts under the per-request character limit, timed across the parts. Azure neural voices (`ar-JO-SanaNeural` by default, Azure budget) give no timings over REST, so narration speaks them line by line and measures each piece. Lines meet end to end and a pause belongs to the line just spoken. Voices are settings: ElevenLabs voice IDs belong to the account, so they must be chosen before narration can run there. The cost is per character.

- Staff AI video: submitting is one job; checking on the video is a separate short job that asks the provider once and, while it is still rendering, queues the next check `VIDEO_POLL_SECONDS` later. The worker is never held while a provider renders, so stories keep moving through transcription and narration. A status check costs nothing and is neither charged nor cached; only the finished video is cached. Checks stop after `VIDEO_MAX_WAIT_SECONDS` (30 minutes by default) and the provider's request ID is kept for follow-up. A check that cannot reach the provider simply tries again next time.

## Search

- Search matches a story's title, place, storyteller and every text layer in two ways at once: as a substring (so part of a name works) and with PostgreSQL full-text search in the built-in Arabic and English configurations (so other word forms work: حكاية finds الحكايات, "story" finds "stories"). The full-text expressions have GIN indexes (migration 0015) and are written to match them exactly. Broken plurals (فوانيس for فانوس) are beyond a light stemmer.

## Premium on stories

- Two seeded stories (Petra and the Red Desert) carry one of the pre-made AI video samples when its file is installed. Visitors and free members see the poster with an upgrade prompt; premium members and staff can watch it, and the video route itself still refuses anyone else. Each sample is labelled for what it is: a clip from a model's demonstration reel, credited, not made from that story.
- Staff can put a member back on the free plan from the staff page (by email), for example after a demo checkout. The reset is audited with the plan it replaced, and the log names the member.

## Cloned voices

- A voice is preparing, ready, needs the speaker's verification (when the provider asks), failed (with the provider's message) or revoked. Cloning is refused, with the reason, when narration uses a provider that cannot read with a cloned voice (Azure), or when ElevenLabs narration would be given a clone made elsewhere.
- Staff choose a ready voice to narrate a story that is not their own, or go back to the default voice. The narration is made again and the slideshow follows; the player says "Narrated in the voice of <name>". Creating a voice, revoking it and choosing a narrator are audited.
- Revoking a voice deletes, at once, its sample, every narration made with it, the slideshows that carry them and the cached speech in that voice; affected stories are narrated again in the default voice. Deleting the provider's copy runs as a job (never inside a web request) and an already-deleted voice counts as done. A narration that finishes after its voice was revoked is discarded.

- Two provider calls deliberately bypass the gateway because they cost nothing and must not be blocked by the live-AI switch: checking a submitted video's status, and deleting a revoked voice at the provider (privacy comes first). Both run in jobs, never in a web request.
- A provider's own cost for a call stands even when the answer is then refused as unusable (Azure bills the tokens it used); the ledger counts it rather than releasing the reservation.
- A narration queued in a cloned voice checks the voice before speaking, so nothing is paid for in a revoked voice; speech made while the voice was being revoked is deleted with it. A cloned narrator is only used while the narration provider can read with it.
- When ElevenLabs asks the speaker to verify a cloned voice, staff confirm on the staff page once the speaker has done it there; the confirmation is audited.
- Video checks stop `VIDEO_MAX_WAIT_SECONDS` after the video was queued, however often a job is retried; a video that is ready but fails to download is fetched again on the next check. Video cost can be set per second (`VIDEO_USD_PER_SECOND`) or as a flat price per video. `.env.example` sets 0.04 USD per second, fal.ai's price for Wan 2.2 at 480p (checked 2026-11-06), so each 6-second video counts as 0.24 USD instead of the 1 USD flat estimate. The rate is one setting for every video provider except Gemini Omni Flash, which has its own (`GEMINI_OMNI_USD_PER_SECOND`): raise it before giving Veo or Higgsfield keys.

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

## Search and nearby discovery (#15)

- Discovery filters run on the server across all published stories, never just a loaded page. Search is literal, case-insensitive substring matching over title, place, author and every text layer. No fuzzy search or extra index is needed for the demo dataset.
- Story tags are trimmed, Unicode-normalized and lowercased; at most 10 distinct tags of 1 to 40 characters. Tags, category, museum and text filters combine. Existing stories have no tags.
- Nearby uses the Haversine formula in PostgreSQL, with radius 1 to 500 km (default 25). Nearby results are nearest first; ordinary results newest first. Cursors are tied to the active filters.
- Location is requested only after activating nearby discovery, held in memory and sent to the discovery API. It is not stored in the account, local storage or shareable URLs. Permission denial, timeout or unavailable location leave ordinary discovery available.

## Interface language (#16)

- English and Arabic catalogues live in `web/src/locales/`. Keys use `common.snake_case`; the source-copy map lets existing screens use readable English fallbacks. New copy needs an English and Arabic entry. Dynamic messages interpolate named placeholders.
- `i18n.ts` owns the language store. Components subscribe without remounting, so switching languages preserves unsaved input and recording state. Storage restrictions leave the language choice usable for the session.
- The document's `lang` and `dir` follow the selected interface language. Layout uses logical spacing and directional navigation icons mirror; story text keeps its own language and direction. Noto Kufi Arabic is used for Arabic interface copy.

## Frontend delivery and accessibility (#17)

- Variable Manrope, Fraunces and Noto Kufi Arabic fonts are served locally through Fontsource packages with `font-display: swap`. There are no Google Fonts requests.
- Routes and MapLibre load as separate chunks; the main entry decreased from about 1.34 MB to 260 KB uncompressed. MapLibre remains a roughly 954 KB optional map chunk. Route and map failures have retry or list fallbacks.
- Shared avatars fall back to initials after image failure and retry a changed URL.
- Keyboard navigation has a skip link, visible focus rings and mobile navigation. Timed text creates WebVTT caption tracks for media; transcript controls remain available. Text color tokens meet a 4.5:1 contrast target against their paired backgrounds. Reduced-motion preferences disable animation. ESLint includes the recommended accessibility checks; Prettier and TypeScript run separately.

## Consent-backed voice cloning (#18)

- Staff open a separate voice consent dialog. The speaker confirms identity, rights, storage, processing and synthetic narration before recording/upload. The server validates the current version and all acknowledgments and stores the exact displayed language/wording, authenticated actor, speaker name and server time. These attestations are recorded consent, not automated identity verification.
- Samples are private MP3 copies, 30 to 60 seconds (half a second tolerance for encoding), at most 15 MB uploaded. The sample hash and consent are stored with the queued clone.
- `VOICE_CLONE_PROVIDER=fake` is the default: it demonstrates the workflow without creating a synthetic voice. ElevenLabs uses its documented IVC endpoint, requires its server-side key, LIVE_AI_ENABLED, and a spending reservation. `VOICE_CLONE_ESTIMATE_USD` is a conservative reservation configured for the account, not a quoted provider price.
- Cloning runs only in the worker. A clone submission has one attempt; uncertain external results need manual confirmation, preventing automatic duplicate creation. Provider-required verification is displayed and never treated as a ready voice.
- Provider contract checked against https://elevenlabs.io/docs/api-reference/voices/ivc/create on 2026-10-25.

## Premium and dummy checkout (#19)

- Membership (`free` or `premium`) is stored on the account, independent of staff role. A server feature matrix describes access; premium gates sample playback on the server. Staff may preview samples for their work.
- Checkout is explicitly a sandbox with no card fields, real charge or recurring subscription. Authenticated attempts move from processing to succeeded or failed after a configurable short delay. Polling finalizes the simulated result under a row lock. Success upgrades only the signed-in owner; failure never downgrades an existing membership. Request IDs prevent duplicates.
- The Premium page resumes an attempt from its URL and refreshes authentication state after success. The gallery uses two small, attributed excerpts from the official Wan 2.2 demonstration reel, served locally with posters and on-demand playback. These are provider examples, not fabricated outputs of Hikaya stories. Provenance is in `api/seed/videos/README.md`.

## Staff video generation (#20)

- Reviewer/admin roles are enforced on every video configuration, submission, job and media endpoint. ENABLE_AI_VIDEO gates submission. The offline fake replays a saved provider demo and is labelled as such; it never pretends to generate the requested story.
- The initial live adapter is fal's Wan 2.2 image-to-video endpoint. Prompt construction combines story title, place, polished text and staff direction. Input photos are snapshotted and sent as data URIs so the demo laptop needs no public media host. The UI exposes only supported models, 16:9/9:16 and a validated seed.
- Submission is a worker job. The provider request URLs are saved before polling; finished media is downloaded with a size limit and served locally. The browser sees real queue/render/completion states, never a fabricated percentage. The same input hash reuses the existing job and cache.
- Paid submission uses the existing gateway. A configurable conservative video estimate is committed on acceptance; uncertain submissions keep their estimate counted because the provider may already have billed. Polling and result retrieval use free gateway operations and never submit another inference request. Uncertain submissions and timed-out jobs retain state for staff follow-up instead of automatically submitting again.
- fal queue contract: https://fal.ai/docs/documentation/model-apis/inference/queue ; model schema: https://fal.ai/models/fal-ai/wan/v2.2-a14b/image-to-video/api (checked 2026-10-25).

## Alternative video providers (#21)

- One browser function and one server provider interface cover fal, Higgsfield, Google Veo and a self-hosted Cog endpoint. Runtime selection is restricted to configured providers and supported models. Unsupported Higgsfield controls are disabled rather than sent as ignored parameters.
- Updated provider research: the Gemini API Veo previews retired on 2026-10-22. The Google selection uses the supported GA Google Cloud Veo endpoint, requiring project/access-token settings. This explicitly replaces the older Gemini-API-key assumption in the initial research.
- Cog's asynchronous prediction API has no GET polling contract. Its adapter makes an idempotent synchronous prediction call inside the worker instead; the app still tracks the local asynchronous job.
- Deployment settings, model contracts, provider limitations and source links are in `docs/VIDEO_PROVIDERS.md`.

## Gemini Omni Flash video with a Google AI Studio key

- Google shut down Veo in the Gemini API on 2026-10-22 and points to Gemini Omni Flash (`gemini-omni-1.2-flash`) as its replacement there, so a Google AI Studio key (`GEMINI_API_KEY`) can make staff videos again: `VIDEO_PROVIDER=gemini_omni`. The existing `gemini` choice stays Veo on Google Cloud, with a project and an access token. (Decided 2026-11-06 with the owner, who holds an AI Studio key.)
- It uses the Interactions API in the background: submitting returns an interaction ID at once, and each check reads that interaction once, as for the other providers, so the worker is never held while Google renders. A finished interaction carries the video as base64 MP4 in its `model_output` step; a failed or cancelled one fails the job with a plain message. The key travels in the `x-goog-api-key` header, never in a URL.
- The request is the story photo (WebP) and the prompt, 16:9 or 9:16, 720p, 6 seconds. Omni takes no seed, so the console disables it and the seed is left out of the cache identity; the aspect ratio works. Videos come with Google's native audio and an invisible SynthID watermark. Google says languages other than English are not evaluated.
- Omni Flash is on the Gemini API's paid tier only (the free tier is "Not available"); a free-tier key is refused, and the message says so. A wrong key is named as such: Google answers it with 400 `API_KEY_INVALID`, not 401, so a 400 is not taken for a blocked prompt unless it says so. Google bills output tokens, 5,792 per second at 720p at 12 USD per million, about 0.07 USD a second. `GEMINI_OMNI_USD_PER_SECOND` (default 0.08, headroom for input and thinking tokens) is Omni's own rate, so a video reserves 0.48 USD on the card budget; `VIDEO_USD_PER_SECOND` and `VIDEO_ESTIMATE_USD` do not apply to it.
- Not exercised with a real key yet; contract tests mock Google's HTTP answers. Sources, checked 2026-11-06: https://ai.google.dev/gemini-api/docs/omni , https://ai.google.dev/gemini-api/docs/background-execution , https://ai.google.dev/gemini-api/docs/pricing , https://ai.google.dev/gemini-api/docs/video

## Narrated AI videos (up to a minute)

- Staff can make a narrated AI video of a story: the story's own soundtrack, either its narration (the default voice or a consenting cloned voice, whichever narrates the story) or the storyteller's recording, laid over AI video shots, with timed subtitles. Only the chosen soundtrack is heard: Omni always generates its own sound (voices included) and cannot be asked for silence, so the shots' sound is dropped entirely, and the lead-in and tail are silent. (Changed on 2026-11-06 at the owner's request: the first version kept Omni's sound quietly underneath, and its voices were still audible.) (Decided 2026-11-06 with the owner, after a live proof of concept on the Petra story; a live one-minute test followed.)
- The soundtrack is the script. Its lines and timings (the narration's alignment, or the transcript's for the recording) are cut into shots at line boundaries, each at most the provider's longest shot (15 s for Omni); a single line longer than that is split evenly. Each shot's prompt is the English text of the lines spoken during it, the place and title, the staff direction, and a continuity instruction. No separate language model writes the script. Without an English translation of every line, prompts use the spoken text and subtitles have one line; the plan says so before anything is queued.
- Shots are chained: the first starts from the story photo, each later one from the frame where the previous shot is cut, so cuts line up. The opening frame carries the people's look, and each later prompt asks Omni to keep the same people with the same faces, hair and clothes even when the scene moves to another place (in the first live test a guide's robe turned into a shirt there). A separate reference image of the people is not possible: Omni reads a second image as the shot's last frame and interpolates towards it, with or without `task: image_to_video`, and refuses two images above 10 s (`INVALID_ARGUMENT`). Both were seen live on 2026-11-06 and match Google's first-and-last-frame documentation. Shots run one after another, each as a submit job and short check jobs, as for single videos; the worker is never held while a shot renders.
- Every clip is trimmed or held to its planned length, then FFmpeg joins the pictures, lays the soundtrack on as the only sound (0.3 s lead-in) and holds the last frame for a 0.6 s tail that is not asked of the provider. The voice stops, with a short fade, at the end of the last line the video covers, so a cut line is never heard. Subtitles are burned in: the polished text of each spoken line, and the English translation under it when the story is not in English. Arabic lines are wrapped in a right-to-left embedding, so their word order and closing full stop are right even with Latin words inside.
- Length: the video lasts as long as the soundtrack, up to `NARRATED_VIDEO_MAX_SECONDS` (60 at most). A longer soundtrack is cut at the last whole line that fits, and the plan says how many lines the video covers.
- Cost: each shot is its own ledger entry at its own length. Before anything is queued, and again before a retry, the estimate of the shots still to make must fit the card and daily budgets. This check reserves nothing, so other spending in between can still reach a cap; the video then stops at a shot and can be retried once there is room. A minute of Omni is about 4 USD at Google's price (the ledger reserves 0.08 USD a second). A submission Gemini Omni refuses outright (a 4xx answer: wrong key, free tier, quota, a refused prompt) started nothing and is released from the ledger, not counted.
- Retrying a failed narrated video goes on from where it stopped: finished shots are kept; a shot the provider reported as failed, cancelled or filtered is submitted again as a new paid attempt; a shot whose check failed for any other reason is checked again, never paid for twice. A submission whose outcome is unknown (the provider may have accepted and billed it) is submitted again only when staff confirm it, knowing it may be billed twice.
- Revoking a cloned voice also removes every narrated video whose soundtrack it read: its files are deleted at once, the video is marked as removed, and a step still running stops.
- Progress is shown as fixed, translated messages with the shot number beside them. A shot Omni fails names Google's own reason (for example `INVALID_ARGUMENT`) instead of guessing at a safety filter.
- Providers: Gemini Omni Flash (shots of 3 to 15 s) and the offline fake for rehearsal. The other providers make fixed-length clips and are not offered for narrated videos yet.

## Refined shot scripts and the voice choice for narrated videos

- Before any shot is made, a screenwriter turns the story into a refined shot script for the video model. It reads the title, place, the whole story (in English), the planned shots with the words spoken in each, the staff direction and the story photo the film starts from, and writes one continuous, geographically coherent film: one route through real places with no jumping back to a place just left, every person and object set up before it is used (the tea is brought before it is poured), one fixed description of the cast kept identical in every shot, and for each shot one action, one camera move and the natural sounds of the scene. The shot prompts are built from that script. (Decided 2026-11-06 with the owner, after shots in a live test jumped back to a place just left and a tea table appeared from nowhere.)
- The screenwriter is a provider chosen by `SCRIPT_PROVIDER`: `fake` (the default: the shot's own words, no call) or `gemini` (Gemini 3.8 Flash through the Gemini API with the AI Studio key, Structured Outputs with exactly one entry per shot; 0.75 USD in and 3.75 USD out per million tokens through 2026, about a cent a video, on the card budget). It runs as the first step of the video's worker jobs, through the gateway (ledger and cache), never in a web request. Its script is stored with the video and shown on the staff page. A failed script step fails the video before any shot is paid for, and a retry writes it again.
- The voice of a narrated video is one switch on the staff page, with the default from `NARRATED_VIDEO_AUDIO`: `soundtrack` (the story's ElevenLabs narration or the storyteller's recording, as above; Omni's own audio dropped) or `omni` (Omni's own audio kept: each shot's prompt asks for a voice-over of the words spoken in it, in the story's language, by the narrator the script describes, over the natural sounds of the scene, with no music; the story's soundtrack is then only used for the shot timings and subtitles, which follow its line timings and are approximate against Omni's voice). Google says Omni is evaluated in English only, so Arabic voice-over quality is not promised.
- Voice Library voices, including the Jordanian-accent ones, need the ElevenLabs Creator plan or higher; a lower plan is refused, and the narration step shows ElevenLabs' own explanation. Adding a library voice to the account and cloning a voice also need a key with the `voices_write` permission. (Both seen live on 2026-11-06.) Until then a Jordanian voice can come from Omni's own voice.
- Sound effects with the ElevenLabs voice (footsteps on stone and sand, cloth, a kettle) are wanted later. The script already describes each shot's sounds so they can be generated and mixed under the narration then; for now the ElevenLabs choice carries the voice only.

## Browser verification (#22)

- Playwright runs the real API and PostgreSQL worker with fake AI providers, local media and blocked external browser traffic. Three journeys verify discovery/RTL, sandbox Premium checkout, consent/upload and queued video playback, location denial, and staff authorization. CI records failure traces, screenshots, video and logs.
- Browser verification caught and fixed lazy staff-module initialization, untranslated feed/player tabs, signup password labelling, and mobile RTL grid overflow. The mobile overflow assertion and axe scans remain regression checks.
- Local setup and coverage limits are documented in `docs/BROWSER_TESTS.md`. Live paid services and physical microphone capture are outside the deterministic CI suite.
- Final local verification: 228 backend tests, 11 frontend unit tests and 3 Chromium journeys pass, along with type checks, lint, formatting and the production build. The optional MapLibre bundle still produces Vite's chunk-size warning. Hosted CI has not been triggered.
