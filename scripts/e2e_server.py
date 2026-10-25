"""Run the complete, deterministic demo stack for browser tests against a disposable DB."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
url = os.environ.get("E2E_DATABASE_URL")
if not url:
    raise SystemExit(
        "Set E2E_DATABASE_URL to a disposable PostgreSQL database before browser tests."
    )
env = {
    **os.environ,
    "DATABASE_URL": url,
    "MEDIA_DIR": str(ROOT / "api/data/e2e-media"),
    "ENV": "test",
    "STT_PROVIDER": "fake",
    "TTS_PROVIDER": "fake",
    "LLM_PROVIDER": "fake",
    "VOICE_CLONE_PROVIDER": "fake",
    "VIDEO_PROVIDER": "fake",
    "ENABLE_AI_VIDEO": "true",
    "LIVE_AI_ENABLED": "false",
    "DUMMY_CHECKOUT_SECONDS": "0.4",
    "WORKER_POLL_SECONDS": "0.2",
    "SEED_ADMIN_EMAIL": "staff-e2e@example.com",
    "SEED_ADMIN_PASSWORD": "e2e-only-staff-password",
    "FAL_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "AZURE_OPENAI_API_KEY": "",
    "AZURE_SPEECH_KEY": "",
    "HIGGSFIELD_KEY_ID": "",
    "HIGGSFIELD_KEY_SECRET": "",
    "GOOGLE_ACCESS_TOKEN": "",
    "GOOGLE_CLOUD_PROJECT": "",
    "CUSTOM_VIDEO_ENDPOINT": "",
    "VITE_API_PROXY_TARGET": "http://127.0.0.1:8001",
}
fixture = ROOT / "web/e2e/fixtures/voice.wav"
fixture.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(
    [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=330:duration=31",
        "-ac",
        "1",
        "-y",
        str(fixture),
    ],
    check=True,
)
for command in (
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    [sys.executable, "-m", "app.seed_staff"],
    [sys.executable, "-m", "app.seed_demo"],
):
    subprocess.run(command, cwd=ROOT / "api", env=env, check=True)
children = []


def stop(_signal, _frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    for command, cwd in [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
            ],
            ROOT / "api",
        ),
        ([sys.executable, "-m", "app.worker"], ROOT / "api"),
        (
            [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "4173",
                "--strictPort",
            ],
            ROOT / "web",
        ),
    ]:
        children.append(subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True))
    while all(child.poll() is None for child in children):
        time.sleep(0.25)
    raise SystemExit("A demo test server stopped unexpectedly.")
except KeyboardInterrupt:
    pass
finally:
    for child in children:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
    for child in children:
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
