"""FastAPI dependencies: database session and current-user enforcement.

Centralises everything injected via ``Depends()`` so routers stay declarative
and the authentication rules live in one place.

A request authenticates either with the session cookie issued by the login flow,
or with a personal API key presented in the ``X-API-Key`` header (or as a bearer
token). Both resolve to the same :class:`~app.auth.SessionUser` principal, so
every route enforces roles identically whichever credential was used.
"""

import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader
from sqlmodel import Session

from .auth import SessionUser, decode_session_token, role_grants
from .config import settings
from .database import engine
from .exceptions import ForbiddenException, UnauthorizedException
from .services import api_key_service, user_service

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name=settings.api_key_header, auto_error=False)


def get_session() -> Generator[Session]:
    """Yield a database session scoped to the current request."""
    with Session(engine) as session:
        yield session


def _presented_api_key(request: Request, header_key: str | None) -> str | None:
    """Return the API key carried by the request, from either accepted location.

    The bearer form is only considered when the token looks like an API key, so
    a session JWT sent as a bearer token is never mistaken for one.
    """
    if header_key:
        return header_key
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token.startswith(api_key_service.KEY_PREFIX):
        return token
    return None


def current_user_optional(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    header_key: Annotated[str | None, Security(_api_key_header)] = None,
) -> SessionUser | None:
    """Return the authenticated principal, from the session cookie or an API key.

    The cookie wins when both are present: a browser session is the more
    specific credential, and re-resolving the key would cost a query for nothing.
    """
    token = request.cookies.get(settings.auth_cookie_name)
    if token:
        user = decode_session_token(token)
        if user is not None:
            return user

    if not settings.api_keys_enabled:
        return None
    raw_key = _presented_api_key(request, header_key)
    if not raw_key:
        return None
    account = api_key_service.authenticate(session, raw_key)
    if account is None:
        return None
    return user_service.to_session_user(session, account)


def require_user(
    user: Annotated[SessionUser | None, Depends(current_user_optional)],
) -> SessionUser:
    """Dependency enforcing an authenticated session."""
    if user is None:
        raise UnauthorizedException()
    return user


def require_session_login(
    request: Request,
    _user: Annotated[SessionUser, Depends(require_user)],
) -> SessionUser:
    """Dependency enforcing an interactive session, rejecting API-key callers.

    Guards the endpoints that manage API keys themselves: a stolen key must not
    be enough to mint further keys, nor to revoke the ones its owner relies on.
    """
    user = decode_session_token(request.cookies.get(settings.auth_cookie_name, ""))
    if user is None:
        raise ForbiddenException("This operation requires an interactive session, not an API key")
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
