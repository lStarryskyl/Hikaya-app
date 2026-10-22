# Hikaya (حكاية)

AI-augmented heritage storytelling for Jordan. People record stories in Jordanian dialect, Modern Standard Arabic or English. The app transcribes, polishes, translates and narrates them, pins them on a map, and publishes them to a community feed.

This is a demo build. Read `docs/DECISIONS.md` for what is real, what is mock and why.

## Layout

| Folder | What it is |
| --- | --- |
| `web/` | React 18, Vite, TypeScript, Tailwind frontend |
| `api/` | FastAPI backend: job queue, worker, accounts |
| `docs/DECISIONS.md` | Scope and decisions, the source of truth |
| `docs/research/` | Provider research with sources and prices |
| `docs/design/` | Visily design export |

## Run everything

```bash
cp .env.example .env      # then set SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD (and the reviewer pair)
docker compose up --build
```

Open http://localhost:5173. Sign up as a member, or sign in with the staff account you put in `.env`. The API is on http://localhost:8000 (`/health`, `/docs`).

## Develop without Docker

```bash
# API: needs PostgreSQL 16 with a `hikaya` database and the `hikaya` role from .env.example
cd api && pip install -r requirements-dev.txt
alembic upgrade head && python -m app.seed_staff && uvicorn app.main:app --reload
python -m app.worker            # in a second terminal
pytest                          # needs a `hikaya_test` database

# Web: proxies /api to localhost:8000
cd web && npm ci && npm run dev
```

The feed, map and story screens still show mock data. The backend replaces it phase by phase.

## Secrets

This repository is public. Never commit keys. Copy `.env.example` to `.env` and fill it in locally.
