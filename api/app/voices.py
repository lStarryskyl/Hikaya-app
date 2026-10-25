"""Staff voice cloning with explicit, versioned speaker consent and private samples."""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import audio, gateway, jobs
from app.auth import require_roles
from app.config import get_settings
from app.db import get_session, get_sessionmaker
from app.errors import INTERNAL_PREFIX, UserFacingError
from app.handlers import handler
from app.models import Job, Role, User, VoiceClone
from app.providers.voices import VoiceCloner
from app.storage import TooLarge, get_storage

router = APIRouter(prefix="/staff/voices", tags=["voices"])
staff = require_roles(Role.REVIEWER, Role.ADMIN)
VERSION = "voice-consent-2026-10-25"
TEXT = (
    "I am the speaker in this sample and I control the rights to my voice. "
    "I explicitly allow Hikaya to store this sample, send it to its selected voice provider, "
    "and create a synthetic copy of my voice for heritage narration. I understand that this "
    "is separate from publishing a story and that a synthetic voice can resemble me."
)
TEXT_AR = (
    "أنا المتحدث في هذا التسجيل وأملك حقوق صوتي. أوافق صراحةً على حفظ العينة "
    "وإرسالها إلى مزوّد الصوت المختار لإنشاء نسخة اصطناعية من صوتي لسرد التراث. "
    "أفهم أن هذه الموافقة منفصلة عن نشر القصة، وأن الصوت الاصطناعي قد يشبه صوتي."
)


async def output(session: AsyncSession, voice: VoiceClone) -> dict:
    job = await session.get(Job, voice.job_id) if voice.job_id else None
    error = job.error if job else None
    if error and error.startswith(INTERNAL_PREFIX):
        error = "Voice cloning failed. Please contact the demo administrator."
    return {
        "id": str(voice.id),
        "speaker_name": voice.speaker_name,
        "status": job.status if job else "failed",
        "error": error,
        "demo": voice.provider == "fake",
        "requires_verification": voice.requires_verification,
        "voice_id": voice.provider_voice_id,
        "duration_ms": voice.duration_ms,
        "consent": voice.consent,
        "sample_url": f"/api/v1/staff/voices/{voice.id}/sample",
    }


@router.get("/consent")
async def statement(user: User = Depends(staff)) -> dict:
    return {
        "version": VERSION,
        "text": TEXT,
        "text_ar": TEXT_AR,
        "min_seconds": 30,
        "max_seconds": 60,
    }


@router.get("")
async def list_voices(
    user: User = Depends(staff), session: AsyncSession = Depends(get_session)
) -> list:
    voices = (
        await session.execute(select(VoiceClone).order_by(VoiceClone.created_at.desc()))
    ).scalars()
    return [await output(session, voice) for voice in voices]


