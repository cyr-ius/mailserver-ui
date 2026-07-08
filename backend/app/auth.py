"""Authentication core: password hashing, session JWTs, current-user dependency.

The session is a signed JWT stored in an HttpOnly cookie (``auth_cookie_name``).
It carries the authenticated subject, display name and role, and is issued
after either a successful local login or a completed OIDC authorization code
flow. No server-side session store is required.
"""

import logging
import time
from typing import Literal

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
# bcrypt only considers the first 72 bytes of a password; longer inputs raise in
# bcrypt >= 5, so truncate defensively on both hash and verify.
_BCRYPT_MAX_BYTES = 72

Role = Literal["admin", "user"]


class SessionUser(BaseModel):
    """The authenticated principal carried by the session cookie."""

    username: str
    display_name: str
    role: Role
    provider: Literal["local", "oidc"]


# ── Password hashing ─────────────────────────────────────────────────────────


def _to_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def verify_password(plain: str, hashed: str) -> bool:
    """Return True when ``plain`` matches the bcrypt ``hashed`` value."""
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except ValueError, TypeError:
        return False


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def _admin_password_hash() -> str:
    """Resolve the admin password hash from settings.

    Prefers a precomputed ``admin_password_hash``; otherwise hashes the
    plaintext ``admin_password`` on demand.
    """
    if settings.admin_password_hash:
        return settings.admin_password_hash
    return hash_password(settings.admin_password)


def authenticate_local(username: str, password: str) -> SessionUser | None:
    """Validate local admin credentials, returning the user on success."""
    if username != settings.admin_username:
        # Still run a hash comparison to keep timing roughly uniform.
        verify_password(password, _admin_password_hash())
        return None
    if not verify_password(password, _admin_password_hash()):
        return None
    return SessionUser(
        username=username,
        display_name=username,
        role="admin",
        provider="local",
    )


# ── Session tokens ───────────────────────────────────────────────────────────


def create_session_token(user: SessionUser) -> str:
    """Issue a signed session JWT for ``user``."""
    now = int(time.time())
    payload = {
        "sub": user.username,
        "name": user.display_name,
        "role": user.role,
        "provider": user.provider,
        "iat": now,
        "exp": now + settings.auth_token_ttl_seconds,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_session_token(token: str) -> SessionUser | None:
    """Decode and validate a session JWT, returning the user or None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except JWTError:
        return None
    try:
        return SessionUser(
            username=payload["sub"],
            display_name=payload.get("name", payload["sub"]),
            role=payload.get("role", "user"),
            provider=payload.get("provider", "local"),
        )
    except KeyError, ValueError:
        return None


# ── FastAPI dependencies ─────────────────────────────────────────────────────


def current_user_optional(request: Request) -> SessionUser | None:
    """Return the session user if a valid auth cookie is present, else None."""
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    return decode_session_token(token)


def require_user(
    user: SessionUser | None = Depends(current_user_optional),
) -> SessionUser:
    """Dependency enforcing an authenticated session."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user
