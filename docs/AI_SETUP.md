# OpenAI + ElevenLabs setup

This setup needs no Azure account. Copy `.env.example` to `.env` in the repository
root. Keep keys only in that file, which is excluded from Git.

```dotenv
STT_PROVIDER=elevenlabs
TTS_PROVIDER=elevenlabs
LLM_PROVIDER=openai
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ARABIC=
ELEVENLABS_VOICE_ENGLISH=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=4096
OPENAI_INPUT_USD_PER_MILLION=0
OPENAI_OUTPUT_USD_PER_MILLION=0
LIVE_AI_ENABLED=false
SPEND_CAP_USD_TOTAL=25
SPEND_CAP_USD_DAILY=10
```

Both ElevenLabs voice IDs are needed; the same accessible multilingual voice may
be used for both languages. `ELEVENLABS_VOICE_ID` from the older ELO prototype is
not this repository's setting. Copy that value into the Arabic and/or English
setting as appropriate. This app uses `LLM_PROVIDER`, not `LANGUAGE_PROVIDER`, and
`LIVE_AI_ENABLED`, not `USE_MOCK_AI`. Do not copy the older prototype's entire env.

Confirm OpenAI prices for the selected model and your account, then replace the
zero rates. Zero blocks paid OpenAI calls. Confirm the ElevenLabs rates already
listed in `.env.example` against your own plan too. Only then enable live AI and
restart API/worker. Account subscriptions, taxes and use outside this application
are not governed by its local spending ledger.

The worker runs Scribe transcription, aligned polishing/translation, moderation,
and ElevenLabs narration through the existing gateway. OpenAI uses the shared
card budget, so it competes with ElevenLabs/video for the $25 total allowance.
Requests have an output token limit and a conservative input reservation; errors
with uncertain billing keep a charge. Generated text must retain one segment per
input segment. Translation targets are English or MSA, never dialect. Moderation
returns the existing hate/violence/sexual/other_terrible labels with reasons, so the
existing hold-for-review flow continues unchanged.

No frontend or database changes are required. Azure remains available as an
alternative provider. Existing result caches remain valid; OpenAI uses a distinct
cache identity including its model and output limit.

## Verification notes (2026-11-01)

- The locally supplied OpenAI key passed a read-only model-access check (HTTP 200).
  This does not establish available billing credit or a successful generation.
- ElevenLabs account and voice reads returned HTTP 401. Check the full secret key,
  its permissions and resource access before enabling live generation.
- No paid generation calls were made. Keys are not included in this repository.
- Local provider contracts were tested with mocked HTTP. Full database/FFmpeg and
  frontend verification is delegated to the repository's existing GitHub CI.

Official references:
- https://developers.openai.com/api/docs/models/gpt-4.1-mini
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- https://elevenlabs.io/docs/api-reference/speech-to-text/convert
- https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
