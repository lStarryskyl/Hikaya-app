"""FastAPI application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import router as auth_router
from app.config import get_settings
from app.db import dispose_engine, get_session
from app.discover import router as discover_router
from app.photos import PhotoLimit, photo_limit_response
from app.photos import media_router as story_photo_media_router
from app.places import media_router as place_media_router
from app.stories import me_router, media_router
from app.stories import router as stories_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


app = FastAPI(title="Hikaya API", version="0.1.0", lifespan=lifespan)

app.add_exception_handler(PhotoLimit, photo_limit_response)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def health(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Returns 200 only when the database answers."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "degraded", "db": "down"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok"})


api_v1 = APIRouter(prefix="/api/v1")
api_v1.add_api_route("/health", health, methods=["GET"])
api_v1.include_router(auth_router)
api_v1.include_router(discover_router)
api_v1.include_router(stories_router)
api_v1.include_router(me_router)

app.include_router(api_v1)
app.include_router(place_media_router)
app.include_router(story_photo_media_router)
app.include_router(media_router)
# A plain /health for container health checks.
app.add_api_route("/health", health, methods=["GET"], include_in_schema=False)
