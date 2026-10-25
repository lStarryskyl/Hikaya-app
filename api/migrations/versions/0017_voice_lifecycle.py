"""voice revocation, a cloned narrator per story, and narration credit

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("voice_clones", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("voice_clones", sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_voice_clones_revoked_by", "voice_clones", "users", ["revoked_by"], ["id"], ondelete="SET NULL"
    )
    op.add_column("stories", sa.Column("narrator_voice_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_stories_narrator_voice_id", "stories", "voice_clones", ["narrator_voice_id"], ["id"],
        ondelete="SET NULL",
    )
    op.add_column("narrations", sa.Column("voice_clone_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_narrations_voice_clone_id", "narrations", "voice_clones", ["voice_clone_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_narrations_voice_clone_id", "narrations", type_="foreignkey")
    op.drop_column("narrations", "voice_clone_id")
    op.drop_constraint("fk_stories_narrator_voice_id", "stories", type_="foreignkey")
    op.drop_column("stories", "narrator_voice_id")
    op.drop_constraint("fk_voice_clones_revoked_by", "voice_clones", type_="foreignkey")
    op.drop_column("voice_clones", "revoked_by")
    op.drop_column("voice_clones", "revoked_at")
