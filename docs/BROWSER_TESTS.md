# Demo browser verification

Requires Node 22, Python 3.12 with `api/requirements-dev.txt` installed, FFmpeg, and a disposable PostgreSQL database. Never point this suite at a production database: it migrates and seeds the database and creates test accounts, checkout attempts, voices and videos.

From `web/`:

```bash
npm ci
npx playwright install --with-deps chromium
export E2E_DATABASE_URL=postgresql+asyncpg://hikaya:hikaya@127.0.0.1:5432/hikaya_e2e
# Optional when Python is in a virtual environment:
export HIKAYA_PYTHON=/absolute/path/to/venv/bin/python
npm run test:e2e
```

Playwright starts the API, PostgreSQL-backed worker and Vite automatically on ports 8001 and 4173, then stops them. Use an empty disposable database for a clean run. Local reruns use unique test accounts and generation inputs. `npm run test:e2e:report` opens the HTML report.

The three Chromium journeys cover:

- Home search, nearby permission granted, English/Arabic direction switching, signup, failed and successful dummy checkout, premium sample playback, staff consent and audio upload, queued fake voice cloning, queued fake video generation and playback.
- Location permission denied while ordinary search remains usable, translated Arabic feed tabs, a 375-pixel viewport with no horizontal overflow, and an automated accessibility scan.
- Anonymous and member access denied to staff voice/video endpoints, including attempts to supply a staff role during signup.

The staff console also receives an axe WCAG A/AA scan. Automated scans cover these rendered states; they are not a complete WCAG certification. Recording consent uses a generated 31-second WAV upload, avoiding CI microphone hardware dependencies. Manual microphone recording should also be checked on deployment browsers.

The test server forces fake providers and disables live AI; browser requests outside localhost are blocked and the map style is intercepted. Playback uses small local, attributed Wan demo excerpts. No paid provider is called. Live adapter contracts have separate mocked HTTP tests; credentials and a controlled live acceptance run are still needed before production use.

`.github/workflows/demo-browser.yml` runs the same journey with a PostgreSQL service and uploads traces, screenshots, video and server logs on failure. The main CI workflow separately runs type checks, lint, formatting, frontend unit tests/build and backend tests.
