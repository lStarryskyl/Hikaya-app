"""narration and slideshow

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column("narration_source", sa.Text(), server_default="polished", nullable=False),
    )
    op.create_check_constraint(
        "ck_stories_narration_source", "stories", "narration_source IN ('polished', 'msa')"
    )
    op.create_table(
        "narrations",
        sa.Column("story_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("voice", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("timing", sa.Text(), nullable=False),
        sa.Column("segments", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE", name="fk_narrations_story_id"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE", name="fk_narrations_asset_id"),
    )


def downgrade() -> None:
    op.drop_table("narrations")
    op.drop_constraint("ck_stories_narration_source", "stories", type_="check")
    op.drop_column("stories", "narration_source")
