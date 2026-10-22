"""Stories: drafts, audio upload, submitting, reading, and serving their stored files.

Visibility: a published story is public. Any other status is visible only to its author
and to staff. Only the author edits, and only while the story is a draft or needs edits.
Anything a caller may not see answers 404, so drafts do not leak their existence.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audio, consent, photos, pipeline, places
from app.auth import current_user, current_user_optional
from app.config import get_settings
from app.db import get_session
from app.models import (
    Asset,
    AssetKind,
    Category,
    Language,
    Story,
    StoryStatus,
    User,
)
from app.storage import LocalStorage, TooLarge, get_storage
from app.visibility import STAFF_ROLES, can_view

router = APIRouter(prefix="/stories", tags=["stories"])
media_router = APIRouter(tags=["media"])

EDITABLE = {StoryStatus.DRAFT.value, StoryStatus.NEEDS_EDIT.value}

Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
PlaceName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class StoryFields(BaseModel):
    title: Title | None = None
    category: Category | None = None
    place_name: PlaceName | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    original_language: Language | None = None


class AuthorOut(BaseModel):
    id: uuid.UUID
    display_name: str


class AudioOut(BaseModel):
    url: str
    content_type: str
    original_url: str


class SegmentOut(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class LayerOut(BaseModel):
    kind: str
    language: str
    edited: bool
    segments: list[SegmentOut]


class StepOut(BaseModel):
    step: str
    status: str
    message: str


class PipelineOut(BaseModel):
    steps: list[StepOut]
    complete: bool


SegmentText = Annotated[str, StringConstraints(max_length=pipeline.MAX_SEGMENT_CHARS)]


class LayerEdit(BaseModel):
    texts: list[SegmentText]


class ConsentOut(BaseModel):
    version: str
    at: datetime


class SubmitIn(BaseModel):
    consent: bool = False
    consent_version: str | None = None


class ConsentStatement(BaseModel):
    version: str
    text: str


class GalleryPick(BaseModel):
    slug: str


class PhotoOrder(BaseModel):
    ids: list[uuid.UUID]


class StoryOut(BaseModel):
    id: uuid.UUID
    title: str
    category: str | None
    place_name: str
    latitude: float | None
    longitude: float | None
    original_language: str | None
    duration_ms: int | None
    status: str
    published_at: datetime | None
    created_at: datetime
    author: AuthorOut
    audio: AudioOut | None
    layers: list[LayerOut]
    place_slug: str | None
    cover: places.PhotoOut | None
    curated: bool
    photos: list[photos.StoryPhotoOut]
    consent: ConsentOut | None


def media_url(asset: Asset) -> str:
    return f"/media/{asset.id}"


def _parse_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise HTTPException(404, "Story not found.") from None


async def _visible_story(session: AsyncSession, story_id: str, user: User | None) -> Story:
    story = await session.get(Story, _parse_id(story_id))
    if story is None or not can_view(story, user):
        raise HTTPException(404, "Story not found.")
    return story


async def _own_or_staff_story(session: AsyncSession, story_id: str, user: User | None) -> Story:
    story = await session.get(Story, _parse_id(story_id))
    if (
        story is None
        or user is None
        or not (user.id == story.author_id or user.role in STAFF_ROLES)
    ):
        raise HTTPException(404, "Story not found.")
    return story


async def _own_story(session: AsyncSession, story_id: str, user: User) -> Story:
    story = await session.get(Story, _parse_id(story_id))
    if story is None or story.author_id != user.id:
        raise HTTPException(404, "Story not found.")
    return story


def _require_editable(story: Story) -> None:
    if story.status not in EDITABLE:
        raise HTTPException(409, "This story can no longer be edited.")


async def _audio_assets(session: AsyncSession, story_id: uuid.UUID) -> dict[str, Asset]:
    rows = await session.execute(
        select(Asset).where(
            Asset.story_id == story_id,
            Asset.kind.in_([AssetKind.ORIGINAL_AUDIO.value, AssetKind.AUDIO.value]),
        )
    )
    return {a.kind: a for a in rows.scalars()}


async def to_out(session: AsyncSession, story: Story) -> StoryOut:
    author = await session.get(User, story.author_id)
    assets = await _audio_assets(session, story.id)
    playable, original = assets.get(AssetKind.AUDIO), assets.get(AssetKind.ORIGINAL_AUDIO)
    audio_out = None
    if playable and original:
        audio_out = AudioOut(
            url=media_url(playable),
            content_type=playable.content_type,
            original_url=media_url(original),
        )
    return StoryOut(
        id=story.id,
        title=story.title,
        category=story.category,
        place_name=story.place_name,
        latitude=story.latitude,
        longitude=story.longitude,
        original_language=story.original_language,
        duration_ms=story.duration_ms,
        status=story.status,
        published_at=story.published_at,
        created_at=story.created_at,
        author=AuthorOut(id=author.id, display_name=author.display_name),
        audio=audio_out,
        layers=[
            LayerOut(kind=la.kind, language=la.language, edited=la.edited, segments=la.segments)
            for la in await pipeline.layers(session, story.id)
        ],
        place_slug=story.place_slug,
        cover=await photos.cover_out(session, story),
        photos=await photos.list_for(session, story.id),
        consent=(
            ConsentOut(version=story.consent_version, at=story.consented_at)
            if story.consent_version and story.consented_at
            else None
        ),
        curated=story.curated_at is not None,
    )


async def _apply(session: AsyncSession, story: Story, fields: StoryFields) -> None:
    for name, value in fields.model_dump(exclude_unset=True).items():
        if value is None and name in ("title", "place_name"):
            value = ""
        setattr(story, name, value.value if hasattr(value, "value") else value)
    # Link the story to a known place when its place name matches one.
    story.place_slug = await places.slug_for_name(session, story.place_name)


@router.post("", status_code=201, response_model=StoryOut)
async def create_story(
    body: StoryFields,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> StoryOut:
    story = Story(author_id=user.id)
    await _apply(session, story, body)
    session.add(story)
    await session.commit()
    await session.refresh(story)
    return await to_out(session, story)


class UploadLimits(BaseModel):
    audio_max_mb: float
    audio_max_minutes: float
    photo_types: list[str]
    photo_max_mb: float
    photos_per_story: int


@router.get("/limits", response_model=UploadLimits)
async def upload_limits() -> UploadLimits:
    """The limits uploads are checked against, so the page can show and pre-check them."""
    settings = get_settings()
    return UploadLimits(
        audio_max_mb=settings.max_audio_upload_mb,
        audio_max_minutes=settings.max_audio_minutes,
        photo_types=sorted(photos.IMAGE_TYPES),
        photo_max_mb=settings.max_photo_upload_mb,
        photos_per_story=settings.max_photos_per_story,
    )


@router.get("/consent", response_model=ConsentStatement)
async def consent_statement() -> ConsentStatement:
    """The rights statement to show before publishing, with the version to send back."""
    return ConsentStatement(version=consent.VERSION, text=consent.TEXT)


@router.get("/{story_id}", response_model=StoryOut)
async def read_story(
    story_id: str,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> StoryOut:
    return await to_out(session, await _visible_story(session, story_id, user))


@router.patch("/{story_id}", response_model=StoryOut)
async def edit_story(
    story_id: str,
    body: StoryFields,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> StoryOut:
    story = await _own_story(session, story_id, user)
    _require_editable(story)
    language_before = story.original_language
    await _apply(session, story, body)
    await session.commit()
    if story.original_language != language_before:
        await pipeline.start(session, story)
    await session.refresh(story)
    return await to_out(session, story)


@router.put("/{story_id}/audio", response_model=StoryOut)
async def upload_audio(
    story_id: str,
    file: UploadFile,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> StoryOut:
    story = await _own_story(session, story_id, user)
    _require_editable(story)
    settings = get_settings()

    accepted = audio.upload_format(file.content_type)
    if accepted is None:
        raise HTTPException(415, "Upload an audio file such as WebM, Ogg, MP3, M4A or WAV.")
    extension, demuxer = accepted
    content_type = (file.content_type or "").split(";")[0].strip().lower()

    stem = f"stories/{story.id}/{uuid.uuid4().hex}"
    original_key, playable_key = (
        f"{stem}-original{extension}",
        f"{stem}{audio.NORMALISED_EXTENSION}",
    )
    max_bytes = int(settings.max_audio_upload_mb * 1024 * 1024)
    try:
        original_size = await storage.save_upload(original_key, file, max_bytes)
    except TooLarge:
        raise HTTPException(
            413, f"The recording is larger than {settings.max_audio_upload_mb:g} MB."
        ) from None

    try:
        await audio.normalise(storage.path(original_key), storage.path(playable_key), demuxer)
        length_ms = await audio.duration_ms(storage.path(playable_key))
    except audio.NotAudio:
        storage.delete(original_key, playable_key)
        raise HTTPException(422, "That file is not a readable audio recording.") from None
    if length_ms > settings.max_audio_minutes * 60_000:
        storage.delete(original_key, playable_key)
        raise HTTPException(
            422, f"Recordings can be up to {settings.max_audio_minutes:g} minutes long."
        )

    # Lock the story so two uploads at once cannot both replace the same old files.
    await session.refresh(story, with_for_update=True)
    old = await _audio_assets(session, story.id)
    for asset in old.values():
        await session.delete(asset)
    session.add_all(
        [
            Asset(
                story_id=story.id,
                kind=AssetKind.ORIGINAL_AUDIO.value,
                storage_key=original_key,
                content_type=content_type,
                size_bytes=original_size,
            ),
            Asset(
                story_id=story.id,
                kind=AssetKind.AUDIO.value,
                storage_key=playable_key,
                content_type=audio.NORMALISED_CONTENT_TYPE,
                size_bytes=storage.size(playable_key),
            ),
        ]
    )
    story.duration_ms = length_ms
    try:
        await session.commit()
    except BaseException:
        storage.delete(original_key, playable_key)
        raise
    # Old files go only after the database no longer points at them.
    storage.delete(*(asset.storage_key for asset in old.values()))
    await pipeline.start(session, story)
    await session.refresh(story)
    return await to_out(session, story)


def missing_for_publishing(story: Story, has_audio: bool, has_transcript: bool) -> list[str]:
    checks = [
        ("title", bool(story.title)),
        ("category", story.category is not None),
        ("place", bool(story.place_name)),
        ("map pin", story.latitude is not None and story.longitude is not None),
        ("language", story.original_language is not None),
        ("audio", has_audio),
        ("transcript (still being prepared)", has_transcript),
    ]
    return [name for name, ok in checks if not ok]


@router.post("/{story_id}/submit", response_model=StoryOut)
async def submit_story(
    story_id: str,
    body: SubmitIn | None = None,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> StoryOut:
    story = await _own_story(session, story_id, user)
    _require_editable(story)
    kinds = {layer.kind for layer in await pipeline.layers(session, story.id)}
    missing = missing_for_publishing(
        story,
        bool(await _audio_assets(session, story.id)),
        {pipeline.VERBATIM, pipeline.POLISHED} <= kinds,
    )
    if missing:
        raise HTTPException(422, "Add these before publishing: " + ", ".join(missing) + ".")
    if body is None or not body.consent or body.consent_version != consent.VERSION:
        raise HTTPException(422, "Agree to the current rights statement before publishing.")
    story.consent_version, story.consented_at = consent.VERSION, datetime.now(UTC)
    # Moderation arrives in a later ticket; until then a complete story publishes at once.
    story.status = StoryStatus.PUBLISHED.value
    story.published_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(story)
    return await to_out(session, story)


@router.post("/{story_id}/photos", status_code=201, response_model=photos.StoryPhotoOut)
async def add_photo(
    story_id: str,
    file: UploadFile,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> photos.StoryPhotoOut:
    story = await _own_story(session, story_id, user)
    _require_editable(story)
    return await photos.add_upload(session, story, file, storage)


@router.post("/{story_id}/photos/gallery", status_code=201, response_model=photos.StoryPhotoOut)
async def pick_gallery_photo(
    story_id: str,
    body: GalleryPick,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> photos.StoryPhotoOut:
    story = await _own_story(session, story_id, user)
    _require_editable(story)
    return await photos.add_gallery_pick(session, story, body.slug)


@router.put("/{story_id}/photos/order", response_model=list[photos.StoryPhotoOut])
async def reorder_photos(
    story_id: str,
    body: PhotoOrder,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[photos.StoryPhotoOut]:
    story = await _own_story(session, story_id, user)
    _require_editable(story)
    await photos.reorder(session, story, body.ids)
    return await photos.list_for(session, story.id)


@router.delete("/{story_id}/photos/{photo_id}", status_code=204)
async def delete_photo(
    story_id: str,
    photo_id: uuid.UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> Response:
    story = await _own_story(session, story_id, user)
    _require_editable(story)
    await photos.remove(session, story, photo_id, storage)
    return Response(status_code=204)


@router.get("/{story_id}/pipeline", response_model=PipelineOut)
async def pipeline_status(
    story_id: str,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
) -> PipelineOut:
    story = await _own_or_staff_story(session, story_id, user)
    steps, complete = await pipeline.status(session, story)
    return PipelineOut(
        steps=[StepOut(step=s.step, status=s.status, message=s.message) for s in steps],
        complete=complete,
    )


@router.post("/{story_id}/pipeline/{step}/retry", response_model=PipelineOut)
async def retry_step(
    story_id: str,
    step: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PipelineOut:
    story = await _own_story(session, story_id, user)
    if step not in pipeline.STEPS:
        raise HTTPException(404, "No such step.")
    _require_editable(story)
    if not await pipeline.retry(session, story, step):
        raise HTTPException(409, "Only a failed step can be retried.")
    return await pipeline_status(story_id, user, session)


@router.patch("/{story_id}/layers/{kind}", response_model=StoryOut)
async def edit_layer(
    story_id: str,
    kind: str,
    body: LayerEdit,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> StoryOut:
    story = await _own_story(session, story_id, user)
    if kind not in pipeline.LAYER_KINDS:
        raise HTTPException(404, "No such text layer.")
    _require_editable(story)
    try:
        await pipeline.edit_layer(session, story, kind, body.texts)
    except pipeline.LayerNotReady:
        raise HTTPException(409, "This text is not ready yet.") from None
    except pipeline.LayerBusy:
        raise HTTPException(
            409, "This text is being updated right now. Edit it once it has finished."
        ) from None
    except pipeline.Misaligned:
        raise HTTPException(422, "Keep exactly one text for each line.") from None
    await session.refresh(story)
    return await to_out(session, story)


@media_router.api_route("/media/{asset_id}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_media(
    asset_id: str,
    user: User | None = Depends(current_user_optional),
    session: AsyncSession = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> FileResponse:
    try:
        asset = await session.get(Asset, uuid.UUID(asset_id))
    except ValueError:
        asset = None
    story = await session.get(Story, asset.story_id) if asset else None
    if asset is None or story is None or not can_view(story, user):
        raise HTTPException(404, "Not found.")
    path = storage.path(asset.storage_key)
    if not path.is_file():
        raise HTTPException(404, "Not found.")
    # Revalidate every time: a published story can later be held, and its files must then stop
    # being served at once. Private files never enter any cache.
    cache = "no-cache" if story.status == StoryStatus.PUBLISHED else "private, no-store"
    return FileResponse(path, media_type=asset.content_type, headers={"Cache-Control": cache})
