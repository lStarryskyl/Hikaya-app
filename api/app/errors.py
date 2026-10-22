"""Errors whose message is safe and useful to show to a member as-is."""


class UserFacingError(Exception):
    """Raise from a job to fail it with this exact message shown to the author."""


# Marks a stored job error as internal detail that members must never see.
INTERNAL_PREFIX = "internal: "
