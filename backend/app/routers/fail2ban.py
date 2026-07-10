"""Fail2ban management endpoints (admin only).

Exposes docker-mailserver's fail2ban: jail status, currently banned IPs,
manual ban/unban and the fail2ban log. Every operation runs a ``docker exec``
against the mailserver container, so the calls are offloaded to a threadpool to
avoid blocking the event loop. See :mod:`app.services.fail2ban_service`.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ..auth import SessionUser
from ..depends import require_admin
from ..models.fail2ban_models import (
    BannedIp,
    BanRequest,
    Fail2banActionResult,
    Fail2banConfig,
    Fail2banConfigUpdate,
    Fail2banLog,
    Fail2banPolicy,
    Fail2banPolicyUpdate,
    Fail2banStatus,
)
from ..services import fail2ban_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fail2ban", tags=["fail2ban"])

AdminDep = Annotated[SessionUser, Depends(require_admin)]


@router.get("/status", response_model=Fail2banStatus)
async def get_status(_admin: AdminDep) -> Fail2banStatus:
    """Return the status of every fail2ban jail, banned IPs included (admin only)."""
    return await run_in_threadpool(fail2ban_service.get_status)


@router.get("/banned", response_model=list[BannedIp])
async def list_banned(_admin: AdminDep) -> list[BannedIp]:
    """List every currently banned IP with its jail (admin only)."""
    return await run_in_threadpool(fail2ban_service.list_banned_ips)


@router.post("/ban", response_model=Fail2banActionResult)
async def ban_ip(payload: BanRequest, _admin: AdminDep) -> Fail2banActionResult:
    """Ban an IP address across the mailserver's active jails (admin only)."""
    return await run_in_threadpool(fail2ban_service.ban_ip, payload.ip)


@router.delete("/banned/{ip}", response_model=Fail2banActionResult)
async def unban_ip(ip: str, _admin: AdminDep) -> Fail2banActionResult:
    """Remove any ban for an IP address across all jails (admin only)."""
    return await run_in_threadpool(fail2ban_service.unban_ip, ip)


@router.get("/log", response_model=Fail2banLog)
async def get_log(_admin: AdminDep) -> Fail2banLog:
    """Return the trailing lines of the fail2ban log file (admin only)."""
    return await run_in_threadpool(fail2ban_service.get_log)


@router.get("/policy", response_model=Fail2banPolicy)
async def get_policy(_admin: AdminDep) -> Fail2banPolicy:
    """Return the fail2ban ban policy: bantime, findtime, maxretry (admin only)."""
    return await run_in_threadpool(fail2ban_service.get_policy)


@router.put("/policy", response_model=Fail2banPolicy)
async def set_policy(payload: Fail2banPolicyUpdate, _admin: AdminDep) -> Fail2banPolicy:
    """Replace the fail2ban ban policy; takes effect on restart (admin only)."""
    return await run_in_threadpool(fail2ban_service.set_policy, payload)


@router.get("/config", response_model=Fail2banConfig)
async def get_config(_admin: AdminDep) -> Fail2banConfig:
    """Return the raw ``fail2ban-fail2ban.cf`` daemon configuration (admin only)."""
    return await run_in_threadpool(fail2ban_service.get_config)


@router.put("/config", response_model=Fail2banConfig)
async def set_config(payload: Fail2banConfigUpdate, _admin: AdminDep) -> Fail2banConfig:
    """Replace the fail2ban daemon configuration; applies on restart (admin only)."""
    return await run_in_threadpool(fail2ban_service.set_config, payload.content)
