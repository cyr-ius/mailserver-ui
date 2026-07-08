"""User service: persistence-backed authentication and account management.

Encapsulates all database access for users so routers and the auth layer stay
free of query logic. Local users authenticate against a stored bcrypt hash;
OIDC users are provisioned/refreshed on each successful sign-in.
"""

import logging
import secrets
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.auth import SessionUser, hash_password, verify_password
from app.config import settings
from app.user_models import User

logger = logging.getLogger(__name__)

# Length (in bytes) of the randomly generated default admin password.
_GENERATED_PASSWORD_BYTES = 24


def to_session_user(user: User) -> SessionUser:
    """Map a persisted user to the session principal carried by the cookie."""
    return SessionUser(
        username=user.username,
        display_name=user.display_name or user.username,
        role="admin" if user.role == "admin" else "user",
        provider="oidc" if user.provider == "oidc" else "local",
    )


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
    """Validate local credentials against the stored hash."""
    user = get_by_username(session, username)
    if user is None or user.provider != "local" or not user.password_hash:
        # Run a dummy hash comparison to keep timing roughly uniform.
        verify_password(password, "$2b$12$" + "." * 53)
        return None
    if not verify_password(password, user.password_hash):
        return None
    _touch_login(session, user)
    return to_session_user(user)


def upsert_oidc_user(session: Session, principal: SessionUser) -> User:
    """Create or refresh the local record mirroring an OIDC principal."""
    user = get_by_username(session, principal.username)
    if user is None:
        user = User(
            username=principal.username,
            display_name=principal.display_name,
            role=principal.role,
            provider="oidc",
            password_hash=None,
        )
    else:
        user.display_name = principal.display_name
        user.role = principal.role
        user.provider = "oidc"
    user.last_login_at = _now()
    user.updated_at = _now()
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ── Mutations ────────────────────────────────────────────────────────────────


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
