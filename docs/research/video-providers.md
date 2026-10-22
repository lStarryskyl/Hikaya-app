# AI image-to-video providers for Hikaya premium videos

Researched 2026-10-17. Every page cited below was opened on that date ("seen 2026-10-17"). Source ids like [H1] resolve to a URL in the Sources index at the bottom. Pages were read through a summarising fetch tool, so re-check any number in the provider's console or pricing page before you add money. Anything I could not confirm from a primary source is marked UNVERIFIED and repeated in the list at the end.

## Summary and recommendation

1. Best option: **fal.ai** (one key, many models, prepaid USD credits, Python client plus plain REST). Default model `minimax/h3-max-turbo/image-to-video` at 768P, priced $0.026/s until 31 Oct 2026 and $0.04/s after (about $1.25 to $1.92 per 45 s story).
2. Quality alternative on the same fal account: `fal-ai/kling-video/v2.5-turbo/pro/image-to-video`, $0.35 per 5 s clip (about $2.80 per story). Spend about $1 on a one-photo bake-off across both plus LTX-2 Fast before committing.
3. Fallback: **Gemini API, Veo 3.1 Lite**, $0.05/s at 720p (about $2.40 per story), Jordan is on Google's availability list, but Google rejects prepaid cards.
4. Higgsfield **does** have a public documented API (pay-as-you-go USD balance, $5 minimum top-up). Its cheapest prices are promotional and two of its own pages disagree, so treat it as third choice unless the console price matches the promo.
5. Self-hosting open models (Wan 2.2, LTX-2, HunyuanVideo 1.5) costs about the same in GPU rent as fal's hosted endpoints and adds dev time, so it is not sensible at this budget. Estimated total for two stories with 50% retries: about $4 to $9 depending on model.

---

## 1. Higgsfield: public API?

**Yes, there is a public, documented API.** Docs live at docs.higgsfield.ai; it is described as one authenticated asynchronous API for images and videos [H1]. It is separate from the website plans: website plan credits and "Unlimited" access do not apply to the API [H15].

| Item | Finding | Source |
|---|---|---|
| Base URL | `https://api.higgsfield.ai` in the index, intro and model pages. The video guide's curl example instead uses `https://platform.higgsfield.ai` for the `dop/standard` endpoint. Conflict, use `api.higgsfield.ai` as in the per-model pages. | [H1] [H6] [H7] vs [H2] |
| Auth | Header `Authorization: Key <KEY_ID>:<KEY_SECRET>`. Keys are created in the console (console.higgsfield.ai); the secret is shown once. Server-side only. | [H1] [H7] [H15] |
| Python SDK | `pip install higgsfield-client`, env var `HF_KEY=id:secret`, `higgsfield_client.subscribe(model_id, arguments=...)`. Node: `@higgsfield/client`. REST also works from any language. | [H5] |
| Pattern | Async. POST returns `request_id`, `status_url`, `cancel_url`. Poll `status_url` or pass a webhook. Done state is `completed` with `video.url`. Statuses: queued, in_progress, completed, failed, nsfw, canceled. Cancel works only while queued. Send an `Idempotency-Key` header on submissions. | [H2] [H7] [H12] |
| Webhook | Add URL-encoded `hf_webhook` query param to the submit call. POSTs on completed, failed or nsfw, 10 s reply deadline, retried up to 2 h on 5xx, dedupe on `request_id` plus status. No signature or secret is documented. | [H4] |
| Output retention | Files kept at least 7 days. Copy them to your own storage. | [H12] [H13] |
| Billing | Pay-as-you-go USD balance, no subscription. **Minimum top-up $5.** Failed and NSFW-flagged requests are not billed. Funds expire one year after being added. Balance cannot go negative. | [H3] [H13] |
| Free credits | The API landing page says $15 is added to the balance after you verify a business email and add a card, plus a free Playground and a sign-up discount on "sale" models. Whether this applies to an individual in Jordan is UNVERIFIED. | [H14] |
| Rate limits | 20 concurrent requests per API key (first key). Other limits depend on account and model and are shown in the console, no numbers published. | [H13] [H14] [H3] |
| Commercial / demo use | Terms of Use §4.4: Higgsfield does not claim ownership of inputs or outputs and does not restrict commercial use of outputs; outputs may resemble other users' outputs. The help page says API outputs can be used commercially. Higgsfield may use content to improve its models (whether that covers API traffic is UNVERIFIED). | [H16] [H17] [H13] |
| Region / payment | Terms list no restricted countries; you represent you are not in a US-embargoed country (§19.12). Only "add a card" is mentioned for payment. Jordan acceptance of cards: UNVERIFIED. | [H16] [H14] |

### Image-to-video models exposed (start image plus prompt is supported)

