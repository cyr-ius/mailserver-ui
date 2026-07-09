"""User management endpoints: list accounts and change local passwords."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from ..auth import SessionUser
from ..depends import get_session, require_admin
from ..exceptions import ConflictException, NotFoundException
from ..models.user_models import PasswordChangeRequest, UserCreate, UserPublic
from ..services import user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[SessionUser, Depends(require_admin)]


@router.get("", response_model=list[UserPublic])
async def list_users(
    session: SessionDep,
    _admin: AdminDep,
) -> list[UserPublic]:
    """List all local and OIDC users (admin only)."""
    return user_service.to_public_many(session, user_service.list_users(session))


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    session: SessionDep,
    _admin: AdminDep,
) -> UserPublic:
    """Create a local user (admin only).

    The account is created as a ``guest``; add it to a group to grant a role.
    """
    user = user_service.create_local_user(
        session, payload.username, payload.display_name, payload.password
    )
    return user_service.to_public(session, user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    session: SessionDep,
    admin: AdminDep,
) -> None:
    """Delete a user and its group memberships (admin only).

    Refuses to remove the caller's own account or the last administrator, both
    of which would lock the instance out of its own administration.
    """
    user = user_service.get_user(session, user_id)
    if user is None:
        raise NotFoundException("User", user_id)
    if user.username == admin.username:
        raise ConflictException("You cannot delete your own account")
    if user_service.is_last_admin(session, user):
        raise ConflictException("The last administrator account cannot be deleted")
    user_service.delete_user(session, user)


@router.patch("/{user_id}/password", response_model=UserPublic)
async def change_password(
    user_id: int,
    payload: PasswordChangeRequest,
    session: SessionDep,
    _admin: AdminDep,
) -> UserPublic:
    """Set a new password for a local user (admin only).

    OIDC accounts are managed by the identity provider and cannot be changed
    here.
    """
    user = user_service.get_user(session, user_id)
    if user is None:
        raise NotFoundException("User", user_id)
    if user.provider != "local":
        raise ConflictException("Password is managed by the identity provider for OIDC users")
    updated = user_service.set_password(session, user, payload.new_password)
    return user_service.to_public(session, updated)
