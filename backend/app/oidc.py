"""OpenID Connect authorization-code flow helpers.

Discovery metadata is fetched from the issuer's ``.well-known`` document and
cached for the process lifetime. The flow is stateless on the server: the
``state``/``nonce`` pair is carried in a short-lived signed cookie and verified
on callback (see the auth router).
"""

import logging
import time
from typing import Any

import httpx

from app.auth import SessionUser
from app.config import DEFAULT_TIMEOUT, settings

logger = logging.getLogger(__name__)


class OIDCError(Exception):
    """Raised when the OIDC provider returns an error or invalid data."""


_discovery_cache: dict[str, Any] = {}
_discovery_fetched_at: float = 0.0
_DISCOVERY_TTL_S = 3600.0


async def _discover() -> dict[str, Any]:
    """Return the issuer's OpenID configuration, cached for an hour."""
    global _discovery_cache, _discovery_fetched_at
    now = time.monotonic()
    if _discovery_cache and now - _discovery_fetched_at < _DISCOVERY_TTL_S:
        return _discovery_cache

    url = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(url)
    if resp.status_code != httpx.codes.OK:
        raise OIDCError(f"Discovery failed: HTTP {resp.status_code}")
    _discovery_cache = resp.json()
    _discovery_fetched_at = now
    return _discovery_cache


async def authorization_url(state: str, nonce: str) -> str:
    """Build the provider authorization URL to redirect the browser to."""
    meta = await _discover()
    endpoint = meta["authorization_endpoint"]
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": settings.oidc_response_type,
        "scope": settings.oidc_scope,
        "redirect_uri": settings.oidc_redirect_uri,
        "state": state,
        "nonce": nonce,
    }
    query = httpx.QueryParams(params)
    return f"{endpoint}?{query}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Exchange an authorization code for the token response."""
    meta = await _discover()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oidc_redirect_uri,
        "client_id": settings.oidc_client_id,
        "client_secret": settings.oidc_client_secret,
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(meta["token_endpoint"], data=data)
    if resp.status_code != httpx.codes.OK:
        logger.warning("OIDC token exchange failed: HTTP %s", resp.status_code)
        raise OIDCError("Token exchange failed")
    return resp.json()


async def fetch_userinfo(access_token: str) -> dict[str, Any]:
    """Fetch the userinfo claims using the access token."""
    meta = await _discover()
    endpoint = meta.get("userinfo_endpoint")
    if not endpoint:
        raise OIDCError("Provider exposes no userinfo endpoint")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            endpoint, headers={"Authorization": f"Bearer {access_token}"}
        )
    if resp.status_code != httpx.codes.OK:
        raise OIDCError("Userinfo request failed")
    return resp.json()


def _claim_groups(claims: dict[str, Any], claim_name: str) -> list[str]:
    """Return the group values for ``claim_name`` as a list of strings."""
    raw = claims.get(claim_name)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def map_claims_to_user(claims: dict[str, Any]) -> SessionUser | None:
    """Map OIDC claims to a SessionUser, applying group-based restrictions.

    Returns ``None`` when group restrictions are enabled and the user is in
    neither the admin nor the user group (access denied).
    """
    username = (
        claims.get("preferred_username") or claims.get("email") or claims.get("sub", "")
    )
    display_name = claims.get("name") or username

    role: str = "user"
    is_admin = False
    is_user = True

    if settings.oidc_admin_group_claim and settings.oidc_admin_group:
        groups = _claim_groups(claims, settings.oidc_admin_group_claim)
        is_admin = settings.oidc_admin_group in groups

    if settings.oidc_user_group_claim and settings.oidc_user_group:
        groups = _claim_groups(claims, settings.oidc_user_group_claim)
        is_user = settings.oidc_user_group in groups

    role = "admin" if is_admin else "user"

    if settings.oidc_restrict_to_groups and not (is_admin or is_user):
        logger.info("OIDC user %s denied: not in any authorized group", username)
        return None

    return SessionUser(
        username=str(username),
        display_name=str(display_name),
        role=role,  # type: ignore[arg-type]
        provider="oidc",
    )
