"""story photos and publishing consent

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "story_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("place_photo_slug", sa.Text(), nullable=True),
        sa.Column("widths", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE", name="fk_story_photos_story_id"),
        sa.ForeignKeyConstraint(
            ["place_photo_slug"], ["place_photos.slug"], ondelete="CASCADE", name="fk_story_photos_place_photo_slug"
        ),
        sa.CheckConstraint("(place_photo_slug IS NULL) <> (widths IS NULL)", name="ck_story_photos_one_source"),
    )
    op.create_index("ix_story_photos_story_position", "story_photos", ["story_id", "position"])
    op.add_column("stories", sa.Column("consent_version", sa.Text(), nullable=True))
    op.add_column("stories", sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "consented_at")
    op.drop_column("stories", "consent_version")
    op.drop_index("ix_story_photos_story_position", table_name="story_photos")
    op.drop_table("story_photos")
