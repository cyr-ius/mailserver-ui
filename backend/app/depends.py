"""FastAPI dependencies: database session and current-user enforcement.

Centralises everything injected via ``Depends()`` so routers stay declarative
and the authentication rules live in one place.
"""

import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from .auth import SessionUser, decode_session_token, role_grants
from .config import settings
from .database import engine
from .exceptions import ForbiddenException, UnauthorizedException

logger = logging.getLogger(__name__)


def get_session() -> Generator[Session]:
    """Yield a database session scoped to the current request."""
    with Session(engine) as session:
        yield session


def current_user_optional(request: Request) -> SessionUser | None:
    """Return the session user if a valid auth cookie is present, else None."""
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        return None
    return decode_session_token(token)


def require_user(
    user: Annotated[SessionUser | None, Depends(current_user_optional)],
) -> SessionUser:
    """Dependency enforcing an authenticated session."""
    if user is None:
        raise UnauthorizedException()
    return user


def require_mailbox_manager(
    user: Annotated[SessionUser, Depends(require_user)],
) -> SessionUser:
    """Dependency enforcing mailbox-management privileges (managers and admins)."""
    if not role_grants(user.role, "mailbox_manager"):
        raise ForbiddenException("Mailbox manager privileges required")
    return user


def require_admin(
    user: Annotated[SessionUser, Depends(require_user)],
) -> SessionUser:
    """Dependency enforcing an authenticated session with the admin role."""
    if not role_grants(user.role, "admin"):
        raise ForbiddenException("Administrator privileges required")
    return user
