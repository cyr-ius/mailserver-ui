"""Group service: group management and user membership."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import text as sql_text
from sqlmodel import Session, col, select

from ..models.group_models import Group, UserGroupLink
from ..models.user_models import User

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Queries ──────────────────────────────────────────────────────────────────


def list_groups(session: Session) -> list[Group]:
    """Return every group ordered by name."""
    return list(session.exec(select(Group).order_by(Group.name)).all())


def get_granted_roles(session: Session, user_ids: Sequence[int]) -> dict[int, list[str]]:
    """Return, per user id, the roles granted by the groups that user belongs to.

    Resolved for every user in one query so callers listing users do not issue a
    membership lookup per row.
    """
    if not user_ids:
        return {}
    rows = session.exec(
        select(UserGroupLink.user_id, Group.role)
        .join(Group, onclause=col(Group.id) == col(UserGroupLink.group_id))
        .where(col(UserGroupLink.user_id).in_(user_ids))
    ).all()
    granted: dict[int, list[str]] = {}
    for user_id, role in rows:
        if user_id is not None:
            granted.setdefault(user_id, []).append(role)
    return granted


def get_group(session: Session, group_id: int) -> Group | None:
    """Return a group by primary key, or None."""
    return session.get(Group, group_id)


def get_group_members(session: Session, group_id: int) -> list[User]:
    """Return all users in a group, ordered by username."""
    return list(
        session.exec(
            select(User)
            .join(UserGroupLink, onclause=col(User.id) == col(UserGroupLink.user_id))
            .where(UserGroupLink.group_id == group_id)
            .order_by(col(User.username))
        ).all()
    )


def get_group_member_ids(session: Session, group_id: int) -> list[int]:
    """Return IDs of all users in a group."""
    rows = session.exec(
        select(UserGroupLink.user_id)
        .where(UserGroupLink.group_id == group_id)
        .order_by(col(UserGroupLink.user_id))
    ).all()
    return [user_id for user_id in rows if user_id is not None]


# ── Mutations ────────────────────────────────────────────────────────────────


def create_group(session: Session, name: str, description: str = "", role: str = "guest") -> Group:
    """Create a new group granting ``role`` to its members."""
    group = Group(name=name, description=description, role=role)
    session.add(group)
    session.commit()
    session.refresh(group)
    logger.info(f"Created group: {group.name} (id={group.id}, role={group.role})")
    return group


def update_group(
    session: Session,
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
    session.commit()
    session.refresh(group)
    logger.info(f"Updated group: {group.name} (id={group.id}, role={group.role})")
    return group


def delete_group(session: Session, group_id: int) -> None:
    """Delete a group and all its memberships."""
    group = session.get(Group, group_id)
    if group is not None:
        session.exec(
            sql_text("DELETE FROM user_group WHERE group_id = :group_id").bindparams(
                group_id=group_id
            )
        )
        session.delete(group)
        session.commit()
        logger.info(f"Deleted group: {group.name} (id={group.id})")


def add_user_to_group(session: Session, group_id: int, user_id: int) -> None:
    """Add a user to a group."""
    session.exec(
        sql_text(
            "INSERT INTO user_group (user_id, group_id) "
            "VALUES (:user_id, :group_id) "
            "ON CONFLICT DO NOTHING"
        ).bindparams(user_id=user_id, group_id=group_id)
    )
    session.commit()
    logger.info(f"Added user {user_id} to group {group_id}")


def remove_user_from_group(session: Session, group_id: int, user_id: int) -> None:
    """Remove a user from a group."""
    session.exec(
        sql_text(
            "DELETE FROM user_group WHERE group_id = :group_id AND user_id = :user_id"
        ).bindparams(group_id=group_id, user_id=user_id)
    )
    session.commit()
    logger.info(f"Removed user {user_id} from group {group_id}")


def remove_user_memberships(session: Session, user_id: int) -> None:
    """Drop every group membership of a user, without committing.

    Called just before deleting the account so the caller can wipe the
    memberships and the user itself in a single transaction.
    """
    session.exec(
        sql_text("DELETE FROM user_group WHERE user_id = :user_id").bindparams(user_id=user_id)
    )


def add_users_to_group(session: Session, group_id: int, user_ids: list[int]) -> None:
    """Add multiple users to a group."""
    for user_id in user_ids:
        session.exec(
            sql_text(
                "INSERT INTO user_group (user_id, group_id) "
                "VALUES (:user_id, :group_id) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(user_id=user_id, group_id=group_id)
        )
    session.commit()
    logger.info(f"Added {len(user_ids)} users to group {group_id}")
