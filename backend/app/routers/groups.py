"""Group management endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlmodel import Session

from ..auth import SessionUser
from ..depends import get_session, require_admin
from ..exceptions import NotFoundException
from ..models.group_models import GroupPublic, GroupWithMembers, GroupWrite
from ..models.user_models import UserPublic
from ..services import group_service, user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/groups", tags=["groups"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[SessionUser, Depends(require_admin)]


class AddUsersPayload(BaseModel):
    """Payload for adding multiple users to a group."""

    user_ids: list[int]


@router.get("", response_model=list[GroupWithMembers])
async def list_groups(
    session: SessionDep,
    _admin: AdminDep,
) -> list[GroupWithMembers]:
    """List all groups with member count (admin only)."""
    groups = group_service.list_groups(session)
    result = []
    for group in groups:
        member_ids = group_service.get_group_member_ids(session, group.id)
        result.append(
            GroupWithMembers(
                id=group.id,
                name=group.name,
                description=group.description,
                role=group.role,
                created_at=group.created_at,
                updated_at=group.updated_at,
                member_count=len(member_ids),
            )
        )
    return result


@router.post("", response_model=GroupPublic)
async def create_group(
    payload: GroupWrite,
    session: SessionDep,
    _admin: AdminDep,
) -> GroupPublic:
    """Create a new group granting a role to its members (admin only)."""
    group = group_service.create_group(
        session, payload.name, payload.description, payload.role
    )
    return GroupPublic.model_validate(group, from_attributes=True)


@router.patch("/{group_id}", response_model=GroupPublic)
async def update_group(
    group_id: int,
    payload: GroupWrite,
    session: SessionDep,
    _admin: AdminDep,
) -> GroupPublic:
    """Update a group's name, description and granted role (admin only)."""
    group = group_service.get_group(session, group_id)
    if group is None:
        raise NotFoundException("Group", group_id)
    updated = group_service.update_group(
        session, group, payload.name, payload.description, payload.role
    )
    return GroupPublic.model_validate(updated, from_attributes=True)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    session: SessionDep,
    _admin: AdminDep,
) -> None:
    """Delete a group (admin only)."""
    group = group_service.get_group(session, group_id)
    if group is None:
        raise NotFoundException("Group", group_id)
    group_service.delete_group(session, group_id)


@router.get("/{group_id}/members", response_model=list[UserPublic])
async def get_group_members(
    group_id: int,
    session: SessionDep,
    _admin: AdminDep,
) -> list[UserPublic]:
    """Get all members of a group (admin only)."""
    group = group_service.get_group(session, group_id)
    if group is None:
        raise NotFoundException("Group", group_id)
    members = group_service.get_group_members(session, group_id)
    return user_service.to_public_many(session, members)


# Declared before /{user_id}: a literal path segment must be matched before the
# catch-all converter, otherwise "batch" is parsed as a user id.
@router.post("/{group_id}/members/batch", status_code=status.HTTP_204_NO_CONTENT)
async def add_users_to_group(
    group_id: int,
    payload: AddUsersPayload,
    session: SessionDep,
    _admin: AdminDep,
) -> None:
    """Add multiple users to a group (admin only)."""
    group = group_service.get_group(session, group_id)
    if group is None:
        raise NotFoundException("Group", group_id)
    for user_id in payload.user_ids:
        if user_service.get_user(session, user_id) is None:
            raise NotFoundException("User", user_id)
    group_service.add_users_to_group(session, group_id, payload.user_ids)


@router.post("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_user_to_group(
    group_id: int,
    user_id: int,
    session: SessionDep,
    _admin: AdminDep,
) -> None:
    """Add a user to a group (admin only)."""
    group = group_service.get_group(session, group_id)
    if group is None:
        raise NotFoundException("Group", group_id)
    user = user_service.get_user(session, user_id)
    if user is None:
        raise NotFoundException("User", user_id)
    group_service.add_user_to_group(session, group_id, user_id)


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_group(
    group_id: int,
    user_id: int,
    session: SessionDep,
    _admin: AdminDep,
) -> None:
    """Remove a user from a group (admin only)."""
    group = group_service.get_group(session, group_id)
    if group is None:
        raise NotFoundException("Group", group_id)
    group_service.remove_user_from_group(session, group_id, user_id)
