# Video provider deployment

The browser calls `generateVideo(payload: VideoPromptPayload): Promise<VideoJobResult>`.
The API authorizes staff, snapshots story context and the input image, and queues work.
All adapters implement the server's `VideoProvider` interface. They share storage, cache,
job tracking and spending controls. No key or server endpoint is returned to the browser.

Set `ENABLE_AI_VIDEO=true`. `VIDEO_PROVIDER` chooses the initial selection; staff may select
another configured provider at runtime. Live adapters also require `LIVE_AI_ENABLED=true`.
The configuration endpoint reports missing settings without exposing their values.
Live calls have not been exercised with credentials; contract tests mock the provider HTTP layer.

| Provider | Settings | Behavior |
| --- | --- | --- |
| fake | no credentials | Replays the attributed local Wan sample; explicitly labelled offline demo |
| fal | FAL_KEY | Wan 2.2 image-to-video, data URI input, durable queue polling |
| higgsfield | HIGGSFIELD_KEY_ID, HIGGSFIELD_KEY_SECRET | Presigned image upload, Seedance 2.5 image-to-video, idempotent submission and polling |
| gemini | GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, GOOGLE_ACCESS_TOKEN | Veo 3.1 GA on Google Cloud, operation polling, inline bytes or authenticated Cloud Storage download |
| gemini_omni | GEMINI_API_KEY (Google AI Studio, paid tier) | Gemini Omni Flash through the Gemini API, background interaction, inline MP4 on completion |
| custom | CUSTOM_VIDEO_ENDPOINT, optional CUSTOM_VIDEO_TOKEN | Self-hosted Cog idempotent synchronous prediction in the background worker |

`VIDEO_ESTIMATE_USD` is a conservative per-job reservation for a paid provider, not an
advertised price. Set it for the chosen account/model before live use. Custom endpoints
use `CUSTOM_VIDEO_ESTIMATE_USD`; zero means locally free inference. The gateway still enforces
the configured card budget for a positive estimate. Unknown submission outcomes remain counted.

## Higgsfield

The selected model does not accept a seed or aspect-ratio parameter. The UI disables these
controls and states that framing follows the input photo. Unsupported values are normalized
out of the cache identity. Uploads use only returned storage headers, never the API credentials.
`HIGGSFIELD_MEDIA_HOSTS` allowlists upload/result domains. Add a host only after checking the
authenticated response for your account; unexpected hosts are refused.

Contracts checked 2026-10-25:
- https://docs.higgsfield.ai/docs/models/seedance-2-5/image-to-video.md
- https://docs.higgsfield.ai/docs/concepts/file-uploads.md
- https://docs.higgsfield.ai/docs/concepts/requests.md

## Google Veo

The Gemini API's Veo preview models were shut down on October 22, 2026. The `gemini` selection
therefore uses supported Google Cloud GA models (`veo-3.1-fast-generate-001` or
`veo-3.1-generate-001`), not the retired Gemini API preview route. A Gemini API key alone
cannot enable this adapter. Supply a server-side Google Cloud access token authorized for
Veo in the configured project; expired credentials result in a failed job, not a hidden fallback.

- Retirement notice: https://ai.google.dev/gemini-api/docs/video
- GA contract: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/video/generate-videos-from-text

## Gemini Omni Flash

Google's replacement for Veo in the Gemini API, so it works with a Google AI Studio key
(`GEMINI_API_KEY`). Omni Flash is on the paid tier only: the key's project needs billing, and a
free-tier key is refused (usually HTTP 429), which the job reports in plain words.

- Submit: `POST https://generativelanguage.googleapis.com/v1beta/interactions` with the key in
  the `x-goog-api-key` header, model `gemini-omni-1.2-flash`, the story photo (WebP, base64)
  and the prompt as `input`, `response_format` `{type: video, aspect_ratio, resolution: 720p,
  duration: 6s}` and `background: true`. Google answers at once with an interaction ID.
- Check: `GET .../interactions/<id>` once per check. `in_progress` waits for the next check;
  `completed` carries the MP4 as base64 in the `model_output` step (the GET always returns it
  inline); `failed` or `cancelled` fails the job.
- No seed: the console disables it. The aspect ratio (16:9 or 9:16) is sent.
- Cost: about 0.07 USD per second at 720p (5,792 output tokens per second at 12 USD per million).
  `GEMINI_OMNI_USD_PER_SECOND` (default 0.08) reserves 0.48 USD per 6-second video on the card
  budget; it is Omni's own rate, so `VIDEO_USD_PER_SECOND` does not apply.
- Videos include native audio and an invisible SynthID watermark. Google says languages other
  than English are not evaluated.

Contracts checked 2026-11-06:
- https://ai.google.dev/gemini-api/docs/omni
- https://ai.google.dev/gemini-api/docs/background-execution
- https://ai.google.dev/gemini-api/docs/pricing

## Narrated videos (up to a minute)

Staff choose "Narrated video" on the staff video page (`mode: "narrated"` on
`POST /api/v1/staff/videos`; `POST /api/v1/staff/videos/plan` shows the shots, length, lines
covered and estimated cost first). Offered for Gemini Omni Flash and the offline fake only.

- The soundtrack (the story's narration, in the default or a consenting cloned voice, or the
  storyteller's recording) is cut into shots of up to 15 s at line boundaries, up to
  `NARRATED_VIDEO_MAX_SECONDS` (60). Each shot's prompt is the English text spoken during it.
- Shot 1 starts from the story photo; each later shot starts from the frame where the previous
  one is cut and also gets a reference frame of the people from shot 1, so faces and clothes
  stay the same. Omni takes several images per request and the prompt says which is which.
- FFmpeg joins the shots (each cut or held to its planned length), lays the soundtrack over them
  with Omni's sound ducked underneath, stops the voice at the last covered line, holds the last
  frame for 0.6 s and burns in Arabic + English subtitles.
- Each shot is its own ledger entry. The whole estimate (and, on a retry, what is still to pay)
  must fit the caps before anything is queued. `POST /api/v1/staff/videos/<id>/retry` goes on
  from the failed shot; `{"confirm_resubmit": true}` sends an unconfirmed shot again.
- Live result (2026-11-06): a 53 s video of five shots (12/15/13/11/6 s) rendered in under six
  minutes for about 3.96 USD at Google's price.

## Self-hosted Cog

Deploy a video predictor whose input schema accepts `prompt`, `image` (data URI),
`aspect_ratio`, and `seed`, and whose output is an MP4 data URI or a same-origin file URL.
Point `CUSTOM_VIDEO_ENDPOINT` at the server's base URL, not `/predictions`.
The adapter uses `PUT /predictions/<stable-id>` synchronously with a 480-second timeout.
This runs in the background worker; browser requests remain quick. Cog does not support
GET polling for its asynchronous predictions, so the adapter does not invent that route.

Contract: https://cog.run/http/
