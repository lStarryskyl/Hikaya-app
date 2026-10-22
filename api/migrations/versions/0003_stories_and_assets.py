"""stories and their stored files

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATUSES = "'draft', 'moderating', 'published', 'held', 'needs_edit'"
CATEGORIES = "'crafts', 'daily_life', 'folklore', 'history', 'personal'"
LANGUAGES = "'jordanian', 'msa', 'english'"


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), server_default="", nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("place_name", sa.Text(), server_default="", nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("original_language", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE", name="fk_stories_author_id"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="ck_stories_status"),
        sa.CheckConstraint(f"category IS NULL OR category IN ({CATEGORIES})", name="ck_stories_category"),
        sa.CheckConstraint(f"original_language IS NULL OR original_language IN ({LANGUAGES})", name="ck_stories_language"),
        sa.CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_stories_latitude"),
        sa.CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_stories_longitude"),
        sa.CheckConstraint("status <> 'published' OR published_at IS NOT NULL", name="ck_stories_published_at"),
    )
    op.create_index("ix_stories_status_published_at", "stories", ["status", "published_at"])
    op.create_index("ix_stories_author_id", "stories", ["author_id"])

    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE", name="fk_assets_story_id"),
        sa.UniqueConstraint("storage_key", name="uq_assets_storage_key"),
    )
    op.create_index("ix_assets_story_id_kind", "assets", ["story_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_assets_story_id_kind", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_stories_author_id", table_name="stories")
    op.drop_index("ix_stories_status_published_at", table_name="stories")
    op.drop_table("stories")
