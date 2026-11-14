# Story packs

Each folder here is one published story with what its page shows, so it comes with every copy
of the app. On every start (when `SEED_DEMO_DATA` is on) the API adds each pack whose story is
not there yet; nothing is called or paid for. See "Story packs" in `docs/DECISIONS.md`.

| Pack | Story | Storyteller |
| --- | --- | --- |
| `kayed-kiosk-magazine` | مجلة بعد أربعين سنة (a magazine, forty years later) | طارق أحمد كايد, Ahmad Kayed's kiosk, downtown Amman |

A pack holds `story.json` (texts in every version with their timings, place, storyteller's
name, narration and video details) and the media its page shows: `recording`, `narration`,
`slideshow`, `photo-NN.webp` and `video.mp4`. Only material the storyteller agreed to publish
goes here: the edited recording the page plays, never the raw interview or a voice sample, and
never a story read in a cloned voice. This repository is public.

```bash
# Write a published story's pack (from a running copy with its database and media)
cd api && python -m app.story_pack export <story id> <pack name>

# Add packs whose stories are not here yet; --refresh replaces them with the pack
cd api && python -m app.story_pack import
```

Provenance of `kayed-kiosk-magazine`: recorded at the kiosk in downtown Amman and cut to one
48-second story (questions and a second story removed) on 2026-11-14; photos by the Hikaya team.
The video was made with Gemini Omni Flash over his own recording; signs the model invented in
its second half were blurred. Spoken permission to use his voice is in the original interview.
