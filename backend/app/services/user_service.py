"""User service: persistence-backed authentication and account management.

Encapsulates all database access for users so routers and the auth layer stay
free of query logic. Local users authenticate against a stored bcrypt hash;
OIDC users are provisioned/refreshed on each successful sign-in.
"""

import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

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
from ..services import group_service, pat_service

logger = logging.getLogger(__name__)

# Length (in bytes) of the randomly generated default admin password.
_GENERATED_PASSWORD_BYTES = 24


# ── Role resolution ──────────────────────────────────────────────────────────


async def resolve_role(session: AsyncSession, user: User) -> Role:
    """Return the effective role of ``user``.

    An account carries a role of its own (set by the OIDC group claims, or
    ``admin`` for the seeded administrator). Membership in a local group can only
    raise it: the effective role is the most privileged of the two sources.
    """
    granted = await group_service.get_granted_roles(
        session, [user.id] if user.id else []
    )
    return highest_role([user.role, *granted.get(user.id or 0, [])])


async def to_session_user(session: AsyncSession, user: User) -> SessionUser:
    """Map a persisted user to the session principal carried by the cookie."""
    return SessionUser(
        username=user.username,
        display_name=user.display_name or user.username,
        role=await resolve_role(session, user),
        provider="oidc" if user.provider == "oidc" else "local",
    )


def _to_public(user: User, effective_role: Role) -> UserPublic:
    data = user.model_dump(exclude={"password_hash", "updated_at", "role"})
    return UserPublic(
        **data, role=normalize_role(user.role), effective_role=effective_role
    )


async def to_public(session: AsyncSession, user: User) -> UserPublic:
    """Map a persisted user to its API representation, effective role included."""
    return _to_public(user, await resolve_role(session, user))


async def to_public_many(session: AsyncSession, users: list[User]) -> list[UserPublic]:
    """Map several users at once, resolving every group membership in one query."""
    granted = await group_service.get_granted_roles(
        session, [u.id for u in users if u.id]
    )
    return [
        _to_public(user, highest_role([user.role, *granted.get(user.id or 0, [])]))
        for user in users
    ]


# ── Queries ──────────────────────────────────────────────────────────────────


async def list_users(session: AsyncSession) -> list[User]:
    """Return every user ordered by username."""
    result = await session.exec(select(User).order_by(User.username))
    return list(result.all())


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    """Return a user by primary key, or None."""
    return await session.get(User, user_id)


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    """Return a user by username, or None."""
    result = await session.exec(select(User).where(User.username == username))
    return result.first()


# ── Authentication ───────────────────────────────────────────────────────────


async def authenticate_local(
    session: AsyncSession, username: str, password: str
) -> SessionUser | None:
    """Validate local credentials against the stored hash.

    A deactivated account is refused exactly like a wrong password: the caller
    gets no signal about which of the two it was.
    """
    user = await get_by_username(session, username)
    if user is None or user.provider != "local" or not user.password_hash:
        # Run a dummy hash comparison to keep timing roughly uniform.
        verify_password(password, "$2b$12$" + "." * 53)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        logger.warning("Login refused for deactivated account %s", user.username)
        return None
    await _touch_login(session, user)
    return await to_session_user(session, user)


async def upsert_oidc_user(
    session: AsyncSession, principal: SessionUser
) -> SessionUser:
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
    user = await get_by_username(session, principal.username)
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
    await session.commit()
    await session.refresh(user)
    return await to_session_user(session, user)


# ── Mutations ────────────────────────────────────────────────────────────────


async def create_local_user(
    session: AsyncSession,
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
    if await get_by_username(session, username) is not None:
        raise ConflictException(f"User {username} already exists")

    user = User(
        username=username,
        display_name=display_name.strip(),
        role="guest",
        provider="local",
        password_hash=hash_password(password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("Created local user %s (id=%s)", user.username, user.id)
    return user


async def is_last_admin(session: AsyncSession, user: User) -> bool:
    """Return True when ``user`` is the only *active* account with an admin role.

    Deleting or deactivating it would leave the instance with no way to
    administer itself, so callers reject the operation. A deactivated
    administrator does not count: it cannot sign in, so it cannot be the one that
    keeps the instance administrable.
    """
    if not user.is_active or await resolve_role(session, user) != "admin":
        return False
    users = await list_users(session)
    active_admins = [
        public
        for public in await to_public_many(session, users)
        if public.effective_role == "admin" and public.is_active
    ]
    return len(active_admins) <= 1


async def set_active(session: AsyncSession, user: User, is_active: bool) -> User:
    """Activate or deactivate an account, local or OIDC.

    Deactivating the last active administrator is refused: it would lock the
    instance out of its own administration.
    """
    if not is_active and await is_last_admin(session, user):
        raise ConflictException(
            "The last active administrator account cannot be deactivated"
        )

    user.is_active = is_active
    user.updated_at = _now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info(
        "User %s %s", user.username, "activated" if is_active else "deactivated"
    )
    return user


async def delete_user(session: AsyncSession, user: User) -> None:
    """Delete a user along with every group membership and token it holds."""
    if user.id is not None:
        await group_service.remove_user_memberships(session, user.id)
        await pat_service.delete_for_user(session, user.id)
    username = user.username
    await session.delete(user)
    await session.commit()
    logger.info("Deleted user %s", username)


async def change_own_password(
    session: AsyncSession,
    username: str,
    current_password: str,
    new_password: str,
) -> User:
    """Let a local user rotate their own password after proving the current one.

    OIDC accounts have no local hash to replace: their credentials live in the
    identity provider.
    """
    user = await get_by_username(session, username)
    if user is None:
        raise NotFoundException("User", username)
    if user.provider != "local" or not user.password_hash:
        raise ConflictException(
            "Password is managed by the identity provider for OIDC users"
        )
    if not verify_password(current_password, user.password_hash):
        raise BadRequestException("The current password is incorrect")
    if current_password == new_password:
        raise BadRequestException("The new password must differ from the current one")
    return await set_password(session, user, new_password)


async def set_password(session: AsyncSession, user: User, new_password: str) -> User:
    """Set a new bcrypt password hash for a local user."""
    user.password_hash = hash_password(new_password)
    user.updated_at = _now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("Password changed for user %s", user.username)
    return user


async def ensure_default_admin(session: AsyncSession) -> None:
    """Seed a default admin with a random password when none exists.

    The generated password is printed once to the logs; there is no other way
    to recover it, so it must be captured on first startup.
    """
    result = await session.exec(
        select(User).where(User.role == "admin", User.provider == "local")
    )
    existing = result.first()
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
    try:
        await session.commit()
    except IntegrityError:
        # Lost the race against a sibling worker seeding the same admin
        # account concurrently on first boot: it already exists now.
        await session.rollback()
        logger.info("Default admin already created by a concurrent worker")
        return
    banner = "=" * 72
    logger.warning(
        "\n%s\n"
        " Mailserver UI — initial admin account created (first launch)\n"
        "   username : %s\n"
        "   password : %s\n"
        " This password is shown only once. Store it now.\n"
        "%s",
        banner,
        settings.admin_username,
        password,
        banner,
    )


# ── Internal helpers ─────────────────────────────────────────────────────────


def _now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


async def _touch_login(session: AsyncSession, user: User) -> None:
    """Record the user's last successful login time."""
    user.last_login_at = _now()
    session.add(user)
    await session.commit()
