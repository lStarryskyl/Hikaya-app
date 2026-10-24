"""staff review, museum curation and audit events

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("curated_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("stories", sa.Column("museum_dismissed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stories", sa.Column("museum_dismissed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_stories_curated_by", "stories", "users", ["curated_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_stories_museum_dismissed_by", "stories", "users", ["museum_dismissed_by"], ["id"], ondelete="SET NULL")
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL", name="fk_audit_events_actor_id"),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_constraint("fk_stories_museum_dismissed_by", "stories", type_="foreignkey")
    op.drop_constraint("fk_stories_curated_by", "stories", type_="foreignkey")
    op.drop_column("stories", "museum_dismissed_by")
    op.drop_column("stories", "museum_dismissed_at")
    op.drop_column("stories", "curated_by")
