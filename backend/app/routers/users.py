"""User endpoints: self-service profile, plus administrative account management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from ..auth import SessionUser
from ..depends import get_session, require_admin, require_session_login, require_user
from ..exceptions import ConflictException, NotFoundException
from ..models.api_key_models import ApiKey, ApiKeyCreate, ApiKeyCreated, ApiKeyPublic
from ..models.user_models import (
    PasswordChangeRequest,
    SelfPasswordChangeRequest,
    User,
    UserCreate,
    UserPublic,
)
from ..services import api_key_service, user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[SessionUser, Depends(require_admin)]
UserDep = Annotated[SessionUser, Depends(require_user)]
#: API keys are managed from the browser only — never with a key itself.
InteractiveDep = Annotated[SessionUser, Depends(require_session_login)]


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


# ── Self-service ─────────────────────────────────────────────────────────────
# Declared before the "/{user_id}" routes so "me" is never parsed as an id.


def _own_account(session: Session, user: SessionUser) -> User:
    """Return the persisted account behind the current principal."""
    account = user_service.get_by_username(session, user.username)
    if account is None:
        raise NotFoundException("User", user.username)
    return account


@router.get("/me", response_model=UserPublic)
async def read_own_profile(session: SessionDep, user: UserDep) -> UserPublic:
    """Return the profile of the caller, group-granted role included."""
    return user_service.to_public(session, _own_account(session, user))


@router.patch("/me/password", response_model=UserPublic)
async def change_own_password(
    payload: SelfPasswordChangeRequest,
    session: SessionDep,
    user: UserDep,
) -> UserPublic:
    """Let the caller rotate their own password, proving the current one first."""
    updated = user_service.change_own_password(
        session, user.username, payload.current_password, payload.new_password
    )
    return user_service.to_public(session, updated)


# ── Personal API keys ────────────────────────────────────────────────────────
# Bearer credentials the caller issues to itself to drive the REST API from a
# script. A key inherits the effective role of its owner; it grants nothing more.


@router.get("/me/api-keys", response_model=list[ApiKeyPublic])
async def list_own_api_keys(session: SessionDep, user: UserDep) -> list[ApiKey]:
    """List the API keys owned by the caller. Secrets are never returned."""
    account = _own_account(session, user)
    return api_key_service.list_for_user(session, account.id or 0)


@router.post("/me/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_own_api_key(
    payload: ApiKeyCreate,
    session: SessionDep,
    user: InteractiveDep,
) -> ApiKeyCreated:
    """Issue an API key for the caller.

    The plaintext key is returned once, here: only its digest is stored, so a
    key that is lost has to be revoked and reissued.
    """
    account = _own_account(session, user)
    key, raw_key = api_key_service.create(session, account, payload.name, payload.expires_in_days)
    return ApiKeyCreated(**key.model_dump(exclude={"user_id", "key_hash"}), key=raw_key)


@router.delete("/me/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_own_api_key(
    key_id: int,
    session: SessionDep,
    user: InteractiveDep,
) -> None:
    """Revoke one of the caller's API keys, refusing any key it does not own."""
    account = _own_account(session, user)
    key = api_key_service.get_for_user(session, key_id, account.id or 0)
    if key is None:
        raise NotFoundException("API key", key_id)
    api_key_service.delete_key(session, key)


# ── Administration ───────────────────────────────────────────────────────────


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
