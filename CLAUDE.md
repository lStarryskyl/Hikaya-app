# Hikaya

Heritage storytelling app for Jordan: people record stories in Jordanian dialect, Modern Standard Arabic or English, and the app transcribes, polishes, translates, narrates and publishes them to a feed and map. This is a one-off demo for a judging panel, not a launch. Read `docs/DECISIONS.md` first: it says what is real, what is mock and why.

## Layout

- `web/`: React 18, Vite, TypeScript, Tailwind. Currently mock-data driven; phases replace the mock data.
- `api/`: FastAPI, SQLAlchemy 2 async, asyncpg, Alembic, plain PostgreSQL 16.
- `docs/DECISIONS.md`: scope and decisions. Change it first when a decision changes.
- `docs/research/`: provider research with sources and prices.

## Commands

```bash
# Everything, in Docker (db, api, worker, web). App on http://localhost:5173, API on :8000
docker compose up --build

# Backend tests (needs a local PostgreSQL 16 with a hikaya_test database, or set TEST_DATABASE_URL)
cd api && pip install -r requirements-dev.txt && pytest
cd api && ruff check . && ruff format --check .

# Frontend
cd web && npm ci && npm run build
```

## Rules

1. Work one phase at a time and stop at its gate. The phases are scaffold, accounts, stories without AI, AI pipeline, search and right-to-left, governance.
2. Never call an AI provider inside a web request. Each AI step is a job in the Postgres queue (`api/app/jobs.py`) with an idempotency key, and records `provider_cost_usd`.
3. Paid calls must pass the spending ledger. Card-paid spending is capped at about 25 USD in total. Cache every provider result by a hash of its input.
4. Every provider sits behind one interface and is chosen by a setting (`STT_PROVIDER`, `TTS_PROVIDER`, `LLM_PROVIDER`, `VIDEO_PROVIDER`). Live AI calls are off unless `LIVE_AI_ENABLED=true`.
5. Schema changes go through Alembic migrations only. Write the failing test first, then the code.
6. Not used, on purpose: PostGIS, Redis, Celery, MinIO. Do not add them. Media lives on local disk behind a storage interface.
7. This repository is public. Never commit keys, `.env`, or the partner documents. Keys live only in `.env`.
8. If the plan and the code disagree, say so. Do not choose silently.
9. Finish each phase with the commands you ran and their output.

## Not built (out of scope)

Persona chat, reels, the 360 viewer, analytics dashboards, the visit planner, real payments, Google sign-in, TOTP, email verification, scaling.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `lStarryskyl/Hikaya-app`, through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
