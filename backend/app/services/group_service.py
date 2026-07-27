"""Group service: group management and user membership."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import text as sql_text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models.group_models import Group, UserGroupLink
from ..models.user_models import User

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Queries ──────────────────────────────────────────────────────────────────


async def list_groups(session: AsyncSession) -> list[Group]:
    """Return every group ordered by name."""
    result = await session.exec(select(Group).order_by(Group.name))
    return list(result.all())


async def get_granted_roles(
    session: AsyncSession, user_ids: Sequence[int]
) -> dict[int, list[str]]:
    """Return, per user id, the roles granted by the groups that user belongs to.

    Resolved for every user in one query so callers listing users do not issue a
    membership lookup per row.
    """
    if not user_ids:
        return {}
    result = await session.exec(
        select(UserGroupLink.user_id, Group.role)
        .join(Group, onclause=col(Group.id) == col(UserGroupLink.group_id))
        .where(col(UserGroupLink.user_id).in_(user_ids))
    )
    granted: dict[int, list[str]] = {}
    for user_id, role in result.all():
        if user_id is not None:
            granted.setdefault(user_id, []).append(role)
    return granted


async def get_group(session: AsyncSession, group_id: int) -> Group | None:
    """Return a group by primary key, or None."""
    return await session.get(Group, group_id)


async def get_group_members(session: AsyncSession, group_id: int) -> list[User]:
    """Return all users in a group, ordered by username."""
    result = await session.exec(
        select(User)
        .join(UserGroupLink, onclause=col(User.id) == col(UserGroupLink.user_id))
        .where(UserGroupLink.group_id == group_id)
        .order_by(col(User.username))
    )
    return list(result.all())


async def get_group_member_ids(session: AsyncSession, group_id: int) -> list[int]:
    """Return IDs of all users in a group."""
    result = await session.exec(
        select(UserGroupLink.user_id)
        .where(UserGroupLink.group_id == group_id)
        .order_by(col(UserGroupLink.user_id))
    )
    return [user_id for user_id in result.all() if user_id is not None]


# ── Mutations ────────────────────────────────────────────────────────────────


async def create_group(
    session: AsyncSession, name: str, description: str = "", role: str = "guest"
) -> Group:
    """Create a new group granting ``role`` to its members."""
    group = Group(name=name, description=description, role=role)
    session.add(group)
    await session.commit()
    await session.refresh(group)
    logger.info(f"Created group: {group.name} (id={group.id}, role={group.role})")
    return group


async def update_group(
    session: AsyncSession,
    group: Group,
    name: str | None = None,
    description: str | None = None,
    role: str | None = None,
) -> Group:
    """Update group name, description and/or granted role."""
    if name is not None:
        group.name = name
    if description is not None:
        group.description = description
    if role is not None:
        group.role = role
    group.updated_at = _utcnow()
    session.add(group)
    await session.commit()
    await session.refresh(group)
    logger.info(f"Updated group: {group.name} (id={group.id}, role={group.role})")
    return group


async def delete_group(session: AsyncSession, group_id: int) -> None:
    """Delete a group and all its memberships."""
    group = await session.get(Group, group_id)
    if group is not None:
        await session.exec(
            sql_text("DELETE FROM user_group WHERE group_id = :group_id").bindparams(
                group_id=group_id
            )
        )
        await session.delete(group)
        await session.commit()
        logger.info(f"Deleted group: {group.name} (id={group.id})")


async def add_user_to_group(session: AsyncSession, group_id: int, user_id: int) -> None:
    """Add a user to a group."""
    await session.exec(
        sql_text(
            "INSERT INTO user_group (user_id, group_id) "
            "VALUES (:user_id, :group_id) "
            "ON CONFLICT DO NOTHING"
        ).bindparams(user_id=user_id, group_id=group_id)
    )
    await session.commit()
    logger.info(f"Added user {user_id} to group {group_id}")


async def remove_user_from_group(
    session: AsyncSession, group_id: int, user_id: int
) -> None:
    """Remove a user from a group."""
    await session.exec(
        sql_text(
            "DELETE FROM user_group WHERE group_id = :group_id AND user_id = :user_id"
        ).bindparams(group_id=group_id, user_id=user_id)
    )
    await session.commit()
    logger.info(f"Removed user {user_id} from group {group_id}")


async def remove_user_memberships(session: AsyncSession, user_id: int) -> None:
    """Drop every group membership of a user, without committing.

    Called just before deleting the account so the caller can wipe the
    memberships and the user itself in a single transaction.
    """
    await session.exec(
        sql_text("DELETE FROM user_group WHERE user_id = :user_id").bindparams(
            user_id=user_id
        )
    )


async def add_users_to_group(
    session: AsyncSession, group_id: int, user_ids: list[int]
) -> None:
    """Add multiple users to a group."""
    for user_id in user_ids:
        await session.exec(
            sql_text(
                "INSERT INTO user_group (user_id, group_id) "
                "VALUES (:user_id, :group_id) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(user_id=user_id, group_id=group_id)
        )
    await session.commit()
    logger.info(f"Added {len(user_ids)} users to group {group_id}")
