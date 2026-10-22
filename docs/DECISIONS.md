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
- Live AI calls are off by default during the demo. The demo stories use pre-generated outputs. A toggle turns live AI on.
- API keys live only in `.env`, which is never committed. This repository is public.

## Infrastructure

Docker Compose with four containers: `db` (plain PostgreSQL 16), `api` (FastAPI), `worker` (polls a job table in Postgres), `web` (the React app).

Not used: PostGIS, Redis, Celery, MinIO. Map pins need only latitude and longitude, "nearby" uses a distance formula in SQL, media is stored on local disk behind a storage interface, and background jobs use Postgres row locking. If any of these are ever needed, the interfaces let them slot in.

## Sign-in

Email and password. Sign-up creates a member with no email verification. Staff accounts are seeded. No TOTP and no Google sign-in yet.

## Defaults I assumed (confirm or change)

- Story creation is real (record or upload, AI steps, publish). Only the social interactions and the AI video samples are mock.
- The demo plays pre-generated AI outputs, and live AI is a toggle that is off by default.
- Transcription defaults to ElevenLabs Scribe, with Azure as the fallback. Three short test clips (Jordanian dialect, MSA, English) can flip the default.
- The default narrator voice is chosen by a short listening test between a Jordanian-tagged ElevenLabs voice, a clone of a consenting Jordanian team member, and Azure `ar-JO`.

## Out of scope

AI persona chat, reels, the 360 viewer, analytics dashboards, the visit planner (no document defines it), real payments, Google sign-in, TOTP, email verification, scaling.
