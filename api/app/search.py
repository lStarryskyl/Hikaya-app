"""Full-text search with PostgreSQL's built-in Arabic and English configurations.

A word matches its other forms: the Arabic stemmer finds الحكايات for حكاية and الحارة for
حارة; the English one finds "stories" for "story". Broken plurals (فوانيس for فانوس) are
beyond a light stemmer. The expressions here match the GIN indexes in migration 0015 exactly,
so the indexes are used.
"""

from sqlalchemy import ColumnElement, func, literal_column, or_

from app.models import Story, TextLayer

CONFIGS = ("arabic", "english")


def _config(name: str):
    return literal_column(f"'{name}'::regconfig")


def _query(name: str, q: str):
    return func.websearch_to_tsquery(_config(name), q)


def story_matches(q: str) -> ColumnElement[bool]:
    """Title or place, in either language's word forms."""
    # Constants are written as SQL, not bound parameters, so the expression is the indexed one.
    empty, space = literal_column("''"), literal_column("' '")
    document = (
        func.coalesce(Story.title, empty)
        .op("||")(space)
        .op("||")(func.coalesce(Story.place_name, empty))
    )
    return or_(*(func.to_tsvector(_config(c), document).op("@@")(_query(c, q)) for c in CONFIGS))


def layer_matches(q: str) -> ColumnElement[bool]:
    """Any text layer's segment texts (timestamps are numbers, so they are left out)."""
    strings = literal_column("'[\"string\"]'::jsonb")
    return or_(
        *(
            func.jsonb_to_tsvector(_config(c), TextLayer.segments, strings).op("@@")(_query(c, q))
            for c in CONFIGS
        )
    )
