"""moderation results and review notes

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moderation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("labels", postgresql.JSONB(), nullable=False),
        sa.Column("held", sa.Boolean(), nullable=False),
        sa.Column("text_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE", name="fk_moderation_results_story_id"),
    )
    op.create_index("ix_moderation_results_story_created", "moderation_results", ["story_id", "created_at"])
    op.add_column("stories", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("stories", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stories", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_stories_reviewed_by", "stories", "users", ["reviewed_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_stories_reviewed_by", "stories", type_="foreignkey")
    op.drop_column("stories", "reviewed_by")
    op.drop_column("stories", "reviewed_at")
    op.drop_column("stories", "review_note")
    op.drop_index("ix_moderation_results_story_created", table_name="moderation_results")
    op.drop_table("moderation_results")
