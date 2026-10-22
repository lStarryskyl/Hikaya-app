"""spend ledger and provider result cache

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spend_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("budget", sa.Text(), nullable=False),
        sa.Column("estimated_usd", sa.Numeric(10, 4), nullable=False),
        sa.Column("actual_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("state", sa.Text(), server_default="reserved", nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL", name="fk_spend_entries_job_id"),
        sa.CheckConstraint("budget IN ('card', 'azure')", name="ck_spend_entries_budget"),
        sa.CheckConstraint("state IN ('reserved', 'committed', 'released')", name="ck_spend_entries_state"),
    )
    op.create_index("ix_spend_entries_budget_created_at", "spend_entries", ["budget", "created_at"])
    op.create_table(
        "provider_cache",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("file_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_cache")
    op.drop_index("ix_spend_entries_budget_created_at", table_name="spend_entries")
    op.drop_table("spend_entries")
