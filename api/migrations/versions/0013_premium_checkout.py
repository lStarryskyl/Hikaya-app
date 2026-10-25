"""Premium membership and dummy checkout.
Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("plan", sa.Text(), nullable=False, server_default="free"))
    op.create_check_constraint("ck_users_plan", "users", "plan IN ('free', 'premium')")
    op.create_table("checkout_attempts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("scenario", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="processing"),
        sa.Column("complete_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "request_id", name="uq_checkout_request"),
        sa.CheckConstraint("status IN ('processing', 'succeeded', 'failed')", name="ck_checkout_status"),
        sa.CheckConstraint("scenario IN ('success', 'failure')", name="ck_checkout_scenario"),
    )

def downgrade():
    op.drop_table("checkout_attempts")
    op.drop_constraint("ck_users_plan", "users")
    op.drop_column("users", "plan")
