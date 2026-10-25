"""Database models: the job queue, accounts, and stories with their stored files."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(Base):
    """One unit of background work, claimed by the worker with row locking."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=JobStatus.QUEUED)
    # One key per dispatch, so a retry can never run (or bill) twice.
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    provider_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_jobs_status_run_after", "status", "run_after"),)


class Role(StrEnum):
    MEMBER = "member"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Always stored lower-case, so sign-in and duplicate checks are case-insensitive.
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=Role.MEMBER.value)
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        CheckConstraint("plan IN ('free', 'premium')", name="ck_users_plan"),
        CheckConstraint("role IN ('member', 'reviewer', 'admin')", name="ck_users_role"),
    )


class AuthSession(Base):
    """A signed-in browser. Only the hash of the cookie token is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_auth_sessions_user_id", "user_id"),)


class StoryStatus(StrEnum):
    DRAFT = "draft"
    MODERATING = "moderating"
    PUBLISHED = "published"
    HELD = "held"
    NEEDS_EDIT = "needs_edit"


class Category(StrEnum):
    CRAFTS = "crafts"
    DAILY_LIFE = "daily_life"
    FOLKLORE = "folklore"
    HISTORY = "history"
    PERSONAL = "personal"


class Language(StrEnum):
    JORDANIAN = "jordanian"
    MSA = "msa"
    ENGLISH = "english"


class AssetKind(StrEnum):
    ORIGINAL_AUDIO = "original_audio"
    AUDIO = "audio"  # normalised copy used for playback and providers
    NARRATION = "narration"  # the text read by a voice (MP3)
    SLIDESHOW = "slideshow"  # pan-and-zoom video of the photos with the recording (MP4)


class NarrationSource(StrEnum):
    POLISHED = "polished"
    MSA = "msa"


class NarrationTiming(StrEnum):
    ALIGNMENT = "alignment"  # from the voice provider's alignment data
    PER_SEGMENT = "per_segment"  # each line spoken alone and measured


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    category: Mapped[str | None] = mapped_column(Text)
    place_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    original_language: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    # The known place the story is pinned to, matched from place_name; null for other places.
    place_slug: Mapped[str | None] = mapped_column(
        Text, ForeignKey("places.slug", ondelete="SET NULL")
    )
    cover_photo_slug: Mapped[str | None] = mapped_column(
        Text, ForeignKey("place_photos.slug", ondelete="SET NULL")
    )
    # The museum: curated by staff, or set aside as "not now" so it leaves the candidates.
    curated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    curated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    museum_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    museum_dismissed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # The rights statement version the author agreed to when submitting, and when.
    consent_version: Mapped[str | None] = mapped_column(Text)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set by staff when they send a story back (needs_edit) or approve it.
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=StoryStatus.DRAFT.value
    )
    # A consenting person's cloned voice chosen by staff to narrate this story (#18).
    narrator_voice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_clones.id", ondelete="SET NULL")
    )
    # A pre-made AI video sample shown on this story to premium members (#19); seeded only.
    ai_video_sample: Mapped[str | None] = mapped_column(Text)
    # Which text the narration reads: the polished text, or the MSA translation.
    narration_source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=NarrationSource.POLISHED.value
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_stories_status_published_at", "status", "published_at"),
        Index("ix_stories_author_id", "author_id"),
        # Full-text search (app/search.py, migration 0015).
        *(
            Index(
                f"ix_stories_search_{cfg}",
                # Owned by migration 0015; autogenerate skips it (migrations/env.py).
                text(
                    f"to_tsvector('{cfg}'::regconfig, ((COALESCE(title, ''::text) "
                    "|| ' '::text) || COALESCE(place_name, ''::text)))"
                ),
                postgresql_using="gin",
            )
            for cfg in ("arabic", "english")
        ),
        CheckConstraint(
            "status IN ('draft', 'moderating', 'published', 'held', 'needs_edit')",
            name="ck_stories_status",
        ),
        CheckConstraint(
            "narration_source IN ('polished', 'msa')", name="ck_stories_narration_source"
        ),
        CheckConstraint(
            "category IS NULL OR category IN "
            "('crafts', 'daily_life', 'folklore', 'history', 'personal')",
            name="ck_stories_category",
        ),
        CheckConstraint(
            "original_language IS NULL OR original_language IN ('jordanian', 'msa', 'english')",
            name="ck_stories_language",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_stories_latitude"
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_stories_longitude"
        ),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL", name="ck_stories_published_at"
        ),
    )


class Asset(Base):
    """A stored file belonging to a story. The file itself lives in storage under `key`."""

    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_assets_story_id_kind", "story_id", "kind"),)


class TextLayer(Base):
    """One version of a story's text, as segments that share the verbatim timestamps.

    kinds: verbatim, polished, translation_en, translation_msa.
    segments: [{"start_ms": int, "end_ms": int, "text": str}, ...]
    """

    __tablename__ = "text_layers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list] = mapped_column(JSONB, nullable=False)
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("story_id", "kind", name="uq_text_layers_story_kind"),
        # Full-text search over the segment texts (app/search.py, migration 0015).
        *(
            Index(
                f"ix_text_layers_search_{cfg}",
                text(f"jsonb_to_tsvector('{cfg}'::regconfig, segments, '[\"string\"]'::jsonb)"),
                postgresql_using="gin",
            )
            for cfg in ("arabic", "english")
        ),
        CheckConstraint(
            "kind IN ('verbatim', 'polished', 'translation_en', 'translation_msa')",
            name="ck_text_layers_kind",
        ),
    )


class PipelineStep(Base):
    """The latest job for one step of one story, and the input it was made from.

    A job whose input hash no longer matches its step's is stale: its result is dropped.
    """

    __tablename__ = "pipeline_steps"

    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (PrimaryKeyConstraint("story_id", "step", name="pk_pipeline_steps"),)


class Place(Base):
    """A town or site with a photo gallery. Stories link to one when their place matches."""

    __tablename__ = "places"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cover_photo_slug: Mapped[str | None] = mapped_column(Text)


class PlacePhoto(Base):
    """A gallery photo, stored as WebP at each width in `widths`."""

    __tablename__ = "place_photos"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    place_slug: Mapped[str] = mapped_column(
        Text, ForeignKey("places.slug", ondelete="CASCADE"), nullable=False
    )
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    widths: Mapped[list] = mapped_column(JSONB, nullable=False)


class SpendEntry(Base):
    """One paid provider call: reserved before the call, then committed or released."""

    __tablename__ = "spend_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    budget: Mapped[str] = mapped_column(Text, nullable=False)  # card | azure
    estimated_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    actual_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="reserved")
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("budget IN ('card', 'azure')", name="ck_spend_entries_budget"),
        CheckConstraint(
            "state IN ('reserved', 'committed', 'released')", name="ck_spend_entries_state"
        ),
        Index("ix_spend_entries_budget_created_at", "budget", "created_at"),
    )


class ProviderCacheEntry(Base):
    """A provider result, keyed by a hash of the operation, provider and input."""

    __tablename__ = "provider_cache"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # A stored file the result points at (narration audio, video), if any.
    file_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StoryPhoto(Base):
    """One photo of a story, in order: an upload (WebP at `widths`) or a gallery pick."""

    __tablename__ = "story_photos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    place_photo_slug: Mapped[str | None] = mapped_column(
        Text, ForeignKey("place_photos.slug", ondelete="CASCADE")
    )
    widths: Mapped[list | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_story_photos_story_position", "story_id", "position"),
        CheckConstraint(
            "(place_photo_slug IS NULL) <> (widths IS NULL)", name="ck_story_photos_one_source"
        ),
    )


class ModerationResult(Base):
    """One moderation pass: each label's verdict and the hash of the text it judged."""

    __tablename__ = "moderation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    # {"hate": {"raised": false, "reason": ""}, ...}
    labels: Mapped[dict] = mapped_column(JSONB, nullable=False)
    held: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # The exact texts that were judged, so staff can see what the verdict was about.
    texts: Mapped[list] = mapped_column(JSONB, nullable=False)
    text_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_moderation_results_story_created", "story_id", "created_at"),)