| Endpoint (POST) | Duration | Resolution | Last frame | Audio | Source |
|---|---|---|---|---|---|
| `/bytedance/seedance-2.5/image-to-video` | 4 to 30 s (default 5) | 480p, 720p (default), 1080p | `end_image_url` | `generate_audio` (default true) | [H7] |
| `/kling-video/v2.6/pro/image-to-video` | 5 or 10 s | aspect 16:9, 9:16, 1:1 | not documented | `sound` on/off | [H8] |
| `/wan/v2.6/image-to-video` | 5, 10 or 15 s | 480p, 720p, 1080p | not supported | optional `audio_url` | [H9] |
| `/lightricks/ltx-2.5/image-to-video/fast` (and `/pro`) | 6, 8 or 10 s | 720p to 4k | `end_image_url` | `generate_audio` | [H10] |
| `/minimax/hailuo-2.3/standard/image-to-video` | schema page not read | | | | [H11] |

Other families named in the catalog (Kling 2.5/3.0/O3, Wan 2.7/3.0, MiniMax H3, PixVerse 6, Grok Imagine, DoP) have their own pages; I did not read each schema [H11].

### Higgsfield price points (two pages disagree, so both are shown)

- Marketing blog "list rates": Kling 2.5 $0.042/s, Kling 2.6 $0.07/s, Seedance 2.5 $0.0738/s, Kling 3.0 $0.112/s, MiniMax H3 $0.13/s, LTX 2.5 Pro $0.17/s, Wan 3.0 $0.20/s [H15].
- API landing page (shows discounted price and an "original" price): Kling 2.5 $0.021 (orig $0.042), Kling 2.6 $0.035 (orig $0.07), Hailuo 2.3 $0.0117 (orig $0.0467), Wan 3.0 $0.02 (orig $0.05), LTX 2.5 Fast $0.09, LTX 2.5 Pro $0.12, Seedance 2.5 $0.144 (orig $0.2057) [H14]. These are sale prices with an unstated end date.
- The two pages contradict each other on several models (for example Wan 3.0 $0.20 vs $0.05 original; Seedance 2.5 $0.0738 vs $0.2057 original). The per-model docs pages show no prices, and the help page says an estimate endpoint returns the cost before a run [H13]. Use that estimate (endpoint name UNVERIFIED) before spending.

Verdict: real API, usable, and potentially the cheapest if the sale prices hold (Kling 2.6 at $0.035/s would be about $1.40 for 40 s), but pricing is not stable or clear enough to plan a budget on.

---

## 2. Other hosted providers (image-to-video via API)

Prices are the cheapest sensible resolution at the time of reading. "Account access" notes what a new individual must do. Full price rows with URLs are in the price table below.

### fal.ai (recommended)
- **Access:** sign in, buy prepaid credits, create key. New accounts start at 2 concurrent requests; buying credits raises it automatically up to 40; extra requests queue rather than fail [F3]. No approval step is documented for hosted model APIs (approval is only for Serverless) [F8]. Minimum credit purchase and free credits for new accounts: UNVERIFIED.
- **Interface:** `Authorization: Key $FAL_KEY`; `POST https://queue.fal.run/{model_id}`; status and result URLs; webhook via `fal_webhook` query param or `webhook_url` in Python; Python `fal_client.submit/subscribe`; statuses IN_QUEUE, IN_PROGRESS, COMPLETED [F6].
- **Billing:** you pay for successful outputs only; HTTP 500+ errors and queue time are not billed; 422 invalid-input errors may be billed [F1] [F2]. Purchased credits expire after 365 days and are non-refundable; payment by card or ACH in USD [F4].
- **Models worth testing:**
  - `minimax/h3-max-turbo/image-to-video`: $0.026/s at 768P (promo, 35% off until 31 Oct), $0.04/s after; 480P $0.01625 promo / $0.025; 1080P $0.052 / $0.08. Duration 0.92 to 15 s (continuous), `end_image_url` supported, optional `target_audio_url` (2 s minimum, 15 MB) to pin a soundtrack [F9]. The pricing page lists "H3 Max Turbo Image to Video" at $0.025 and "H3 Max" at $0.05 without a resolution [F5]; the model page is more specific, so I used it.
  - `fal-ai/kling-video/v2.5-turbo/pro/image-to-video`: $0.35 for 5 s, +$0.07 per extra second; 5 or 10 s; `tail_image_url` for last frame [F7].
  - `fal-ai/ltx-2/image-to-video/fast`: $0.04/s at 1080p, $0.08 at 1440p, $0.16 at 2160p; 6 to 20 s (over 10 s only at 1080p/25 fps); `generate_audio` toggle; no end image [F10]. Model page carries a "Commercial use" label [F11].
  - `fal-ai/wan/v2.2-a14b/image-to-video`: $0.04 (480p), $0.06 (580p), $0.08 (720p) per second at 16 fps; about 1 to 10 s [F12].
  - `fal-ai/wan/v2.7/image-to-video`: $0.10/s (720p), $0.15/s (1080p); 2 to 15 s; `end_image_url`, `audio_url` [F13].
  - `fal-ai/minimax/hailuo-2.3/standard/image-to-video`: $0.28 per 6 s, $0.56 per 10 s; no end image [F14].
  - Also listed: Veo 3.1 $0.20/s without audio, $0.40/s with; Seedance 2.0 Fast $0.2419/s at 720p; Kling 3.0 Pro $0.112 to $0.14/s (two fal pages differ) [F15] [F5].
- **Terms:** US export-control representation only, no countries named; "own personal or internal business use"; the ToS does not clearly state output ownership and says each model has its own license (most marked Commercial use) [F4] [F2].

