"""Consent-backed voice clones.
Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("voice_clones",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("speaker_name", sa.Text(), nullable=False),
        sa.Column("consent", pg.JSONB(), nullable=False),
        sa.Column("sample_key", sa.Text(), nullable=False),
        sa.Column("sample_hash", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_voice_id", sa.Text()),
        sa.Column("requires_verification", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submitted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("actor_id", "request_id", name="uq_voice_request"),
    )

def downgrade():
    op.drop_table("voice_clones")
