"""the narrated video shown on a story's page

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column(
            "featured_video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("video_generations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("stories", "featured_video_id")