@router.post("", status_code=202)
async def create_voice(
    file: UploadFile,
    speaker_name: Annotated[str, Form(min_length=1, max_length=80)],
    consent_version: Annotated[str, Form(max_length=80)],
    speaker_confirmed: Annotated[bool, Form()],
    rights_confirmed: Annotated[bool, Form()],
    use_confirmed: Annotated[bool, Form()],
    request_id: Annotated[str, Form(min_length=1, max_length=80)],
    locale: Annotated[str, Form()] = "en",
    user: User = Depends(staff),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if consent_version != VERSION or not all((speaker_confirmed, rights_confirmed, use_confirmed)):
        raise HTTPException(422, "Agree to all parts of the current voice consent statement.")
    if locale not in {"en", "ar"} or not speaker_name.strip():
        raise HTTPException(422, "Please check the speaker name and language.")
    existing = (
        await session.execute(
            select(VoiceClone).where(
                VoiceClone.actor_id == user.id, VoiceClone.request_id == request_id
            )
        )
    ).scalar_one_or_none()
    if existing:
        return await output(session, existing)
    fmt = audio.upload_format(file.content_type)
    if not fmt:
        raise HTTPException(422, "Upload a supported audio sample.")
    voice_id = uuid.uuid4()
    storage = get_storage()
    prefix = f"voices/{voice_id}"
    original = f"{prefix}/original{fmt[0]}"
    sample = f"{prefix}/sample.mp3"
    try:
        await storage.save_upload(original, file, 15 * 1024 * 1024)
        await audio.normalise(storage.path(original), storage.path(sample), fmt[1])
        duration = await audio.duration_ms(storage.path(sample))
        if not 30000 <= duration <= 60500:
            raise HTTPException(422, "Record a sample between 30 and 60 seconds.")
        digest = await asyncio.to_thread(
            lambda: hashlib.sha256(storage.path(sample).read_bytes()).hexdigest()
        )
        consent = {
            "version": VERSION,
            "text": TEXT_AR if locale == "ar" else TEXT,
            "locale": locale,
            "at": datetime.now(UTC).isoformat(),
            "actor_id": str(user.id),
            "speaker_name": speaker_name.strip(),
            "speaker_confirmed": True,
            "rights_confirmed": True,
            "use_confirmed": True,
        }
        job = await jobs.enqueue(
            session,
            "voice_clone",
            {"voice_id": str(voice_id)},
            idempotency_key=f"voice:{user.id}:{request_id}",
            max_attempts=1,
            commit=False,
        )
        voice = VoiceClone(
            id=voice_id,
            actor_id=user.id,
            request_id=request_id,
            speaker_name=speaker_name.strip(),
            consent=consent,
            sample_key=sample,
            sample_hash=digest,
            duration_ms=duration,
            provider=get_settings().voice_clone_provider,
            job_id=job.id,
        )
        session.add(voice)
        await session.commit()
        return await output(session, voice)
    except TooLarge as exc:
        await session.rollback()
        storage.delete_tree(prefix)
        raise HTTPException(413, "The voice sample must be at most 15 MB.") from exc
    except audio.NotAudio as exc:
        await session.rollback()
        storage.delete_tree(prefix)
        raise HTTPException(422, "This sample could not be read as audio.") from exc
    except IntegrityError:
        await session.rollback()
        storage.delete_tree(prefix)
        raise HTTPException(
            409, "This sample was already submitted. Refresh the voice list."
        ) from None
    except BaseException:
        await session.rollback()
        storage.delete_tree(prefix)
        raise


async def find_voice(session: AsyncSession, voice_id: uuid.UUID) -> VoiceClone:
    voice = await session.get(VoiceClone, voice_id)
    if not voice:
        raise HTTPException(404, "Voice not found.")
    return voice


@router.get("/{voice_id}")
async def read_voice(
    voice_id: uuid.UUID, user: User = Depends(staff), session: AsyncSession = Depends(get_session)
) -> dict:
    return await output(session, await find_voice(session, voice_id))


@router.get("/{voice_id}/sample")
async def sample(
    voice_id: uuid.UUID, user: User = Depends(staff), session: AsyncSession = Depends(get_session)
) -> FileResponse:
    voice = await find_voice(session, voice_id)
    return FileResponse(
        get_storage().path(voice.sample_key),
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, no-store"},
    )


@handler("voice_clone")
async def clone_job(payload: dict) -> dict:
    async with get_sessionmaker()() as session:
        voice = await find_voice(session, uuid.UUID(payload["voice_id"]))
        if voice.provider_voice_id:
            return {"voice_id": voice.provider_voice_id}
        if voice.submitted:
            raise UserFacingError(
                "This provider submission needs manual confirmation before retrying."
            )
        voice.submitted = True
        await session.commit()
        cloner = VoiceCloner(voice.provider)
        result = await gateway.call(
            "voice_clone",
            cloner,
            (str(voice.actor_id), voice.sample_hash, voice.consent["version"], voice.speaker_name),
            voice.duration_ms,
            lambda: cloner.clone(get_storage().path(voice.sample_key), voice.consent),
        )
        voice.provider_voice_id = result["voice_id"]
        voice.requires_verification = result["requires_verification"]
        await session.commit()
        return result
