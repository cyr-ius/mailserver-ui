"""User service: persistence-backed authentication and account management.

Encapsulates all database access for users so routers and the auth layer stay
free of query logic. Local users authenticate against a stored bcrypt hash;
OIDC users are provisioned/refreshed on each successful sign-in.
"""

import logging
import secrets
from datetime import UTC, datetime

from sqlmodel import Session, select

from ..auth import (
    Role,
    SessionUser,
    hash_password,
    highest_role,
    normalize_role,
    verify_password,
)
from ..config import settings
from ..exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from ..models.user_models import User, UserPublic
from ..services import api_key_service, group_service

logger = logging.getLogger(__name__)

# Length (in bytes) of the randomly generated default admin password.
_GENERATED_PASSWORD_BYTES = 24


# ── Role resolution ──────────────────────────────────────────────────────────


def resolve_role(session: Session, user: User) -> Role:
    """Return the effective role of ``user``.

    An account carries a role of its own (set by the OIDC group claims, or
    ``admin`` for the seeded administrator). Membership in a local group can only
    raise it: the effective role is the most privileged of the two sources.
    """
    granted = group_service.get_granted_roles(session, [user.id] if user.id else [])
    return highest_role([user.role, *granted.get(user.id or 0, [])])


def to_session_user(session: Session, user: User) -> SessionUser:
    """Map a persisted user to the session principal carried by the cookie."""
    return SessionUser(
        username=user.username,
        display_name=user.display_name or user.username,
        role=resolve_role(session, user),
        provider="oidc" if user.provider == "oidc" else "local",
    )


def _to_public(user: User, effective_role: Role) -> UserPublic:
    data = user.model_dump(exclude={"password_hash", "updated_at", "role"})
    return UserPublic(**data, role=normalize_role(user.role), effective_role=effective_role)


def to_public(session: Session, user: User) -> UserPublic:
    """Map a persisted user to its API representation, effective role included."""
    return _to_public(user, resolve_role(session, user))


def to_public_many(session: Session, users: list[User]) -> list[UserPublic]:
    """Map several users at once, resolving every group membership in one query."""
    granted = group_service.get_granted_roles(session, [u.id for u in users if u.id])
    return [
        _to_public(user, highest_role([user.role, *granted.get(user.id or 0, [])]))
        for user in users
    ]


# ── Queries ──────────────────────────────────────────────────────────────────


def list_users(session: Session) -> list[User]:
    """Return every user ordered by username."""
    return list(session.exec(select(User).order_by(User.username)).all())


def get_user(session: Session, user_id: int) -> User | None:
    """Return a user by primary key, or None."""
    return session.get(User, user_id)


def get_by_username(session: Session, username: str) -> User | None:
    """Return a user by username, or None."""
    return session.exec(select(User).where(User.username == username)).first()


# ── Authentication ───────────────────────────────────────────────────────────


def authenticate_local(session: Session, username: str, password: str) -> SessionUser | None:
    """Validate local credentials against the stored hash.

    A deactivated account is refused exactly like a wrong password: the caller
    gets no signal about which of the two it was.
    """
    user = get_by_username(session, username)
    if user is None or user.provider != "local" or not user.password_hash:
        # Run a dummy hash comparison to keep timing roughly uniform.
        verify_password(password, "$2b$12$" + "." * 53)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        logger.warning("Login refused for deactivated account %s", user.username)
        return None
    _touch_login(session, user)
    return to_session_user(session, user)


def upsert_oidc_user(session: Session, principal: SessionUser) -> SessionUser:
    """Create or refresh the local record mirroring an OIDC principal.

    ``principal.role`` is the role derived from the provider's group claims; it
    overwrites the account role on every sign-in. The returned principal carries
    the effective role, so a guest promoted through a local group keeps the
    privileges the administrator granted them.

    An identity provider is free to assert any username, including one that
    already belongs to a *local* account — the seeded administrator being the
    obvious target. Converting that account would hand its privileges to whoever
    controls the provider, so the sign-in is refused instead: the two namespaces
    stay separate, and an administrator who wants the account on SSO deletes the
    local one first.
    """
    user = get_by_username(session, principal.username)
    if user is not None and user.provider != "oidc":
        raise ConflictException(
            f"A local account named {principal.username} already exists; "
            "an OIDC identity cannot take it over"
        )
    if user is None:
        user = User(
            username=principal.username,
            display_name=principal.display_name,
            role=principal.role,
            provider="oidc",
            password_hash=None,
        )
    else:
        if not user.is_active:
            raise ForbiddenException(f"The account {principal.username} is deactivated")
        user.display_name = principal.display_name
        user.role = principal.role
    user.last_login_at = _now()
    user.updated_at = _now()
    session.add(user)
    session.commit()
    session.refresh(user)
    return to_session_user(session, user)


