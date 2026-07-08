"""Authentication endpoints: local login, session, and OIDC code flow."""

import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from app import oidc
from app.auth import (
    SessionUser,
    authenticate_local,
    create_session_token,
    require_user,
)
from app.config import settings

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
    """Public auth capabilities, consumed by the login page."""

    local_enabled: bool
    oidc_enabled: bool


# ── Cookie helpers ───────────────────────────────────────────────────────────


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: Response, name: str) -> None:
    response.delete_cookie(key=name, path="/")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/config", response_model=AuthConfig)
async def auth_config() -> AuthConfig:
    """Report which login methods are available to the frontend."""
    return AuthConfig(
        local_enabled=not settings.oidc_only,
        oidc_enabled=settings.oidc_enabled,
    )


@router.post("/login", response_model=SessionUser)
async def login(payload: LoginRequest, response: Response) -> SessionUser:
    """Authenticate local admin credentials and start a session."""
    if settings.oidc_only:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local login is disabled",
        )
    user = authenticate_local(payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    _set_session_cookie(response, create_session_token(user))
    logger.info("Local login succeeded for %s", user.username)
    return user


@router.get("/me", response_model=SessionUser)
async def me(user: SessionUser = Depends(require_user)) -> SessionUser:
    """Return the current authenticated user."""
    return user


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    """Clear the session cookie."""
    _clear_cookie(response, settings.auth_cookie_name)
    return {"detail": "Logged out"}


# ── OIDC authorization-code flow ─────────────────────────────────────────────


def _encode_state(state: str, nonce: str) -> str:
    payload = {
        "state": state,
        "nonce": nonce,
        "exp": int(time.time()) + _OIDC_STATE_TTL_S,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_STATE_ALGORITHM)


def _decode_state(token: str) -> dict[str, str] | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_STATE_ALGORITHM])
    except JWTError:
        return None


@router.get("/oidc/login")
async def oidc_login() -> RedirectResponse:
    """Start the OIDC flow: stash state/nonce in a cookie and redirect."""
    if not settings.oidc_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OIDC disabled"
        )

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    try:
        url = await oidc.authorization_url(state, nonce)
    except oidc.OIDCError as exc:
        logger.error("OIDC authorization URL build failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OIDC provider unavailable",
        ) from exc

    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=_OIDC_STATE_COOKIE,
        value=_encode_state(state, nonce),
        max_age=_OIDC_STATE_TTL_S,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle the provider redirect: verify state, exchange code, start session."""
    if not settings.oidc_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OIDC disabled"
        )

    if error or not code or not state:
        logger.warning("OIDC callback error=%s code=%s", error, bool(code))
        return RedirectResponse("/login?error=oidc", status_code=status.HTTP_302_FOUND)

    stored = _decode_state(request.cookies.get(_OIDC_STATE_COOKIE, ""))
    if not stored or not secrets.compare_digest(stored.get("state", ""), state):
        logger.warning("OIDC state mismatch")
        return RedirectResponse("/login?error=state", status_code=status.HTTP_302_FOUND)

    try:
        tokens = await oidc.exchange_code(code)
        claims = await oidc.fetch_userinfo(tokens["access_token"])
    except (oidc.OIDCError, KeyError) as exc:
        logger.error("OIDC token/userinfo failure: %s", exc)
        return RedirectResponse("/login?error=oidc", status_code=status.HTTP_302_FOUND)

    user = oidc.map_claims_to_user(claims)
    if user is None:
        return RedirectResponse(
            "/login?error=forbidden", status_code=status.HTTP_302_FOUND
        )

    response = RedirectResponse("/welcome", status_code=status.HTTP_302_FOUND)
    _set_session_cookie(response, create_session_token(user))
    _clear_cookie(response, _OIDC_STATE_COOKIE)
    logger.info("OIDC login succeeded for %s", user.username)
    return response
