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

## Self-hosted Cog

Deploy a video predictor whose input schema accepts `prompt`, `image` (data URI),
`aspect_ratio`, and `seed`, and whose output is an MP4 data URI or a same-origin file URL.
Point `CUSTOM_VIDEO_ENDPOINT` at the server's base URL, not `/predictions`.
The adapter uses `PUT /predictions/<stable-id>` synchronously with a 480-second timeout.
This runs in the background worker; browser requests remain quick. Cog does not support
GET polling for its asynchronous predictions, so the adapter does not invent that route.

Contract: https://cog.run/http/
