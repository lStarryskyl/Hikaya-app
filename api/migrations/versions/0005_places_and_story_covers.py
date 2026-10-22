"""places, place photos, and story place, cover and curation

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cover_photo_slug", sa.Text(), nullable=True),
        sa.UniqueConstraint("name", name="uq_places_name"),
    )
    op.create_table(
        "place_photos",
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("place_slug", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("widths", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["place_slug"], ["places.slug"], ondelete="CASCADE", name="fk_place_photos_place_slug"),
    )
    op.add_column("stories", sa.Column("place_slug", sa.Text(), nullable=True))
    op.add_column("stories", sa.Column("cover_photo_slug", sa.Text(), nullable=True))
    op.add_column("stories", sa.Column("curated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_stories_place_slug", "stories", "places", ["place_slug"], ["slug"], ondelete="SET NULL")
    op.create_foreign_key(
        "fk_stories_cover_photo_slug", "stories", "place_photos", ["cover_photo_slug"], ["slug"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_stories_cover_photo_slug", "stories", type_="foreignkey")
    op.drop_constraint("fk_stories_place_slug", "stories", type_="foreignkey")
    op.drop_column("stories", "curated_at")
    op.drop_column("stories", "cover_photo_slug")
    op.drop_column("stories", "place_slug")
    op.drop_table("place_photos")
    op.drop_table("places")
