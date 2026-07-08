"""Resolve the real client IP, honouring a configured trusted-proxy chain."""

import ipaddress
import logging

from fastapi import Request

from app.config import settings

logger = logging.getLogger(__name__)


def _parse_trusted_proxies(raw: str) -> list[ipaddress._BaseNetwork]:
    """Parse the comma-separated ``trusted_proxies`` setting into networks."""
    networks: list[ipaddress._BaseNetwork] = []
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid trusted proxy entry: %s", item)
    return networks


def get_client_ip(request: Request) -> str | None:
    """Return the originating client IP.

    When no trusted proxies are configured the peer address is returned as-is.
    Otherwise the rightmost ``X-Forwarded-For`` entry that is *not* a trusted
    proxy is treated as the real client, preventing header spoofing from
    untrusted callers.
    """
    peer = request.client.host if request.client else None
    trusted = _parse_trusted_proxies(settings.trusted_proxies)
    if not trusted:
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
    # Walk the chain from the closest hop backwards, skipping trusted proxies.
    for candidate in reversed(chain):
        try:
            addr = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if not any(addr in net for net in trusted):
            return candidate
    return peer