### Google Veo via the Gemini API (fallback)
- **Prices (per second, audio included, billed only on success; no free tier; no batch price listed):** Veo 3.1 Lite $0.05 (720p) / $0.08 (1080p), not available at 4K; Veo 3.1 Fast $0.10 / $0.12 / $0.30 (4K); Veo 3.1 $0.40 / $0.40 / $0.60 [G1]. A user on Google's forum confirmed a $0.40 charge for one 8 s Lite clip (user report, non-primary) [G6].
- **Features (Lite):** durations 4, 6 or 8 s; 720p default, 1080p only at 8 s; 16:9 or 9:16; text-to-video and image-to-video; `lastFrame` supported with `image`; no extension, no reference images; audio always on (strip it with `-an`); models are labelled Preview (`veo-3.1-lite-generate-preview`) [G2].
- **API:** Python `google-genai`: `client.models.generate_videos(...)`, poll `client.operations.get(op)` every ~10 s, download with `client.files.download`; generated videos are kept 2 days; SynthID watermark; image-to-video accepts only `personGeneration=allow_adult` and in MENA that is the only allowed value (may block photos of children, strictness UNVERIFIED) [G2].
- **Access:** Jordan is on the Gemini API availability list [G3]. Paid use needs Cloud Billing linked and a Prepay balance of at least $5 (max $5,000), Tier 1 spend cap $250/month [G4]. Google does not accept prepaid cards or debit cards that need 2-factor authentication, and no wire for Prepay [G5]. The Cloud Billing currency table has no Jordan row, so the billing-country status for Jordan is inconclusive [G7].
- The same pricing page also lists a newer Gemini Omni Flash video model at about $0.10/s (720p estimate); I did not check its image-to-video support [G1].

### Runway API
- `gen4_turbo` costs 5 credits per second, credits are $0.01 each, so **$0.05/s**; `gen4.5` 12 credits/s ($0.12/s); `veo3.1_fast` 10/15 credits/s; `h3_max` 5 (480p) or 8 (768p) credits/s [R1].
- `gen4_turbo`: duration 2 to 10 s, 720p-class ratios, first frame only; Veo 3.1 and Kling models accept first plus last frame via `promptImage` with `position: first|last` [R2].
- Access: dev.runway.com, create project, API key, buy credits, **minimum payment $10** [R3]. Tier-based rate limits upgrade automatically with spend; the starting tier and numbers are not published in text I could read (UNVERIFIED) [R4]. Moderated generations are still charged [R5]. Output URLs expire (24 to 48 h per the API reference) [R2]. Python SDK `runwayml`, header `X-Runway-Version: 2024-11-06` required [R5][R6].

### Luma API
- Ray 3.2 pay-per-output: 5 s clip $0.15 (540p), $0.30 (720p), $1.20 (1080p); 10 s $0.45 / $0.90 / $3.60; no minimum for pay-as-you-go. The page contradicts itself between table and FAQ and between "per 5-second block" and the 10 s prices, so confirm in the console [L1].
- `POST https://agents.lumalabs.ai/v1/generations` with `model: "ray-3.2"`, `video.start_frame` and `video.end_frame`, poll `GET /v1/generations/{id}`; Python and JS SDKs [L2]. No waitlist is mentioned; free credits and supported countries are not stated (UNVERIFIED) [L3].

### Replicate
- Per-second hardware billing for most models, per-output billing for some. Its pricing page lists only older Wan 2.1 I2V at $0.09/s (480p) and $0.25/s (720p), via wavespeedai [P1]. Prices for newer models (Wan 2.2/2.7, Kling 2.5, Seedance, Veo, Hailuo) did not render in the pages I could read: UNVERIFIED.
- Rate-limit note: as balance approaches zero, stronger limits apply, and they recommend auto-reload above $20; granted credit without a payment method is limited to 1 request/s, 6/min [P2]. That is awkward for a $10 test.
- Minimum purchase and supported countries: UNVERIFIED.

### Others
- **Kling direct API** and **BytePlus ModelArk (Seedance)** pricing pages returned only page shells; direct prices UNVERIFIED. Kling 2.5/2.6/3.0 and Seedance 2.0/2.5 prices are available through fal, Runway and Higgsfield above.
- **Alibaba Model Studio (Wan 2.7 I2V):** international (Singapore) $0.10/s at 720P, $0.15/s at 1080P, 300 requests/min [A1]. Durations, first/last frame, async pattern, free quota and account approval were not on the page I read: UNVERIFIED.
- **MiniMax API platform:** Hailuo 2.3 Fast 768P is $0.19 (6 s) or $0.32 (10 s); Hailuo 2.3 768P $0.28 / $0.56; listed under "legacy models", the newer H3 price was not seen; minimum top-up, payment and regions UNVERIFIED [M1].

---

## 3. Open-source models

