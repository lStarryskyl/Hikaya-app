#!/usr/bin/env bash
# Writes .env from .env.example, ready for ElevenLabs:
#   - transcription, narration and voice cloning on ElevenLabs,
#   - live AI on (paid calls still stop at the SPEND_CAP_USD_* limits),
#   - staff accounts admin@hikaya.test and reviewer@hikaya.test with random passwords.
# Then add ELEVENLABS_API_KEY and the two ELEVENLABS_VOICE_* IDs to .env.
# Never overwrites an existing .env. .env is git-ignored, so keys stay on this machine.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -e .env ]; then
  echo ".env already exists, so it was left unchanged. Edit it directly." >&2
  exit 1
fi

# 24 hex characters from the system's random source (od reads exactly 12 bytes).
password() { od -An -tx1 -N12 /dev/urandom | tr -d ' \n'; }

# Each rule replaces a setting's value and keeps any comment after it. Plain sed, no -i,
# so it behaves the same with GNU sed (Linux) and BSD sed (macOS).
sed \
  -e "s|^\(STT_PROVIDER=\)[^ ]*|\1elevenlabs|" \
  -e "s|^\(TTS_PROVIDER=\)[^ ]*|\1elevenlabs|" \
  -e "s|^\(VOICE_CLONE_PROVIDER=\)[^ ]*|\1elevenlabs|" \
  -e "s|^\(LIVE_AI_ENABLED=\)[^ ]*|\1true|" \
  -e "s|^\(SEED_ADMIN_EMAIL=\)[^ ]*|\1admin@hikaya.test|" \
  -e "s|^\(SEED_ADMIN_PASSWORD=\)[^ ]*|\1$(password)|" \
  -e "s|^\(SEED_REVIEWER_EMAIL=\)[^ ]*|\1reviewer@hikaya.test|" \
  -e "s|^\(SEED_REVIEWER_PASSWORD=\)[^ ]*|\1$(password)|" \
  .env.example > .env.tmp
mv .env.tmp .env
chmod 600 .env

echo "Wrote .env. Fill in ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ARABIC and ELEVENLABS_VOICE_ENGLISH."
