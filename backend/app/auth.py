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
from collections.abc import Iterable
from typing import Literal, get_args

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
# bcrypt only considers the first 72 bytes of a password; longer inputs raise in
# bcrypt >= 5, so truncate defensively on both hash and verify.
_BCRYPT_MAX_BYTES = 72

Role = Literal["guest", "mailbox_manager", "admin"]
AuthProvider = Literal["local", "oidc"]

#: Roles ordered from least to most privileged; a role implies every role before it.
ROLE_PRECEDENCE: tuple[Role, ...] = get_args(Role)

#: Role stored by releases that only knew ``admin``/``user``. The old ``user``
#: role granted nothing beyond the dashboard, which is exactly ``guest`` today —
#: mapping it to ``mailbox_manager`` would silently widen existing accounts.
_LEGACY_ROLES: dict[str, Role] = {"user": "guest"}


def normalize_role(value: str) -> Role:
    """Coerce a stored role string into a known role, defaulting to ``guest``."""
    role = _LEGACY_ROLES.get(value, value)
    return role if role in ROLE_PRECEDENCE else "guest"  # type: ignore[return-value]


def highest_role(roles: Iterable[str]) -> Role:
    """Return the most privileged of ``roles``, or ``guest`` when empty."""
    return max(
        (normalize_role(role) for role in roles),
        key=ROLE_PRECEDENCE.index,
        default="guest",
    )


def role_grants(role: Role, required: Role) -> bool:
    """Return True when ``role`` is at least as privileged as ``required``."""
    return ROLE_PRECEDENCE.index(role) >= ROLE_PRECEDENCE.index(required)


class SessionUser(BaseModel):
    """The authenticated principal carried by the session cookie.

    ``role`` is the *effective* role: the most privileged of the role stored on
    the account and the roles granted by its local group memberships.
    """

    username: str
    display_name: str
    role: Role
    provider: AuthProvider


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
        "exp": now + settings.access_token_expire_minutes * 60,
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
            role=normalize_role(payload.get("role", "")),
            provider=payload.get("provider", "local"),
        )
    except KeyError, ValueError:
        return None
