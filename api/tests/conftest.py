import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Point the app at the test database before anything imports the settings.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://hikaya:hikaya@localhost:5432/hikaya_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Media written by tests goes to a throwaway folder.
os.environ["MEDIA_DIR"] = tempfile.mkdtemp(prefix="hikaya-test-media-")

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import dispose_engine, get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402

API_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Run every migration down and up, so a broken migration fails the suite."""
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run([sys.executable, "-m", "alembic", *args], cwd=API_DIR, env=env, check=True)


@pytest_asyncio.fixture
async def sessionmaker():
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(
            text(
                "TRUNCATE jobs, pipeline_steps, text_layers, assets, stories, auth_sessions, users"
                " CASCADE"
            )
        )
        await session.commit()
    yield maker
    # The engine is bound to this test's event loop, so drop it after every test.
    await dispose_engine()


@pytest_asyncio.fixture
async def session(sessionmaker):
    async with sessionmaker() as s:
        yield s


@pytest_asyncio.fixture
async def client(sessionmaker):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
