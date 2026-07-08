"""OpenID Connect authorization-code flow helpers.

The configuration is passed in from the caller (loaded from the database via
:mod:`app.services.settings_service`). Discovery metadata is fetched from the
issuer's ``.well-known`` document and cached per issuer for an hour; the cache is
reset explicitly when the issuer changes. The flow is stateless on the server:
the ``state``/``nonce`` pair is carried in a short-lived signed cookie and
verified on callback (see the auth router).
"""

import logging
import time
from typing import Any

import httpx

from app.auth import SessionUser
from app.config import DEFAULT_TIMEOUT
from app.settings_models import OidcSettings

logger = logging.getLogger(__name__)


class OIDCError(Exception):
    """Raised when the OIDC provider returns an error or invalid data."""


# Discovery documents keyed by issuer URL, with the fetch timestamp.
_discovery_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_DISCOVERY_TTL_S = 3600.0


def reset_discovery_cache() -> None:
    """Drop cached discovery documents (call when the issuer changes)."""
    _discovery_cache.clear()


async def _discover(config: OidcSettings) -> dict[str, Any]:
    """Return the issuer's OpenID configuration, cached per issuer for an hour."""
    issuer = config.issuer.rstrip("/")
    now = time.monotonic()
    cached = _discovery_cache.get(issuer)
    if cached and now - cached[0] < _DISCOVERY_TTL_S:
        return cached[1]

    url = issuer + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(url)
    if resp.status_code != httpx.codes.OK:
        raise OIDCError(f"Discovery failed: HTTP {resp.status_code}")
    document: dict[str, Any] = resp.json()
    _discovery_cache[issuer] = (now, document)
    return document


async def authorization_url(config: OidcSettings, state: str, nonce: str) -> str:
    """Build the provider authorization URL to redirect the browser to."""
    meta = await _discover(config)
    endpoint = meta["authorization_endpoint"]
    params = {
        "client_id": config.client_id,
        "response_type": config.response_type,
        "scope": config.scope,
        "redirect_uri": config.redirect_uri,
        "state": state,
        "nonce": nonce,
    }
    query = httpx.QueryParams(params)
    return f"{endpoint}?{query}"


async def exchange_code(config: OidcSettings, code: str) -> dict[str, Any]:
    """Exchange an authorization code for the token response."""
    meta = await _discover(config)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.post(meta["token_endpoint"], data=data)
    if resp.status_code != httpx.codes.OK:
        logger.warning("OIDC token exchange failed: HTTP %s", resp.status_code)
        raise OIDCError("Token exchange failed")
    tokens: dict[str, Any] = resp.json()
    return tokens


async def fetch_userinfo(config: OidcSettings, access_token: str) -> dict[str, Any]:
    """Fetch the userinfo claims using the access token."""
    meta = await _discover(config)
    endpoint = meta.get("userinfo_endpoint")
    if not endpoint:
        raise OIDCError("Provider exposes no userinfo endpoint")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(endpoint, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code != httpx.codes.OK:
        raise OIDCError("Userinfo request failed")
    claims: dict[str, Any] = resp.json()
    return claims


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


def map_claims_to_user(config: OidcSettings, claims: dict[str, Any]) -> SessionUser | None:
    """Map OIDC claims to a SessionUser, applying group-based restrictions.

    Returns ``None`` when group restrictions are enabled and the user is in
    neither the admin nor the user group (access denied).
    """
    username = claims.get("preferred_username") or claims.get("email") or claims.get("sub", "")
    display_name = claims.get("name") or username

    is_admin = False
    is_user = True

    if config.admin_group_claim and config.admin_group:
        groups = _claim_groups(claims, config.admin_group_claim)
        is_admin = config.admin_group in groups

    if config.user_group_claim and config.user_group:
        groups = _claim_groups(claims, config.user_group_claim)
        is_user = config.user_group in groups

    role = "admin" if is_admin else "user"

    if config.restrict_to_groups and not (is_admin or is_user):
        logger.info("OIDC user %s denied: not in any authorized group", username)
        return None

    return SessionUser(
        username=str(username),
        display_name=str(display_name),
        role=role,  # type: ignore[arg-type]
        provider="oidc",
    )
