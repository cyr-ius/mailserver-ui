"""Authentication core: password hashing and session JWTs.

The session is a signed JWT stored in an HttpOnly cookie (``auth_cookie_name``).
It carries the authenticated subject, display name and role, and is issued
after either a successful local login or a completed OIDC authorization code
flow. No server-side session store is required.

The FastAPI dependencies that consume these primitives (current-user
enforcement, database session) live in :mod:`app.depends`.
"""

import logging
import time
from typing import Literal

import bcrypt
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
    token: str = jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)
    return token


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
