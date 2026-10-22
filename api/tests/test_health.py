import httpx
import pytest

from app.db import get_session
from app.main import app


@pytest.fixture
async def client(sessionmaker):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_health_ok(client):
    for path in ("/health", "/api/v1/health"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "db": "ok"}


async def test_health_is_503_when_database_is_down(client):
    class BrokenSession:
        async def execute(self, *_args, **_kwargs):
            raise ConnectionError("database is down")

    async def broken_session():
        yield BrokenSession()

    app.dependency_overrides[get_session] = broken_session
    response = await client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "down"}
    # No internal error text leaks to the caller.
    assert "database is down" not in response.text
