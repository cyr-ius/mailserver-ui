"""Authentication endpoints: local login, session, and OIDC code flow."""

import logging
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..auth import SessionUser, create_session_token
from ..client_ip import is_secure_request
from ..config import settings
from ..depends import get_session, require_user
from ..exceptions import (
    BadGatewayException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from ..services import audit_service, oidc, settings_service, user_service

SessionDep = Annotated[Session, Depends(get_session)]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_OIDC_STATE_COOKIE = "pc_oidc_state"
_OIDC_STATE_TTL_S = 600
_STATE_ALGORITHM = "HS256"


# ── Schemas ──────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class AuthConfig(BaseModel):
    """Public auth capabilities, consumed by the login page and the profile page."""

    local_enabled: bool
    oidc_enabled: bool
    # When false, the profile page hides the personal API key section entirely:
    # the backend rejects keys, so offering to mint one would be a dead end.
    api_keys_enabled: bool


# ── Cookie helpers ───────────────────────────────────────────────────────────


def _set_session_cookie(response: Response, token: str, *, secure: bool) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(key=name, path="/")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/config", response_model=AuthConfig)
async def auth_config(session: SessionDep) -> AuthConfig:
    """Report which login methods are available to the frontend."""
    cfg = settings_service.get_oidc_settings(session)
    return AuthConfig(
        local_enabled=not cfg.oidc_only,
        oidc_enabled=cfg.enabled,
        api_keys_enabled=settings.api_keys_enabled,
    )


@router.post("/login", response_model=SessionUser)
async def login(
    payload: LoginRequest, request: Request, response: Response, session: SessionDep
) -> SessionUser:
    """Authenticate local credentials against the database and start a session."""
    if settings_service.get_oidc_settings(session).oidc_only:
        raise ForbiddenException("Local login is disabled")

    user = user_service.authenticate_local(session, payload.username, payload.password)
    if user is None:
        # The audit trail names the account that was attempted — a burst of
        # failures against one username is exactly what it exists to surface.
        await audit_service.record(
            session,
            request=request,
            category="auth",
            action="auth.login",
            actor=payload.username,
            target=payload.username,
            status="failure",
            detail="Invalid credentials, or the account is deactivated",
        )
        raise UnauthorizedException("Invalid username or password")

    _set_session_cookie(response, create_session_token(user), secure=is_secure_request(request))
    logger.info("Local login succeeded for %s", user.username)
    await audit_service.record(
        session,
        request=request,
        category="auth",
        action="auth.login",
        actor=user.username,
        target=user.username,
        detail="provider=local",
    )
    return user


@router.get("/me", response_model=SessionUser)
async def me(user: Annotated[SessionUser, Depends(require_user)]) -> SessionUser:
    """Return the current authenticated user."""
    return user


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    user: Annotated[SessionUser, Depends(require_user)],
) -> dict[str, str]:
    """Clear the session cookie."""
    _clear_cookie(response, settings.auth_cookie_name)
    await audit_service.record(
        session,
        request=request,
        category="auth",
        action="auth.logout",
        actor=user.username,
        target=user.username,
        detail=f"provider={user.provider}",
    )
    return {"detail": "Logged out"}


# ── OIDC authorization-code flow ─────────────────────────────────────────────


def _encode_state(state: str, nonce: str) -> str:
    payload = {
        "state": state,
        "nonce": nonce,
        "exp": int(time.time()) + _OIDC_STATE_TTL_S,
    }
    token: str = jwt.encode(payload, settings.secret_key, algorithm=_STATE_ALGORITHM)
    return token


def _decode_state(token: str) -> dict[str, str] | None:
    try:
        payload: dict[str, str] = jwt.decode(
            token, settings.secret_key, algorithms=[_STATE_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


@router.get("/oidc/login")
async def oidc_login(request: Request, session: SessionDep) -> RedirectResponse:
    """Start the OIDC flow: stash state/nonce in a cookie and redirect."""
    cfg = settings_service.get_oidc_settings(session)
    if not cfg.enabled:
        raise NotFoundException("OIDC endpoint", "login")

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    try:
        url = await oidc.authorization_url(cfg, state, nonce)
    except oidc.OIDCError as exc:
        logger.error("OIDC authorization URL build failed: %s", exc)
        raise BadGatewayException("OIDC provider unavailable") from exc

    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=_OIDC_STATE_COOKIE,
        value=_encode_state(state, nonce),
        max_age=_OIDC_STATE_TTL_S,
        httponly=True,
        secure=is_secure_request(request),
        samesite="lax",
        path="/",
    )
    return response


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    session: SessionDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle the provider redirect: verify state, exchange code, start session."""
    cfg = settings_service.get_oidc_settings(session)
    if not cfg.enabled:
        raise NotFoundException("OIDC endpoint", "callback")

    if error or not code or not state:
        logger.warning("OIDC callback error=%s code=%s", error, bool(code))
        return RedirectResponse("/login?error=oidc", status_code=status.HTTP_302_FOUND)

    stored = _decode_state(request.cookies.get(_OIDC_STATE_COOKIE, ""))
    if not stored or not secrets.compare_digest(stored.get("state", ""), state):
        logger.warning("OIDC state mismatch")
        return RedirectResponse("/login?error=state", status_code=status.HTTP_302_FOUND)

    try:
        tokens = await oidc.exchange_code(cfg, code)
        claims = await oidc.fetch_userinfo(cfg, tokens["access_token"])
    except (oidc.OIDCError, KeyError) as exc:
        logger.error("OIDC token/userinfo failure: %s", exc)
        return RedirectResponse("/login?error=oidc", status_code=status.HTTP_302_FOUND)

    principal = oidc.map_claims_to_user(cfg, claims)
    if principal is None:
        return RedirectResponse("/login?error=forbidden", status_code=status.HTTP_302_FOUND)

    # Persist/refresh the OIDC account so it appears in the users list, and pick
    # up any role granted by the local groups it belongs to. Refuses to take over
    # a local account of the same name, and to sign in a deactivated one.
    try:
        user = user_service.upsert_oidc_user(session, principal)
    except (ConflictException, ForbiddenException) as exc:
        logger.warning("OIDC login refused for %s: %s", principal.username, exc.detail)
        await audit_service.record(
            session,
            request=request,
            category="auth",
            action="auth.login",
            actor=principal.username,
            target=principal.username,
            status="failure",
            detail=f"OIDC sign-in refused: {exc.detail}",
        )
        reason = "conflict" if isinstance(exc, ConflictException) else "disabled"
        return RedirectResponse(f"/login?error={reason}", status_code=status.HTTP_302_FOUND)

    response = RedirectResponse("/welcome", status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, create_session_token(user), secure=is_secure_request(request))
    _clear_cookie(response, _OIDC_STATE_COOKIE)
    logger.info("OIDC login succeeded for %s", user.username)
    await audit_service.record(
        session,
        request=request,
        category="auth",
        action="auth.login",
        actor=user.username,
        target=user.username,
        detail="provider=oidc",
    )
    return response
