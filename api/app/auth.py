"""Sign-up, sign-in and the dependencies other routes use to find the current user.

A signed-in browser holds an httpOnly cookie with a random token. The database stores
only the token's hash, so logging out (or expiry) really ends the session.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import AuthSession, Role, User
from app.security import hash_password, hash_token, new_session_token, verify_password

COOKIE_NAME = "hikaya_session"

router = APIRouter(prefix="/auth", tags=["auth"])

Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class SignupIn(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    display_name: DisplayName


class LoginIn(BaseModel):
    # No length rules here: a wrong password is just a wrong password.
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: str


@cache
def _dummy_hash() -> str:
    """Checked when the email is unknown, so both failures take about the same time."""
    return hash_password("not-a-real-password")


async def _start_session(session: AsyncSession, user: User, response: Response) -> None:
    settings = get_settings()
    ttl = timedelta(days=settings.session_ttl_days)
    token = new_session_token()
    session.add(
        AuthSession(
            user_id=user.id, token_hash=hash_token(token), expires_at=datetime.now(UTC) + ttl
        )
    )
    await session.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/signup", status_code=201, response_model=UserOut)
async def signup(
    body: SignupIn, response: Response, session: AsyncSession = Depends(get_session)
) -> User:
    password_hash = await asyncio.to_thread(hash_password, body.password)
    user = User(email=body.email, display_name=body.display_name, password_hash=password_hash)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "That email is already registered.") from None
    await _start_session(session, user, response)
    return user


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginIn, response: Response, session: AsyncSession = Depends(get_session)
) -> User:
    email = body.email.strip().lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    stored = user.password_hash if user else _dummy_hash()
    ok = await asyncio.to_thread(verify_password, body.password, stored)
    if user is None or not ok:
        raise HTTPException(401, "Wrong email or password.")
    await session.execute(delete(AuthSession).where(AuthSession.expires_at < func.now()))
    await _start_session(session, user, response)
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await session.execute(
            delete(AuthSession).where(AuthSession.token_hash == hash_token(token))
        )
        await session.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


async def current_user_optional(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    result = await session.execute(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.expires_at > func.now())
    )
    return result.scalar_one_or_none()


async def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in first.")
    return user


def require_roles(*roles: Role):
    """Dependency factory: `Depends(require_roles(Role.REVIEWER, Role.ADMIN))`."""
    allowed = {role.value for role in roles}

    async def guard(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(403, "Not allowed.")
        return user

    return guard


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user
