# Hikaya (حكاية)

AI-augmented heritage storytelling for Jordan. People record stories in Jordanian dialect, Modern Standard Arabic or English. The app transcribes, polishes, translates and narrates them, pins them on a map, and publishes them to a community feed.

This is a demo build. Read `docs/DECISIONS.md` for what is real, what is mock and why.

## Layout

| Folder | What it is |
| --- | --- |
| `web/` | React 18, Vite, TypeScript, Tailwind frontend |
| `api/` | FastAPI backend (added in phase 1) |
| `docs/DECISIONS.md` | Scope and decisions, the source of truth |
| `docs/research/` | Provider research with sources and prices |
| `docs/design/` | Visily design export |

## Run the frontend alone

```bash
cd web
npm ci
npm run dev
```

It currently runs on mock data. The backend replaces the mock data phase by phase.

## Secrets

This repository is public. Never commit keys. Copy `.env.example` to `.env` and fill it in locally.
