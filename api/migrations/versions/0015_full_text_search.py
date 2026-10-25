"""full-text search indexes (Arabic and English) over stories and their text layers

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-26
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

# These expressions must match app/search.py exactly, or the indexes are not used.
STORY = "to_tsvector('{cfg}'::regconfig, coalesce(title, '') || ' ' || coalesce(place_name, ''))"
LAYER = "jsonb_to_tsvector('{cfg}'::regconfig, segments, '[\"string\"]'::jsonb)"


def upgrade() -> None:
    for cfg in ("arabic", "english"):
        op.execute(f"CREATE INDEX ix_stories_search_{cfg} ON stories USING gin ({STORY.format(cfg=cfg)})")
        op.execute(f"CREATE INDEX ix_text_layers_search_{cfg} ON text_layers USING gin ({LAYER.format(cfg=cfg)})")


def downgrade() -> None:
    for cfg in ("arabic", "english"):
        op.execute(f"DROP INDEX IF EXISTS ix_text_layers_search_{cfg}")
        op.execute(f"DROP INDEX IF EXISTS ix_stories_search_{cfg}")
