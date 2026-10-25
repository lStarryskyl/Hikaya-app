"""One normalization rule for stored tags and discovery filters."""

import unicodedata


def normalize_tag(value: str) -> str:
    tag = unicodedata.normalize("NFKC", value).strip().casefold()
    if not 1 <= len(tag) <= 40:
        raise ValueError("Tags must contain 1 to 40 characters.")
    return tag