| Model | License (primary) | Commercial use | VRAM | Typical speed | Source |
|---|---|---|---|---|---|
| Wan 2.2 I2V-A14B (480p/720p) | Apache 2.0 | Yes, license text grants freedom to use; Wan claims no rights over outputs | 80 GB for the single-GPU command (with offload flags) | Timing table is an image, not readable | [W1] [W2] |
| Wan 2.2 TI2V-5B (720p, 24 fps, T2V + I2V) | Apache 2.0 | Same | 24 GB (RTX 4090) | 5 s 720p in under 9 min on one consumer GPU, unoptimised | [W1] [W3] |
| LTX-2 / LTX-2.3 (22B, video + audio, I2V) | LTX-2 Open Weights License (5 Jan 2026) | Free below $10M annual revenue; entities at or above $10M need a paid license; no competing product; attribution and AI-content disclosure terms | not stated; FP8 and offload recommended; ~66 GiB download | not stated (distilled pipeline is 8 + 4 steps) | [O1] [O2] [O3] |
| HunyuanVideo-I2V (v1) | Tencent Hunyuan Community License (tag only on the model card) | Terms below were read from the HunyuanVideo-1.5 repo's LICENSE; the v1 text itself was not read, so assume similar (UNVERIFIED): territory excludes EU, UK, South Korea; license needed above 100M monthly users; outputs may not be used outside the territory or to train other AI models | ~60 GB peak at 720p (80 GB recommended) | 129 frames (about 5 s): 1904 s on 1 GPU, 337 s on 8 GPUs | [T1] [T2] |
| HunyuanVideo 1.5 (8.3B, 480p/720p, SR to 1080p) | Tencent Hunyuan Community License (license text read from the GitHub repo) | Same territory and 100M-user terms | 14 GB minimum with offloading | Step-distilled 480p I2V "within 75 seconds" on one RTX 4090 | [T3] [T2] |

Newer Wan versions (2.5, 2.6, 2.7, 3.0) are sold through APIs (fal, Runway, Higgsfield, Alibaba). I found no open weights for them in the visible part of the Wan-AI Hugging Face listing, which shows 10 of 27 models (UNVERIFIED for the rest) [W4].

### Realistic cost to run 10 to 20 clips

GPU rent prices read today: RunPod RTX 4090 $0.89/h, L40S $1.09/h, A100 80GB $1.79/h, H100 PCIe $2.89/h [N1]. Modal bills per second (A100 80GB $0.000694/s, about $2.50/h) and lists $30/month free credits on the Starter plan [N2]. Replicate lists A100 80GB at $5.04/h and L40S $3.51/h for its own hardware [P1]. Vast.ai prices are a live widget with no numbers in the page text [N3].

Rough arithmetic (my estimate, built from the figures above):
- Wan 2.2 TI2V-5B on a 4090: 16 clips x up to 9 min = about 2.4 GPU hours = about $2.15 at $0.89/h. Add 3 to 4 hours of setup, model download and failed runs and the total is about $5 to $6.
- HunyuanVideo 1.5 step-distilled on a 4090: 16 clips x 75 s = about 20 min = under $0.50 of pure generation, but 480p-class quality, EU/UK/KR exclusion and a longer setup.
- Wan A14B / HunyuanVideo-I2V v1 need 60 to 80 GB cards ($1.79 to $2.89/h). Their per-clip times are not published in text, so a cost estimate is UNVERIFIED.

**Honest verdict:** the cash cost (about $3 to $6) fits the budget, but fal's hosted endpoints for the same families cost $1.25 to $3.84 for both stories (H3 Max Turbo or LTX-2 Fast), with no setup, no GPU debugging and no 66 GB downloads. Self-hosting only makes sense if the owner wants to show an open-source stack or has free dev time. Hosting platforms that run open models (fal: Wan 2.2, LTX-2; Replicate: Wan family) cover the owner's "open-source models and platforms that host them" request without the ops burden.

---

## 4. Getting 30 to 60 s from 5 to 15 s clips

**Pattern: one clip per photo, then stitch.** With up to 8 photos, 8 clips x 4 to 8 s gives 32 to 64 s before crossfades.

1. **Plan the timeline from the narration.** Give each photo a time slot from transcript segment timestamps (or split the audio length evenly). Request a clip length equal to slot plus the crossfade; if the model allows only fixed lengths (Kling 5/10 s, Veo 4/6/8 s, LTX 6/8/10 s on Higgsfield), pick the nearest and trim or hold in FFmpeg. H3 Max Turbo accepts any duration from 0.92 to 15 s, which makes slot matching trivial [F9].
2. **Generate silent clips.** Turn model audio off where possible (`sound: off`, `generate_audio: false`); for Veo Lite, where audio is always on, drop it with `-an` [G2].
3. **Normalise, crossfade, add the narration** with FFmpeg. I tested this exact recipe on synthetic clips (different sizes and frame rates, 6 + 5 + 6 s with 0.5 s fades) in FFmpeg 6.1 and it produced a 16.0 s, 1280x720, 30 fps file with the narration track:

