"""User management endpoints: list accounts and change local passwords."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth import SessionUser
from app.depends import get_session, require_admin
from app.exceptions import ConflictException, NotFoundException
from app.services import user_service
from app.user_models import PasswordChangeRequest, UserPublic

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
    return [
        UserPublic.model_validate(u, from_attributes=True) for u in user_service.list_users(session)
    ]


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
    return UserPublic.model_validate(updated, from_attributes=True)
