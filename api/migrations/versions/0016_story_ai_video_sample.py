"""a pre-made AI video sample on a story

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("ai_video_sample", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "ai_video_sample")
