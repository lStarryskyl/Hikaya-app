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

from app import audio, gateway, jobs, media
from app.auth import require_roles
from app.config import get_settings
from app.db import get_session, get_sessionmaker
from app.errors import INTERNAL_PREFIX, UserFacingError
from app.handlers import handler
from app.models import (
    Asset,
    AssetKind,
    AuditAction,
    AuditEvent,
    Job,
    JobStatus,
    Narration,
    Role,
    Story,
    StoryStatus,
    User,
    VoiceClone,
)
from app.providers.voices import VoiceCloner, unavailable_reason
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


VOICE = "voice"  # audit target type
VERIFY = (
    "The provider asks the speaker to verify this voice before it can narrate. "
    "Complete the verification with the speaker, then check again."
)


def state_of(voice: VoiceClone, job: Job | None) -> tuple[str, str | None]:
    """preparing | ready | needs_verification | failed | revoked, with a message to show."""
    if voice.revoked_at:
        return "revoked", "This voice was revoked; its sample and narrations are deleted."
    if job is None or job.status == JobStatus.FAILED:
        error = job.error if job else None
        if error and error.startswith(INTERNAL_PREFIX):
            error = "Voice cloning failed. Please contact the demo administrator."
        return "failed", error or "Voice cloning failed."
    if job.status != JobStatus.DONE or not voice.provider_voice_id:
        return "preparing", None
    if voice.requires_verification:
        return "needs_verification", VERIFY
    return "ready", None


async def ready_voice(session: AsyncSession, voice_id: uuid.UUID) -> VoiceClone | None:
    """The voice when it can narrate now, else None."""
    voice = await session.get(VoiceClone, voice_id)
    if voice is None:
        return None
    job = await session.get(Job, voice.job_id) if voice.job_id else None
    return voice if state_of(voice, job)[0] == "ready" else None


async def output(session: AsyncSession, voice: VoiceClone) -> dict:
    job = await session.get(Job, voice.job_id) if voice.job_id else None
    error = job.error if job else None
    if error and error.startswith(INTERNAL_PREFIX):
        error = "Voice cloning failed. Please contact the demo administrator."
    state, message = state_of(voice, job)
    return {
        "state": state,
        "message": message,
        "revoked_at": voice.revoked_at.isoformat() if voice.revoked_at else None,
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
        # Whether cloned voices can narrate with the current providers, and why not.
        "available": unavailable_reason() is None,
        "reason": unavailable_reason(),
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
    if reason := unavailable_reason():
        raise HTTPException(409, reason)
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
        session.add(
            AuditEvent(
                actor_id=user.id,
                action=AuditAction.VOICE_CREATED.value,
                target_type=VOICE,
                target_id=voice_id,
                detail={"consent_version": VERSION},
            )
        )
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
    if voice.revoked_at or not get_storage().exists(voice.sample_key):
        raise HTTPException(404, "This sample was deleted.")
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


# --- verification ---


@router.post("/{voice_id}/verified")
async def mark_verified(
    voice_id: uuid.UUID, user: User = Depends(staff), session: AsyncSession = Depends(get_session)
) -> dict:
    """The provider asked the speaker to verify the voice; staff confirm it was done there.
    (The provider's own verification happens with the speaker, outside this app.)"""
    voice = await session.get(VoiceClone, voice_id, with_for_update=True)
    if voice is None:
        raise HTTPException(404, "Voice not found.")
    job = await session.get(Job, voice.job_id) if voice.job_id else None
    if state_of(voice, job)[0] != "needs_verification":
        raise HTTPException(409, "This voice is not waiting for verification.")
    voice.requires_verification = False
    session.add(
        AuditEvent(
            actor_id=user.id,
            action=AuditAction.VOICE_VERIFIED.value,
            target_type=VOICE,
            target_id=voice.id,
        )
    )
    await session.commit()
    return await output(session, voice)


# --- revocation ---


@router.post("/{voice_id}/revoke")
async def revoke(
    voice_id: uuid.UUID, user: User = Depends(staff), session: AsyncSession = Depends(get_session)
) -> dict:
    """Withdraw a voice: its sample, every narration made with it (and the slideshows that
    carry them) and the cached speech in it are deleted at once; affected stories are
    narrated again in the default voice; the provider's copy is deleted by a job."""
    voice = await session.get(VoiceClone, voice_id, with_for_update=True)
    if voice is None:
        raise HTTPException(404, "Voice not found.")
    if voice.revoked_at:
        return await output(session, voice)
    voice.revoked_at, voice.revoked_by = datetime.now(UTC), user.id

    narrated = list(
        (
            await session.execute(select(Narration).where(Narration.voice_clone_id == voice.id))
        ).scalars()
    )
    chosen = list(
        (await session.execute(select(Story).where(Story.narrator_voice_id == voice.id))).scalars()
    )
    affected = {n.story_id for n in narrated} | {s.id for s in chosen}
    for story in chosen:
        story.narrator_voice_id = None
    for narration in narrated:
        await session.delete(narration)
    files: list[str] = []
    if affected:
        old = (
            await session.execute(
                select(Asset).where(
                    Asset.story_id.in_(affected),
                    Asset.kind.in_([AssetKind.NARRATION.value, AssetKind.SLIDESHOW.value]),
                )
            )
        ).scalars()
        for asset in old:
            files.append(asset.storage_key)
            await session.delete(asset)
    if voice.provider_voice_id:
        files += await media.purge_speech(session, voice.provider_voice_id)
        await jobs.enqueue(
            session,
            "voice_delete",
            {"provider": voice.provider, "provider_voice_id": voice.provider_voice_id},
            idempotency_key=f"voice-delete:{voice.id}",
            commit=False,
        )
    await session.flush()
    # Narrated again in the default voice; the slideshow follows the new narration.
    for story_id in affected:
        story = await session.get(Story, story_id)
        if story is not None and story.status in (
            StoryStatus.MODERATING,
            StoryStatus.PUBLISHED,
            StoryStatus.HELD,
        ):
            await media.queue(session, story)
    session.add(
        AuditEvent(
            actor_id=user.id,
            action=AuditAction.VOICE_REVOKED.value,
            target_type=VOICE,
            target_id=voice.id,
            detail={"stories": len(affected)},
        )
    )
    await session.commit()
    storage = get_storage()
    await asyncio.to_thread(storage.delete, *files)
    await asyncio.to_thread(storage.delete_tree, f"voices/{voice.id}")
    return await output(session, voice)


@handler("voice_delete")
async def delete_job(payload: dict) -> dict:
    await VoiceCloner(payload["provider"]).delete(payload["provider_voice_id"])
    return {"deleted": payload["provider_voice_id"]}
