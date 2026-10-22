import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text

from app.auth import current_user, require_roles
from app.models import Role, User
from app.seed_staff import StaffSeed, seed_staff

PASSWORD = "correct horse battery"


async def signup(client, email="salma@example.com", password=PASSWORD, name="Salma K.", **extra):
    return await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "display_name": name, **extra},
    )


async def login(client, email="salma@example.com", password=PASSWORD):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_signup_creates_a_member_and_signs_them_in(client):
    response = await signup(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "salma@example.com"
    assert body["display_name"] == "Salma K."
    assert body["role"] == "member"
    assert "password" not in response.text and "hash" not in response.text

    cookie = response.headers["set-cookie"].lower()
    assert "hikaya_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == body


async def test_signup_normalises_the_email(client):
    response = await signup(client, email="  Salma@Example.COM ")
    assert response.status_code == 201
    assert response.json()["email"] == "salma@example.com"


async def test_duplicate_email_is_refused_in_any_case(client):
    assert (await signup(client)).status_code == 201
    again = await signup(client, email="SALMA@example.com")
    assert again.status_code == 409


async def test_signup_cannot_choose_a_role(client):
    response = await signup(client, role="admin")
    assert response.status_code == 201
    assert response.json()["role"] == "member"


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},
        {"password": "x" * 129},
        {"email": "not-an-email"},
        {"email": "a@b"},
        {"name": ""},
        {"name": "n" * 61},
    ],
)
async def test_signup_rejects_invalid_input(client, overrides):
    response = await signup(client, **overrides)
    assert response.status_code == 422


async def test_password_is_stored_hashed(client, session):
    await signup(client)
    stored = (await session.execute(text("SELECT password_hash FROM users"))).scalar_one()
    assert stored.startswith("scrypt$")
    assert PASSWORD not in stored


async def test_login_works_and_wrong_credentials_look_identical(client):
    await signup(client)
    client.cookies.clear()

    ok = await login(client)
    assert ok.status_code == 200
    assert ok.json()["email"] == "salma@example.com"
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    client.cookies.clear()
    wrong_password = await login(client, password="wrong password here")
    unknown_email = await login(client, email="nobody@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert "set-cookie" not in wrong_password.headers


async def test_login_is_case_insensitive_on_email(client):
    await signup(client)
    client.cookies.clear()
    assert (await login(client, email="SALMA@example.com")).status_code == 200


async def test_me_needs_a_session(client):
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_logout_ends_the_session_for_good(client):
    await signup(client)
    token = client.cookies.get("hikaya_session")

    out = await client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    # The old token no longer works even if someone kept a copy.
    client.cookies.set("hikaya_session", token)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_logout_without_a_session_is_fine(client):
    assert (await client.post("/api/v1/auth/logout")).status_code == 204


async def test_expired_session_is_refused(client, session):
    await signup(client)
    await session.execute(text("UPDATE auth_sessions SET expires_at = now() - interval '1 minute'"))
    await session.commit()
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_a_garbage_cookie_is_refused(client):
    client.cookies.set("hikaya_session", "not-a-real-token")
    assert (await client.get("/api/v1/auth/me")).status_code == 401


def role_app() -> FastAPI:
    """A throwaway app that uses the role guard the way later phases will."""
    app = FastAPI()
    staff_guard = require_roles(Role.REVIEWER, Role.ADMIN)
    admin_guard = require_roles(Role.ADMIN)

    @app.get("/anyone-signed-in")
    async def anyone(user: User = Depends(current_user)):
        return {"role": user.role}

    @app.get("/staff-only")
    async def staff_only(user: User = Depends(staff_guard)):
        return {"role": user.role}

    @app.get("/admin-only")
    async def admin_only(user: User = Depends(admin_guard)):
        return {"role": user.role}

    return app


async def test_role_guards(client, sessionmaker):
    await signup(client, email="member@example.com")
    member_token = client.cookies.get("hikaya_session")
    await seed_staff(
        sessionmaker,
        [
            StaffSeed("reviewer@example.com", PASSWORD, Role.REVIEWER, "Reviewer"),
            StaffSeed("admin@example.com", PASSWORD, Role.ADMIN, "Admin"),
        ],
    )
    client.cookies.clear()
    await login(client, email="reviewer@example.com")
    reviewer_token = client.cookies.get("hikaya_session")
    client.cookies.clear()
    await login(client, email="admin@example.com")
    admin_token = client.cookies.get("hikaya_session")

    transport = httpx.ASGITransport(app=role_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:

        async def status(path, token):
            c.cookies.clear()
            if token:
                c.cookies.set("hikaya_session", token)
            return (await c.get(path)).status_code

        assert await status("/anyone-signed-in", None) == 401
        assert await status("/anyone-signed-in", member_token) == 200
        assert await status("/staff-only", None) == 401
        assert await status("/staff-only", member_token) == 403
        assert await status("/staff-only", reviewer_token) == 200
        assert await status("/staff-only", admin_token) == 200
        assert await status("/admin-only", reviewer_token) == 403
        assert await status("/admin-only", admin_token) == 200


async def test_seed_creates_staff_who_can_sign_in(client, sessionmaker):
    created = await seed_staff(
        sessionmaker, [StaffSeed("Admin@Example.com", PASSWORD, Role.ADMIN, "Hikaya Admin")]
    )
    assert created == ["admin@example.com"]
    response = await login(client, email="admin@example.com")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_seed_is_idempotent_and_keeps_existing_passwords(client, sessionmaker):
    entry = StaffSeed("admin@example.com", PASSWORD, Role.ADMIN, "Hikaya Admin")
    assert await seed_staff(sessionmaker, [entry]) == ["admin@example.com"]
    changed = StaffSeed("admin@example.com", "a different password", Role.ADMIN, "Hikaya Admin")
    assert await seed_staff(sessionmaker, [changed]) == []
    assert (await login(client, email="admin@example.com")).status_code == 200  # old password
    client.cookies.clear()
    assert (
        await login(client, email="admin@example.com", password="a different password")
    ).status_code == 401


async def test_seed_promotes_an_existing_member(client, sessionmaker):
    await signup(client, email="boss@example.com")
    await seed_staff(sessionmaker, [StaffSeed("boss@example.com", PASSWORD, Role.ADMIN, "Boss")])
    assert (await client.get("/api/v1/auth/me")).json()["role"] == "admin"


async def test_seed_ignores_unset_entries():
    from app.config import Settings
    from app.seed_staff import staff_from_settings

    nothing = Settings(_env_file=None)
    assert staff_from_settings(nothing) == []

    half = Settings(_env_file=None, seed_admin_email="a@example.com", seed_admin_password="")
    assert staff_from_settings(half) == []

    short = Settings(_env_file=None, seed_admin_email="a@example.com", seed_admin_password="short")
    assert staff_from_settings(short) == []

    both = Settings(
        _env_file=None,
        seed_admin_email="a@example.com",
        seed_admin_password=PASSWORD,
        seed_reviewer_email="r@example.com",
        seed_reviewer_password=PASSWORD,
    )
    assert [s.role for s in staff_from_settings(both)] == [Role.ADMIN, Role.REVIEWER]
