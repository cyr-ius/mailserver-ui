"""Resolve the real client IP, honouring a configured trusted-proxy chain."""

import ipaddress
import logging

from fastapi import Request

from .config import settings

logger = logging.getLogger(__name__)

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def _parse_trusted_proxies(raw: str) -> list[IPNetwork]:
    """Parse the comma-separated ``trusted_proxies`` setting into networks."""
    networks: list[IPNetwork] = []
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid trusted proxy entry: %s", item)
    return networks


def _peer_is_trusted(request: Request, trusted: list[IPNetwork]) -> bool:
    """Return True when the direct peer is one of the configured trusted proxies."""
    peer = request.client.host if request.client else None
    if peer is None:
        return False
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in net for net in trusted)


def is_secure_request(request: Request) -> bool:
    """Return True when the original request reached us over HTTPS.

    The ``X-Forwarded-Proto`` header is honoured only when the direct peer is a
    configured trusted proxy, mirroring :func:`get_client_ip`; otherwise the
    header is ignored to prevent spoofing and the ASGI scheme is used.
    """
    trusted = _parse_trusted_proxies(settings.trusted_proxies)
    if trusted and _peer_is_trusted(request, trusted):
        forwarded = request.headers.get("x-forwarded-proto", "")
        proto = forwarded.split(",")[0].strip().lower()
        if proto:
            return proto == "https"
    return request.url.scheme == "https"


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
