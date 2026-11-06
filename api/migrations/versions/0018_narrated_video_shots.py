"""narrated AI videos: the shots of a video and where each one stands

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One entry per shot of a narrated video, in order; empty for a single clip.
    op.add_column(
        "video_generations",
        sa.Column(
            "shots",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("video_generations", "shots")
