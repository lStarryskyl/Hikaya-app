"""text layers and pipeline steps

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "text_layers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("segments", postgresql.JSONB(), nullable=False),
        sa.Column("edited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE", name="fk_text_layers_story_id"),
        sa.UniqueConstraint("story_id", "kind", name="uq_text_layers_story_kind"),
        sa.CheckConstraint(
            "kind IN ('verbatim', 'polished', 'translation_en', 'translation_msa')", name="ck_text_layers_kind"
        ),
    )
    op.create_table(
        "pipeline_steps",
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("story_id", "step", name="pk_pipeline_steps"),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE", name="fk_pipeline_steps_story_id"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL", name="fk_pipeline_steps_job_id"),
    )


def downgrade() -> None:
    op.drop_table("pipeline_steps")
    op.drop_table("text_layers")
