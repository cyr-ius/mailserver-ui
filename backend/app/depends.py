"""FastAPI dependencies: database session and current-user enforcement.

Centralises everything injected via ``Depends()`` so routers stay declarative
and the authentication rules live in one place.

A request authenticates either with the session cookie issued by the login flow,
or with a personal access token presented as ``Authorization: Bearer``. Both
resolve to the same :class:`~app.auth.SessionUser` principal, so every route
enforces roles identically whichever credential was used.
"""

import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from .auth import SessionUser, decode_session_token, role_grants
from .config import settings
from .database import engine
from .exceptions import ForbiddenException, UnauthorizedException
from .services import pat_service, user_service

logger = logging.getLogger(__name__)

#: Declared so Swagger's *Authorize* dialog offers a personal access token. It
#: does not error on its own, because a request may authenticate with the
#: session cookie instead.
_pat_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="PersonalAccessToken",
    description="A personal access token (pat_…) issued from the profile page.",
)


def get_session() -> Generator[Session]:
    """Yield a database session scoped to the current request."""
    with Session(engine) as session:
        yield session


def current_user_optional(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    bearer: Annotated[
        HTTPAuthorizationCredentials | None, Security(_pat_bearer)
    ] = None,
) -> SessionUser | None:
    """Return the authenticated principal, from the session cookie or a PAT.

    The cookie wins when both are present: a browser session is the more
    specific credential, and re-resolving the token would cost a query for
    nothing.

    A cookie is not trusted on its own: the account behind it is re-read on every
    request, so a session held by an account that has since been deactivated (or
    deleted) stops working immediately instead of surviving until the JWT expires.
    """
    token = request.cookies.get(settings.auth_cookie_name)
    if token:
        user = decode_session_token(token)
        if user is not None:
            account = user_service.get_by_username(session, user.username)
            if account is not None and account.is_active:
                return user_service.to_session_user(session, account)
            logger.info(
                "Rejected session of unknown or deactivated account %s", user.username
            )
            return None

    if not settings.pats_enabled or bearer is None:
        return None
    # Only a credential that looks like a PAT is resolved, so a session JWT sent
    # as a bearer token is never mistaken for one.
    if not bearer.credentials.startswith(pat_service.TOKEN_PREFIX):
        return None
    account = pat_service.authenticate(session, bearer.credentials)
    if account is None or not account.is_active:
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
    """Dependency enforcing an interactive session, rejecting PAT callers.

    Guards the endpoints that manage tokens themselves: a stolen token must not
    be enough to mint further ones, nor to revoke the ones its owner relies on.
    """
    user = decode_session_token(request.cookies.get(settings.auth_cookie_name, ""))
    if user is None:
        raise ForbiddenException(
            "This operation requires an interactive session, not a personal access token"
        )
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
