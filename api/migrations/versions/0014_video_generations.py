"""Staff video generations.
Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("video_generations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("story_id", pg.UUID(as_uuid=True), sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("image_key", sa.Text()),
        sa.Column("provider_request", pg.JSONB()),
        sa.Column("submitted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("file_key", sa.Text()),
        sa.Column("progress", sa.Text(), nullable=False, server_default="Queued locally"),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

def downgrade():
    op.drop_table("video_generations")
