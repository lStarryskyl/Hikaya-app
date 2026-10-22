"""Create the staff accounts named in the environment. Safe to run on every start.

    python -m app.seed_staff

An account that already exists keeps its password; only its role is brought in line.
Only the operator who controls the environment can use this to grant a role.
"""

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db import dispose_engine, get_sessionmaker
from app.models import Role, User
from app.security import hash_password

log = logging.getLogger("hikaya.seed")

MIN_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class StaffSeed:
    email: str
    password: str
    role: Role
    display_name: str


def staff_from_settings(settings: Settings) -> list[StaffSeed]:
    candidates = [
        (settings.seed_admin_email, settings.seed_admin_password, Role.ADMIN, "Hikaya Admin"),
        (
            settings.seed_reviewer_email,
            settings.seed_reviewer_password,
            Role.REVIEWER,
            "Hikaya Reviewer",
        ),
    ]
    staff = []
    for email, password, role, name in candidates:
        if not email and not password:
            continue
        if not email or len(password) < MIN_PASSWORD_LENGTH:
            log.warning("Skipping %s: set both an email and a password of 8+ characters.", role)
            continue
        staff.append(StaffSeed(email, password, role, name))
    return staff


async def seed_staff(
    sessionmaker: async_sessionmaker[AsyncSession], entries: list[StaffSeed]
) -> list[str]:
    """Returns the emails of the accounts that were newly created."""
    created: list[str] = []
    async with sessionmaker() as session:
        for entry in entries:
            email = entry.email.strip().lower()
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user is None:
                password_hash = await asyncio.to_thread(hash_password, entry.password)
                session.add(
                    User(
                        email=email,
                        display_name=entry.display_name,
                        password_hash=password_hash,
                        role=entry.role.value,
                    )
                )
                created.append(email)
            elif user.role != entry.role:
                user.role = entry.role.value
        await session.commit()
    return created


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    entries = staff_from_settings(get_settings())
    if not entries:
        log.info("No staff accounts configured; nothing to seed.")
    else:
        created = await seed_staff(get_sessionmaker(), entries)
        log.info("Staff accounts ready (%d new): %s", len(created), ", ".join(created) or "none")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
