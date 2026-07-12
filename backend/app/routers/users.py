"""User endpoints: self-service profile, plus administrative account management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlmodel import Session

from ..auth import SessionUser
from ..depends import get_session, require_admin, require_session_login, require_user
from ..exceptions import ConflictException, NotFoundException
from ..models.pat_models import Pat, PatCreate, PatCreated, PatPublic
from ..models.user_models import (
    PasswordChangeRequest,
    SelfPasswordChangeRequest,
    User,
    UserCreate,
    UserPublic,
    UserStatusUpdate,
)
from ..services import audit_service, pat_service, user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[SessionUser, Depends(require_admin)]
UserDep = Annotated[SessionUser, Depends(require_user)]
#: Tokens are managed from the browser only — never with a token itself.
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
    request: Request,
    session: SessionDep,
    admin: AdminDep,
) -> UserPublic:
    """Create a local user (admin only).

    The account is created as a ``guest``; add it to a group to grant a role.
    """
    user = user_service.create_local_user(
        session, payload.username, payload.display_name, payload.password
    )
    await audit_service.record(
        session,
        request=request,
        category="user",
        action="user.create",
        actor=admin.username,
        target=user.username,
        detail="Local account created",
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
    request: Request,
    session: SessionDep,
    user: UserDep,
) -> UserPublic:
    """Let the caller rotate their own password, proving the current one first."""
    updated = user_service.change_own_password(
        session, user.username, payload.current_password, payload.new_password
    )
    await audit_service.record(
        session,
        request=request,
        category="user",
        action="user.password.change",
        actor=user.username,
        target=user.username,
        detail="Own password rotated",
    )
    return user_service.to_public(session, updated)


# ── Personal access tokens ───────────────────────────────────────────────────
# Bearer credentials the caller issues to itself to drive the REST API from a
# script. A token inherits the effective role of its owner; it grants nothing
# more, and is presented as ``Authorization: Bearer <token>``.


@router.get("/me/pats", response_model=list[PatPublic])
async def list_own_pats(session: SessionDep, user: UserDep) -> list[Pat]:
    """List the tokens owned by the caller. Secrets are never returned."""
    account = _own_account(session, user)
    return pat_service.list_for_user(session, account.id or 0)


@router.post("/me/pats", response_model=PatCreated, status_code=status.HTTP_201_CREATED)
async def create_own_pat(
    payload: PatCreate,
    request: Request,
    session: SessionDep,
    user: InteractiveDep,
) -> PatCreated:
    """Issue a personal access token for the caller.

    The token is returned once, here: only its digest is stored, so a token that
    is lost has to be revoked and reissued.
    """
    account = _own_account(session, user)
    pat, raw_token = pat_service.create(
        session, account, payload.name, payload.expires_in_days
    )
    await audit_service.record(
        session,
        request=request,
        category="pat",
        action="pat.create",
        actor=user.username,
        target=pat.name,
        detail=f"expires_at={pat.expires_at or 'never'}",
    )
    return PatCreated(
        **pat.model_dump(exclude={"user_id", "token_hash"}),
        token=raw_token,
    )


@router.delete("/me/pats/{pat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_own_pat(
    pat_id: int,
    request: Request,
    session: SessionDep,
    user: InteractiveDep,
) -> None:
    """Revoke one of the caller's tokens, refusing any token it does not own."""
    account = _own_account(session, user)
    pat = pat_service.get_for_user(session, pat_id, account.id or 0)
    if pat is None:
        raise NotFoundException("Personal access token", pat_id)
    name = pat.name
    pat_service.delete_pat(session, pat)
    await audit_service.record(
        session,
        request=request,
        category="pat",
        action="pat.revoke",
        actor=user.username,
        target=name,
    )


# ── Administration ───────────────────────────────────────────────────────────


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    request: Request,
    session: SessionDep,
    admin: AdminDep,
) -> None:
    """Delete a user and its group memberships (admin only).

    Refuses to remove the caller's own account or the last active administrator,
    both of which would lock the instance out of its own administration.
    """
    user = user_service.get_user(session, user_id)
    if user is None:
        raise NotFoundException("User", user_id)
    if user.username == admin.username:
        raise ConflictException("You cannot delete your own account")
    if user_service.is_last_admin(session, user):
        raise ConflictException(
            "The last active administrator account cannot be deleted"
        )
    username = user.username
    user_service.delete_user(session, user)
    await audit_service.record(
        session,
        request=request,
        category="user",
        action="user.delete",
        actor=admin.username,
        target=username,
        detail="Account, group memberships and personal access tokens removed",
    )


@router.patch("/{user_id}/status", response_model=UserPublic)
async def set_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    request: Request,
    session: SessionDep,
    admin: AdminDep,
) -> UserPublic:
    """Activate or deactivate an account, local or OIDC (admin only).

    A deactivated account keeps its data but can no longer authenticate, and the
    sessions and tokens it still holds stop working on their next request.
    Refuses to deactivate the caller's own account or the last active
    administrator.
    """
    user = user_service.get_user(session, user_id)
    if user is None:
        raise NotFoundException("User", user_id)
    if not payload.is_active and user.username == admin.username:
        raise ConflictException("You cannot deactivate your own account")

    updated = user_service.set_active(session, user, payload.is_active)
    await audit_service.record(
        session,
        request=request,
        category="user",
        action="user.activate" if payload.is_active else "user.deactivate",
        actor=admin.username,
        target=updated.username,
        detail=f"provider={updated.provider}",
    )
    return user_service.to_public(session, updated)


@router.patch("/{user_id}/password", response_model=UserPublic)
async def change_password(
    user_id: int,
    payload: PasswordChangeRequest,
    request: Request,
    session: SessionDep,
    admin: AdminDep,
) -> UserPublic:
    """Set a new password for a local user (admin only).

    OIDC accounts are managed by the identity provider and cannot be changed
    here.
    """
    user = user_service.get_user(session, user_id)
    if user is None:
        raise NotFoundException("User", user_id)
    if user.provider != "local":
        raise ConflictException(
            "Password is managed by the identity provider for OIDC users"
        )
    updated = user_service.set_password(session, user, payload.new_password)
    await audit_service.record(
        session,
        request=request,
        category="user",
        action="user.password.reset",
        actor=admin.username,
        target=updated.username,
        detail="Password reset by an administrator",
    )
    return user_service.to_public(session, updated)
