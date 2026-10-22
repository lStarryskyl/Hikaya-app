"""Who may see a story and its files."""

from app.models import Role, Story, StoryStatus, User

STAFF_ROLES = {Role.REVIEWER.value, Role.ADMIN.value}


def can_view(story: Story, user: User | None) -> bool:
    """Published stories are public; anything else is for its author and staff only."""
    if story.status == StoryStatus.PUBLISHED:
        return True
    return user is not None and (user.id == story.author_id or user.role in STAFF_ROLES)