class Narration(Base):
    """A story's current narration: which voice read which text, and when each line starts.

    segments: [{"start_ms": int, "end_ms": int, "text": str}, ...], one per line of the text
    read, in the narration's own time. input_hash is the narrate step's input it was made
    from, so the slideshow knows whether it carries the current narration.
    """

    __tablename__ = "narrations"

    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    voice: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    timing: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Set when a cloned voice read it; the player credits the person.
    voice_clone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_clones.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CURATE = "curate"
    DISMISS = "dismiss"
    UNCURATE = "uncurate"
    PLAN_RESET = "plan_reset"
    VOICE_CREATED = "voice_created"
    VOICE_REVOKED = "voice_revoked"
    NARRATION_REGENERATED = "narration_regenerated"
    VOICE_VERIFIED = "voice_verified"


class AuditEvent(Base):
    """A staff action: who did what to which target, and when. Never edited or deleted, and
    kept when the target is deleted, so decisions can be checked afterwards."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    )

    __table_args__ = (Index("ix_audit_events_created_at", "created_at"),)


class VoiceClone(Base):
    """An immutable speaker consent record and its private sample, with a queued clone job."""

    __tablename__ = "voice_clones"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_name: Mapped[str] = mapped_column(Text, nullable=False)
    consent: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sample_key: Mapped[str] = mapped_column(Text, nullable=False)
    sample_hash: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_voice_id: Mapped[str | None] = mapped_column(Text)
    requires_verification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Revoked: the sample, every narration made with it and the provider voice are deleted.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("actor_id", "request_id", name="uq_voice_request"),)


class CheckoutAttempt(Base):
    __tablename__ = "checkout_attempts"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="processing")
    complete_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_checkout_request"),
        CheckConstraint(
            "status IN ('processing', 'succeeded', 'failed')", name="ck_checkout_status"
        ),
        CheckConstraint("scenario IN ('success', 'failure')", name="ck_checkout_scenario"),
    )


class VideoGeneration(Base):
    __tablename__ = "video_generations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    image_key: Mapped[str | None] = mapped_column(Text)
    provider_request: Mapped[dict | None] = mapped_column(JSONB)
    submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_key: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[str] = mapped_column(Text, nullable=False, server_default="Queued locally")
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
