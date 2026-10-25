"""A deliberately simulated checkout: no card details, payment service, or real charge."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.config import get_settings
from app.db import get_session
from app.models import CheckoutAttempt, Role, User

router = APIRouter(tags=["premium"])
SAMPLE_DIR = Path(__file__).resolve().parents[1] / "seed" / "videos"
SAMPLES = [
    {
        "id": "wan-light",
        "title": "AI lighting study",
        "description": "Lighting and atmosphere examples from Wan's official model demonstration.",
        "credit": "Wan 2.2 team",
        "source_url": "https://github.com/Wan-Video/Wan2.2",
        "duration_seconds": 6,
    },
    {
        "id": "wan-camera",
        "title": "AI camera study",
        "description": "Camera framing examples from Wan's official model demonstration.",
        "credit": "Wan 2.2 team",
        "source_url": "https://github.com/Wan-Video/Wan2.2",
        "duration_seconds": 6,
    },
]
FEATURES = [
    {"id": "stories", "label": "Record and publish stories", "free": True, "premium": True},
    {"id": "discovery", "label": "Search and nearby discovery", "free": True, "premium": True},
    {"id": "narration", "label": "Narration and photo slideshows", "free": True, "premium": True},
    {"id": "ai_video", "label": "AI video previews", "free": False, "premium": True},
]


class CheckoutIn(BaseModel):
    request_id: str = Field(min_length=1, max_length=80)
    scenario: Literal["success", "failure"] = "success"


def checkout_out(attempt: CheckoutAttempt) -> dict:
    return {
        "id": str(attempt.id),
        "status": attempt.status,
        "sandbox": True,
        "message": "No money is charged. This is a demo checkout.",
    }


@router.get("/plans")
async def plans() -> dict:
    return {"features": FEATURES, "sandbox": True}


@router.post("/billing/checkout", status_code=201)
async def checkout(
    body: CheckoutIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    old = (
        await session.execute(
            select(CheckoutAttempt).where(
                CheckoutAttempt.user_id == user.id, CheckoutAttempt.request_id == body.request_id
            )
        )
    ).scalar_one_or_none()
    if old:
        return checkout_out(old)
    attempt = CheckoutAttempt(
        user_id=user.id,
        request_id=body.request_id,
        scenario=body.scenario,
        complete_at=datetime.now(UTC) + timedelta(seconds=get_settings().dummy_checkout_seconds),
    )
    session.add(attempt)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "This checkout was already started. Please refresh.") from None
    return checkout_out(attempt)


@router.get("/billing/checkout/{attempt_id}")
async def checkout_status(
    attempt_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    attempt = (
        await session.execute(
            select(CheckoutAttempt)
            .where(CheckoutAttempt.id == attempt_id, CheckoutAttempt.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not attempt:
        raise HTTPException(404, "Checkout not found.")
    if attempt.status == "processing" and datetime.now(UTC) >= attempt.complete_at:
        attempt.status = "succeeded" if attempt.scenario == "success" else "failed"
        if attempt.status == "succeeded":
            user.plan = "premium"
        await session.commit()
    return checkout_out(attempt)


@router.get("/video-samples")
async def samples() -> list:
    return [
        {
            **sample,
            "poster_url": f"/api/v1/video-samples/{sample['id']}/poster",
            "video_url": f"/api/v1/video-samples/{sample['id']}/video",
        }
        for sample in SAMPLES
    ]


def sample_path(sample_id: str, extension: str) -> Path:
    if sample_id not in {sample["id"] for sample in SAMPLES}:
        raise HTTPException(404, "Sample not found.")
    path = SAMPLE_DIR / f"{sample_id}.{extension}"
    if not path.is_file():
        raise HTTPException(404, "This demo sample is not installed.")
    return path


@router.get("/video-samples/{sample_id}/poster")
async def poster(sample_id: str) -> FileResponse:
    return FileResponse(sample_path(sample_id, "webp"), media_type="image/webp")


@router.get("/video-samples/{sample_id}/video")
async def sample_video(sample_id: str, user: User = Depends(current_user)) -> FileResponse:
    if user.plan != "premium" and user.role not in {Role.REVIEWER, Role.ADMIN}:
        raise HTTPException(403, "Premium unlocks AI video previews.")
    return FileResponse(
        sample_path(sample_id, "webm"),
        media_type="video/webm",
        headers={"Cache-Control": "private, no-store"},
    )