# ── Mutations ────────────────────────────────────────────────────────────────


def create_local_user(
    session: Session,
    username: str,
    display_name: str,
    password: str,
) -> User:
    """Create a local account authenticating against a stored bcrypt hash.

    The account starts as ``guest``; privileges are granted by adding it to a
    local group (see :func:`resolve_role`).
    """
    username = username.strip()
    if not username:
        raise BadRequestException("A username is required")
    if get_by_username(session, username) is not None:
        raise ConflictException(f"User {username} already exists")

    user = User(
        username=username,
        display_name=display_name.strip(),
        role="guest",
        provider="local",
        password_hash=hash_password(password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info("Created local user %s (id=%s)", user.username, user.id)
    return user


def is_last_admin(session: Session, user: User) -> bool:
    """Return True when ``user`` is the only *active* account with an admin role.

    Deleting or deactivating it would leave the instance with no way to
    administer itself, so callers reject the operation. A deactivated
    administrator does not count: it cannot sign in, so it cannot be the one that
    keeps the instance administrable.
    """
    if not user.is_active or resolve_role(session, user) != "admin":
        return False
    active_admins = [
        public
        for public in to_public_many(session, list_users(session))
        if public.effective_role == "admin" and public.is_active
    ]
    return len(active_admins) <= 1


def set_active(session: Session, user: User, is_active: bool) -> User:
    """Activate or deactivate an account, local or OIDC.

    Deactivating the last active administrator is refused: it would lock the
    instance out of its own administration.
    """
    if not is_active and is_last_admin(session, user):
        raise ConflictException("The last active administrator account cannot be deactivated")

    user.is_active = is_active
    user.updated_at = _now()
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info("User %s %s", user.username, "activated" if is_active else "deactivated")
    return user


def delete_user(session: Session, user: User) -> None:
    """Delete a user along with every group membership and API key it holds."""
    if user.id is not None:
        group_service.remove_user_memberships(session, user.id)
        api_key_service.delete_for_user(session, user.id)
    username = user.username
    session.delete(user)
    session.commit()
    logger.info("Deleted user %s", username)


def change_own_password(
    session: Session,
    username: str,
    current_password: str,
    new_password: str,
) -> User:
    """Let a local user rotate their own password after proving the current one.

    OIDC accounts have no local hash to replace: their credentials live in the
    identity provider.
    """
    user = get_by_username(session, username)
    if user is None:
        raise NotFoundException("User", username)
    if user.provider != "local" or not user.password_hash:
        raise ConflictException("Password is managed by the identity provider for OIDC users")
    if not verify_password(current_password, user.password_hash):
        raise BadRequestException("The current password is incorrect")
    if current_password == new_password:
        raise BadRequestException("The new password must differ from the current one")
    return set_password(session, user, new_password)


def set_password(session: Session, user: User, new_password: str) -> User:
    """Set a new bcrypt password hash for a local user."""
    user.password_hash = hash_password(new_password)
    user.updated_at = _now()
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info("Password changed for user %s", user.username)
    return user


def ensure_default_admin(session: Session) -> None:
    """Seed a default admin with a random password when none exists.

    The generated password is printed once to the logs; there is no other way
    to recover it, so it must be captured on first startup.
    """
    existing = session.exec(
        select(User).where(User.role == "admin", User.provider == "local")
    ).first()
    if existing is not None:
        return

    password = secrets.token_urlsafe(_GENERATED_PASSWORD_BYTES)
    admin = User(
        username=settings.admin_username,
        display_name=settings.admin_username,
        role="admin",
        provider="local",
        password_hash=hash_password(password),
    )
    session.add(admin)
    session.commit()
    logger.warning(
        "No admin account found — created default admin '%s'.\n"
        "  ==> Generated password: %s\n"
        "  Store it now: it is shown only once and cannot be recovered.",
        settings.admin_username,
        password,
    )


# ── Internal helpers ─────────────────────────────────────────────────────────


def _now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def _touch_login(session: Session, user: User) -> None:
    """Record the user's last successful login time."""
    user.last_login_at = _now()
    session.add(user)
    session.commit()