```bash
# per clip: same size, fps, pixel format, no audio
ffmpeg -y -i clipN.mp4 -an -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p,setsar=1" -r 30 -video_track_timescale 15360 nN.mp4

# crossfade chain, offset_k = (sum of clip lengths up to k) - (k+1) * fade
ffmpeg -y -i n1.mp4 -i n2.mp4 -i n3.mp4 -i narration.m4a -filter_complex \
 "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=5.5[v01];[v01][2:v]xfade=transition=fade:duration=0.5:offset=10.0[v]" \
 -map "[v]" -map 3:a -c:v libx264 -crf 20 -preset veryfast -c:a aac -shortest -movflags +faststart out.mp4
```
   (FFmpeg's own `xfade` documentation could not be fetched today, so the filter options come from my local test, not a cited page.)
4. **Cheaper tricks:** animate only 4 or 5 of the 8 photos and use the existing pan-and-zoom for the rest; first-and-last-frame interpolation between consecutive photos is available on several models but will morph between unrelated scenes, so it is not recommended here. Wan 2.7 (`audio_url`, driving audio) and H3 Max Turbo (`target_audio_url`, soundtrack pin) can take an audio file, but that is not needed when FFmpeg lays the narration, and what they do with spoken narration over a photo was not tested [F13] [F9].
5. **Keep every clip.** Cache by hash of (image, prompt, model, params, duration) so a re-run never re-bills a clip you already have. Providers delete outputs after 2 days (Gemini), 24 to 48 h (Runway) or 7 days (Higgsfield), so download immediately [G2] [R2] [H12].

### Cost per finished story (8 clips)

Assumptions: 8 clips of 6 s = 48 s generated, 0.5 s crossfades, about 44.5 s finished. Kling uses 8 x 5 s = 40 s generated, about 36.5 s finished. "With retries" assumes 50% of clips are regenerated once.

| Option | Per story | Two stories | Two stories, 50% retries |
|---|---|---|---|
| fal H3 Max Turbo 768P, promo $0.026/s (to 31 Oct) | $1.25 | $2.50 | $3.75 |
| fal H3 Max Turbo 768P, list $0.04/s (after 31 Oct) | $1.92 | $3.84 | $5.76 |
| fal LTX-2 Fast 1080P, $0.04/s | $1.92 | $3.84 | $5.76 |
| Gemini Veo 3.1 Lite 720p, $0.05/s | $2.40 | $4.80 | $7.20 |
| Runway gen4_turbo, $0.05/s (but $10 minimum purchase) | $2.40 | $4.80 | $7.20 |
| Luma Ray 3.2 720p, 8 x $0.30 per 5 s | $2.40 | $4.80 | $7.20 |
| fal Kling 2.5 Turbo Pro, 8 x $0.35 per 5 s | $2.80 | $5.60 | $8.40 |
| Higgsfield Kling 2.6, promo $0.035/s x 40 s | $1.40 | $2.80 | $4.20 |
| Higgsfield Kling 2.6, list $0.07/s x 40 s | $2.80 | $5.60 | $8.40 |
| fal Wan 2.7 720p, $0.10/s (over budget) | $4.80 | $9.60 | $14.40 |
| Gemini Veo 3.1 Fast 720p, $0.10/s (over budget) | $4.80 | $9.60 | $14.40 |

Add roughly $0.70 to $1 for a one-photo bake-off (H3 Max Turbo 5 s about $0.13, Kling 5 s $0.35, LTX-2 6 s $0.24). For a 60 s story scale linearly with seconds (for example Veo Lite 8 x 8 s = 64 s = $3.20).

---

## 5. Recommendation

**Primary: fal.ai.**
- Reasons: lowest verified per-second price among easy-to-start providers; durations are flexible (0.92 to 15 s on H3 Max Turbo); first and last frame supported on three of the listed models; a single key reaches Kling, LTX-2, Wan, Hailuo, Seedance and Veo, so swapping models is a string change; bills only successful outputs; Python client and plain REST; no approval step documented for hosted model APIs.
- Plan: (1) buy the smallest credit pack the dashboard allows (minimum UNVERIFIED), (2) run a bake-off on one photo with `minimax/h3-max-turbo`, `kling-video/v2.5-turbo/pro` and `ltx-2/image-to-video/fast`, (3) generate both stories with the winner, retries only on failed clips. Expected total $4 to $9 including bake-off and retries, inside the $8 to $10 envelope.
- Check first: that a Jordanian card is accepted (no source states either way), and that the H3 Max Turbo promo is still running (it ends 31 Oct 2026).

**Fallback: Gemini API with Veo 3.1 Lite** ($0.05/s, $5 minimum prepay, Jordan listed as available, official SDK, `lastFrame` supported). Use it if fal signup or payment fails or if quality from the fal models is poor. Watch for: prepaid and 2FA debit cards are rejected, models are Preview, `allow_adult`-only for image-to-video in MENA, 4/6/8 s only, audio always on.

**Third: Higgsfield**, only after reading the live console/estimate price; if the promo Kling 2.6 ($0.035/s) or Hailuo 2.3 ($0.0117/s) prices hold and the $15 credit applies, it is the cheapest of all.

### What to put behind a provider interface

The renderer runs as a script or server job (never in the Vite browser bundle: Higgsfield, fal and Runway all say keys must stay server-side [H1] [F2]). For a judge demo only two videos are needed, so a one-off CLI that writes two MP4s into the demo assets, with the paid page unlocking the pre-rendered file, is enough.

```ts
interface VideoProvider {
  id: 'fal' | 'gemini' | 'higgsfield' | 'mock';
  capabilities(modelId: string): {
    allowedDurations: number[] | { min: number; max: number };
    supportsEndFrame: boolean;
    outputHasAudio: 'always' | 'optional' | 'never';
    resolutions: string[];
  };
  estimateCostUsd(req: ClipRequest): number;           // from a local price table
  submit(req: ClipRequest): Promise<{ jobId: string }>; // req carries idempotencyKey
  poll(jobId: string): Promise<ClipStatus>;             // queued | running | succeeded | failed | blocked
  fetchResult(jobId: string, destPath: string): Promise<void>; // download to our storage at once
  cancel?(jobId: string): Promise<void>;
}
type ClipRequest = {
  imagePath: string; prompt: string; durationSec: number;
  aspect: '16:9' | '9:16'; resolution: string;
  endImagePath?: string; seed?: number; modelId: string; idempotencyKey: string;
};
```

Keep these outside the interface, in the pipeline: timeline planning from the transcript; per-clip state stored on disk or in a DB (so reruns resume); a content-hash cache; a budget guard that sums `estimateCostUsd` before each submit and refuses past a hard cap (for example $9); FFmpeg normalise, crossfade and narration mux; per-clip fallback to the existing pan-and-zoom renderer when a clip fails or is blocked; a `mock` provider that returns a local sample clip for development and the dummy-payment flow. Provider and model ids come from env config (`VIDEO_PROVIDER`, `VIDEO_MODEL`), prices live in one table with a "last checked" date, and uploads use a public or signed URL helper because several APIs take only `image_url` (Higgsfield rejects `asset://` references) [H7].

---

## Price table

All prices are USD, accessed 2026-10-17. "Cheapest sensible" means the lowest resolution that is still usable for a web demo.

| Provider and model | Cheapest sensible price | Max clip per call | I2V | First and last frame | Python SDK / REST | New individual account | Source |
|---|---|---|---|---|---|---|---|
| fal, MiniMax H3 Max Turbo | $0.026/s at 768P (promo to 31 Oct), $0.04/s after; 480P $0.01625 / $0.025 | 15 s (0.92 to 15 continuous) | yes | yes (`end_image_url`) | `fal_client` and REST | buy credits, concurrency 2 | https://fal.ai/models/minimax/h3-max-turbo/image-to-video/llms.txt |
| fal, MiniMax H3 Max | $0.052/s at 768P (promo), $0.08/s after | 15 s | yes | yes | same | same | https://fal.ai/models/minimax/h3-max/image-to-video/llms.txt |
| fal, LTX-2 Fast | $0.04/s at 1080p | 20 s | yes | no | same | same | https://fal.ai/models/fal-ai/ltx-2/image-to-video/fast/llms.txt |
| fal, Wan 2.2 A14B | $0.04/s at 480p, $0.08/s at 720p | about 10 s | yes | not in schema read | same | same | https://fal.ai/models/fal-ai/wan/v2.2-a14b/image-to-video/llms.txt |
| fal, Hailuo 2.3 Standard | $0.28 per 6 s, $0.56 per 10 s (768p) | 10 s | yes | no | same | same | https://fal.ai/models/fal-ai/minimax/hailuo-2.3/standard/image-to-video/llms.txt |
| fal, Kling 2.5 Turbo Pro | $0.35 for 5 s, $0.07/s extra | 10 s | yes | yes (`tail_image_url`) | same | same | https://fal.ai/models/fal-ai/kling-video/v2.5-turbo/pro/image-to-video/llms.txt |
| fal, Wan 2.7 | $0.10/s at 720p, $0.15/s at 1080p | 15 s | yes | yes | same | same | https://fal.ai/models/fal-ai/wan/v2.7/image-to-video/llms.txt |
| fal, Veo 3.1 / Seedance 2.0 Fast | $0.20 to $0.40/s / $0.2419/s | not read | yes | not read | same | same | https://fal.ai/explore/image-to-video-apis |
| Gemini API, Veo 3.1 Lite | $0.05/s at 720p, $0.08/s at 1080p | 8 s | yes | yes (`lastFrame`) | `google-genai` | AI Studio, prepay at least $5 | https://ai.google.dev/gemini-api/docs/pricing.md.txt and https://ai.google.dev/gemini-api/docs/veo |
| Gemini API, Veo 3.1 Fast | $0.10/s at 720p | 8 s | yes | yes | same | same | https://ai.google.dev/gemini-api/docs/pricing.md.txt |
| Gemini API, Veo 3.1 | $0.40/s at 720p | 8 s | yes | yes | same | same | https://ai.google.dev/gemini-api/docs/pricing.md.txt |
| Runway, gen4_turbo | 5 credits/s = $0.05/s | 10 s | yes | first frame only | `runwayml` and REST | dev.runway.com, minimum $10 | https://docs.dev.runwayml.com/guides/pricing.md |
| Runway, gen4.5 | 12 credits/s = $0.12/s | 10 s | yes | first frame only | same | same | https://docs.dev.runwayml.com/guides/pricing.md |
| Luma, Ray 3.2 | $0.15 per 5 s at 540p, $0.30 at 720p | 10 s priced | yes | yes (`start_frame`, `end_frame`) | Python, JS, REST | Build plan, pay per output | https://lumalabs.ai/api/pricing |
| Higgsfield, Kling 2.6 | $0.035/s (sale) or $0.07/s (list) | 10 s | yes | not documented | `higgsfield-client` and REST | balance, minimum top-up $5 | https://higgsfield.ai/higgsfield-api and https://higgsfield.ai/blog/higgsfield-api |
| Higgsfield, Hailuo 2.3 | $0.0117/s (sale) or $0.0467/s (list) | not read | yes | not read | same | same | https://higgsfield.ai/higgsfield-api |
| Higgsfield, LTX 2.5 Fast | $0.09/s | 10 s | yes | yes | same | same | https://higgsfield.ai/higgsfield-api |
| Higgsfield, Seedance 2.5 | $0.144/s (sale), $0.2057/s (orig) | 30 s | yes | yes (`end_image_url`) | same | same | https://higgsfield.ai/higgsfield-api |
| Alibaba Model Studio, Wan 2.7 | $0.10/s at 720P (Singapore) | not read | yes | not read | REST | not read | https://www.alibabacloud.com/help/en/model-studio/wan2-7-i2v |
| MiniMax API, Hailuo 2.3 Fast | $0.19 per 6 s at 768P | 10 s | yes | not supported on Replicate-hosted version, API not read | REST | not read | https://platform.minimax.io/docs/guides/pricing-paygo |
| Replicate, Wan 2.1 I2V (old) | $0.09/s at 480p, $0.25/s at 720p | n/a | yes | n/a | `replicate` and REST | billing set-up needed | https://replicate.com/pricing |
| Self-host, RunPod RTX 4090 | $0.89/h | n/a | n/a | n/a | n/a | account and deposit (minimum UNVERIFIED) | https://www.runpod.io/pricing |
| Self-host, Modal A100 80GB | $0.000694/s (about $2.50/h), $30/mo free credit | n/a | n/a | n/a | n/a | n/a | https://modal.com/pricing |

---

## UNVERIFIED list

Pricing and quality
- Output quality, motion realism and face or text fidelity of every model. No primary source shows this; the bake-off is the only way to know.
- Higgsfield's current real per-second prices. Two of its own pages disagree and the per-model docs show none; the "estimate endpoint" is named only on a help page, exact path unknown. The sale end date is unknown.
- Higgsfield $15 sign-up credit conditions (business email, card) for an individual in Jordan.
- Kling direct API pricing and packages, BytePlus ModelArk Seedance pricing (both pages returned only shells).
- MiniMax direct H3 pricing; minimum top-up, payment methods and regions for MiniMax, Alibaba, Luma, Runway, Replicate.
- Replicate per-second prices for current models (Wan 2.2/2.7, Kling, Seedance, Veo, Hailuo).
- Luma Ray 3.2 prices (table and FAQ contradict each other); duration options other than 5 and 10 s; request format of `start_frame`.
- fal: minimum credit purchase, new-account free credits, whether webhook payloads carry a signature, and the real resolution behind the $0.025 and $0.05 H3 rows on fal's pricing page.
- Runway starting usage tier and its limits; gen4_turbo exact allowed durations beyond "2 to 10".
- Alibaba Wan 2.7: durations, first and last frame, async pattern, free quota, account approval.

Region and payment (Jordan)
- Whether a Jordanian bank card is accepted by Higgsfield, fal, Runway, Luma, Replicate, MiniMax or Alibaba. No source states a restriction or an approval. Only Google's rules are known: prepaid cards and 2FA-required debit cards are rejected [G5].
- Whether Google Cloud Billing supports a Jordan billing address; the currency table has no Jordan row (inconclusive) [G7].
- Jordan's status under the US-embargo representations in Higgsfield and fal terms. Neither names countries and I did not check a government sanctions list.
- Whether Veo image-to-video in MENA blocks photos of children (Google only says `allow_adult` is the sole option).
- Whether Higgsfield's "we use content to improve our models" statement applies to API traffic.

Technical
- Higgsfield base URL: `api.higgsfield.ai` (most pages) vs `platform.higgsfield.ai` (video guide).
- Higgsfield Kling 2.6 last-frame support (schema shows none) and the Hailuo 2.3 schema.
- HunyuanVideo-I2V (v1) license text (only the 1.5 repo LICENSE was read).
- Wan 2.2 I2V-A14B timings and LTX-2 VRAM/time (cards give no readable numbers); H100/A100 time per clip for HunyuanVideo-I2V v1 beyond the one 720p figure.
- Whether Wan 2.5/2.6/2.7/3.0 have open weights (only 10 of 27 Wan-AI Hugging Face models were visible).
- FFmpeg `xfade` documentation text (the official pages could not be fetched). The recipe above was tested locally on synthetic clips only, not on real model output.
- RunPod: the page shows one price per GPU with no secure-versus-community split, and minimum deposit is not stated. Vast.ai live prices are not in the page text. Modal credit eligibility for a new card-less account is not stated.
- Gemini Omni Flash image-to-video support and its exact price per resolution.

---

## Sources index (all seen 2026-10-17)

Higgsfield
- [H1] https://docs.higgsfield.ai/docs/index.md
- [H2] https://docs.higgsfield.ai/docs/guides/video.md
- [H3] https://docs.higgsfield.ai/docs/help/faq.md
- [H4] https://docs.higgsfield.ai/docs/how-to/webhooks.md
- [H5] https://docs.higgsfield.ai/docs/how-to/sdk.md
- [H6] https://docs.higgsfield.ai/docs/how-to/introduction.md
- [H7] https://docs.higgsfield.ai/docs/models/seedance-2-5/image-to-video.md
- [H8] https://docs.higgsfield.ai/docs/models/kling-2-6/pro-image-to-video.md
- [H9] https://docs.higgsfield.ai/docs/models/wan-2-6/image-to-video.md
- [H10] https://docs.higgsfield.ai/docs/models/ltx-2-5/image-to-video-fast.md
- [H11] https://docs.higgsfield.ai/docs/models/video-generation.md (and /hailuo-2-3.md)
- [H12] https://docs.higgsfield.ai/docs/concepts/requests.md
- [H13] https://higgsfield.ai/creator-hub/help-center/integrations/what-is-the-higgsfield-api
- [H14] https://higgsfield.ai/higgsfield-api
- [H15] https://higgsfield.ai/blog/higgsfield-api and https://higgsfield.ai/blog/generate-ai-videos-higgsfield-api
- [H16] https://higgsfield.ai/terms-of-use-agreement
- [H17] https://higgsfield.ai/blog/terms-of-use-privacy-policy-update

fal.ai
- [F1] https://fal.ai/docs/documentation/model-apis/pricing
- [F2] https://fal.ai/docs/documentation/model-apis/faq.md
- [F3] https://fal.ai/docs/documentation/model-apis/concurrency-limits
- [F4] https://www.fal.ai/legal/terms-of-service
- [F5] https://fal.ai/pricing
- [F6] https://fal.ai/docs/documentation/model-apis/inference/queue.md
- [F7] https://fal.ai/models/fal-ai/kling-video/v2.5-turbo/pro/image-to-video/llms.txt
- [F8] https://fal.ai/docs/documentation/agent/access-and-pricing.md
- [F9] https://fal.ai/models/minimax/h3-max-turbo/image-to-video/llms.txt and https://fal.ai/models/minimax/h3-max/image-to-video/llms.txt
- [F10] https://fal.ai/models/fal-ai/ltx-2/image-to-video/fast/llms.txt
- [F11] https://fal.ai/models/fal-ai/ltx-2/image-to-video/fast
- [F12] https://fal.ai/models/fal-ai/wan/v2.2-a14b/image-to-video/llms.txt
- [F13] https://fal.ai/models/fal-ai/wan/v2.7/image-to-video/llms.txt
- [F14] https://fal.ai/models/fal-ai/minimax/hailuo-2.3/standard/image-to-video/llms.txt
- [F15] https://fal.ai/explore/image-to-video-apis

Google
- [G1] https://ai.google.dev/gemini-api/docs/pricing.md.txt (and https://ai.google.dev/gemini-api/docs/pricing)
- [G2] https://ai.google.dev/gemini-api/docs/veo
- [G3] https://ai.google.dev/gemini-api/docs/available-regions
- [G4] https://ai.google.dev/gemini-api/docs/billing
- [G5] https://docs.cloud.google.com/billing/docs/how-to/payment-methods
- [G6] https://discuss.ai.google.dev/t/veo-3-1-lite-pricing-shows-0-05-per-video-but-actually-costs-8-times-more/143844 (user forum post, non-primary)
- [G7] https://docs.cloud.google.com/billing/docs/resources/currency

Runway, Luma, Replicate, Alibaba, MiniMax
- [R1] https://docs.dev.runwayml.com/guides/pricing.md
- [R2] https://docs.dev.runwayml.com/api.md
- [R3] https://docs.dev.runwayml.com/guides/setup.md
- [R4] https://docs.dev.runwayml.com/usage/tiers.md
- [R5] https://docs.dev.runwayml.com/ai-context.md
- [R6] https://docs.dev.runwayml.com/guides/using-the-api/
- [L1] https://lumalabs.ai/api/pricing
- [L2] https://docs.agents.lumalabs.ai/
- [L3] https://lumalabs.ai/api
- [P1] https://replicate.com/pricing
- [P2] https://replicate.com/docs/topics/predictions/rate-limits
- [A1] https://www.alibabacloud.com/help/en/model-studio/wan2-7-i2v
- [M1] https://platform.minimax.io/docs/guides/pricing-paygo

Open-source and GPU rent
- [W1] https://github.com/Wan-Video/Wan2.2
- [W2] https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B
- [W3] https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B
- [W4] https://huggingface.co/Wan-AI
- [O1] https://static.lightricks.com/legal/ltx-2-open-weights-license-0.X.pdf
- [O2] https://huggingface.co/Lightricks/LTX-2.3
- [O3] https://github.com/Lightricks/LTX-2
- [T1] https://huggingface.co/tencent/HunyuanVideo-I2V
- [T2] https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/LICENSE
- [T3] https://huggingface.co/tencent/HunyuanVideo-1.5
- [N1] https://www.runpod.io/pricing
- [N2] https://modal.com/pricing
- [N3] https://vast.ai/pricing
