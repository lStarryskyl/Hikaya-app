"""narrated AI videos: the refined shot script

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("video_generations", sa.Column("script", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("video_generations", "script")
