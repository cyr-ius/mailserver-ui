"""Mailserver configuration endpoints (admin only).

Exposes the parts of the docker-mailserver global configuration that live in the
shared config volume — SMTP relays, Postfix and Dovecot overrides, aliases,
global Sieve scripts, DKIM records — plus the read-only runtime views: the mail
queue, the TLS certificate, the DNS records to publish and the container's
effective environment.

Every call shells out to ``docker exec`` and blocks, so it is offloaded to a
threadpool. All operations require the admin role. See
:mod:`app.services.mailserver_service`.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.concurrency import run_in_threadpool

from ..auth import SessionUser
from ..depends import require_admin
from ..models.mailserver_models import (
    DkimGenerateRequest,
    DkimKey,
    DomainDnsRecords,
    DovecotConfig,
    DovecotConfigUpdate,
    DovecotMaster,
    DovecotMasterCreate,
    MailLog,
    MailserverEnvironment,
    MailStats,
    PostfixMasterOverride,
    PostfixMasterOverridesUpdate,
    PostfixOverride,
    PostfixOverridesUpdate,
    QueueActionResult,
    QueueSummary,
    RegexAlias,
    RegexAliasCreate,
    RelayExclusion,
    RelayExclusionCreate,
    RelayHost,
    RelayHostCreate,
    Restriction,
    RestrictionCreate,
    ServiceStatus,
    SieveScope,
    SieveScript,
    SieveScriptUpdate,
    SystemAlias,
    SystemAliasCreate,
    TlsCertificate,
)
from ..services import mailserver_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mailserver", tags=["mailserver"])

AdminDep = Annotated[SessionUser, Depends(require_admin)]


# ── SMTP relays ───────────────────────────────────────────────────────────────


@router.get("/relays", response_model=list[RelayHost])
async def list_relays(_admin: AdminDep) -> list[RelayHost]:
    """List the configured SMTP relays (admin only, passwords never returned)."""
    return await run_in_threadpool(mailserver_service.list_relays)


@router.post("/relays", response_model=RelayHost, status_code=status.HTTP_201_CREATED)
async def create_relay(payload: RelayHostCreate, _admin: AdminDep) -> RelayHost:
    """Add an SMTP relay for a sender domain (admin only)."""
    return await run_in_threadpool(mailserver_service.create_relay, payload)


@router.delete("/relays/{sender}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relay(sender: str, _admin: AdminDep) -> None:
    """Remove an SMTP relay and its stored credentials (admin only)."""
    await run_in_threadpool(mailserver_service.delete_relay, sender)


# ── Global relay exclusions ───────────────────────────────────────────────────


@router.get("/relay-exclusions", response_model=list[RelayExclusion])
async def list_relay_exclusions(_admin: AdminDep) -> list[RelayExclusion]:
    """List the sender domains opted out of the global relay (admin only)."""
    return await run_in_threadpool(mailserver_service.list_relay_exclusions)


@router.post(
    "/relay-exclusions", response_model=RelayExclusion, status_code=status.HTTP_201_CREATED
)
async def create_relay_exclusion(payload: RelayExclusionCreate, _admin: AdminDep) -> RelayExclusion:
    """Opt a sender domain out of the global relay host (admin only)."""
    return await run_in_threadpool(mailserver_service.create_relay_exclusion, payload.sender)


@router.delete("/relay-exclusions/{sender}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relay_exclusion(sender: str, _admin: AdminDep) -> None:
    """Send a sender domain's mail through the global relay again (admin only)."""
    await run_in_threadpool(mailserver_service.delete_relay_exclusion, sender)


# ── Postfix overrides ─────────────────────────────────────────────────────────


@router.get("/postfix", response_model=list[PostfixOverride])
async def get_postfix_overrides(_admin: AdminDep) -> list[PostfixOverride]:
    """Return the Postfix ``main.cf`` overrides (admin only)."""
    return await run_in_threadpool(mailserver_service.list_postfix_overrides)


@router.put("/postfix", response_model=list[PostfixOverride])
async def update_postfix_overrides(
    payload: PostfixOverridesUpdate,
    _admin: AdminDep,
) -> list[PostfixOverride]:
    """Replace the full set of Postfix ``main.cf`` overrides (admin only)."""
    return await run_in_threadpool(mailserver_service.set_postfix_overrides, payload.overrides)


@router.get("/postfix-master", response_model=list[PostfixMasterOverride])
async def get_postfix_master_overrides(_admin: AdminDep) -> list[PostfixMasterOverride]:
    """Return the Postfix ``master.cf`` service overrides (admin only)."""
    return await run_in_threadpool(mailserver_service.list_postfix_master_overrides)


@router.put("/postfix-master", response_model=list[PostfixMasterOverride])
async def update_postfix_master_overrides(
    payload: PostfixMasterOverridesUpdate,
    _admin: AdminDep,
) -> list[PostfixMasterOverride]:
    """Replace the full set of Postfix ``master.cf`` overrides (admin only)."""
    return await run_in_threadpool(
        mailserver_service.set_postfix_master_overrides, payload.overrides
    )


# ── Dovecot configuration override ────────────────────────────────────────────


@router.get("/dovecot-config", response_model=DovecotConfig)
async def get_dovecot_config(_admin: AdminDep) -> DovecotConfig:
    """Return the raw ``dovecot.cf`` override (admin only)."""
    return await run_in_threadpool(mailserver_service.get_dovecot_config)


@router.put("/dovecot-config", response_model=DovecotConfig)
async def update_dovecot_config(payload: DovecotConfigUpdate, _admin: AdminDep) -> DovecotConfig:
    """Replace the ``dovecot.cf`` override; takes effect on restart (admin only)."""
    return await run_in_threadpool(mailserver_service.set_dovecot_config, payload.content)


# ── System and regex aliases ──────────────────────────────────────────────────


@router.get("/system-aliases", response_model=list[SystemAlias])
async def list_system_aliases(_admin: AdminDep) -> list[SystemAlias]:
    """List the local aliases appended to ``/etc/aliases`` (admin only)."""
    return await run_in_threadpool(mailserver_service.list_system_aliases)


@router.post("/system-aliases", response_model=SystemAlias, status_code=status.HTTP_201_CREATED)
async def create_system_alias(payload: SystemAliasCreate, _admin: AdminDep) -> SystemAlias:
    """Add a local system alias such as ``root`` or ``abuse`` (admin only)."""
    return await run_in_threadpool(
        mailserver_service.create_system_alias, payload.name, payload.targets
    )


@router.delete("/system-aliases/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_alias(name: str, _admin: AdminDep) -> None:
    """Remove a local system alias (admin only)."""
    await run_in_threadpool(mailserver_service.delete_system_alias, name)


@router.get("/regex-aliases", response_model=list[RegexAlias])
async def list_regex_aliases(_admin: AdminDep) -> list[RegexAlias]:
    """List the PCRE aliases of ``postfix-regexp.cf`` (admin only)."""
    return await run_in_threadpool(mailserver_service.list_regex_aliases)


@router.post("/regex-aliases", response_model=RegexAlias, status_code=status.HTTP_201_CREATED)
async def create_regex_alias(payload: RegexAliasCreate, _admin: AdminDep) -> RegexAlias:
    """Add a PCRE alias matching addresses by regular expression (admin only)."""
    return await run_in_threadpool(
        mailserver_service.create_regex_alias, payload.pattern, payload.targets
    )


@router.delete("/regex-aliases", status_code=status.HTTP_204_NO_CONTENT)
async def delete_regex_alias(pattern: str, _admin: AdminDep) -> None:
    """Remove a PCRE alias (admin only).

    The pattern travels as a query parameter: it contains slashes, so it cannot
    be a path segment.
    """
    await run_in_threadpool(mailserver_service.delete_regex_alias, pattern)


# ── DKIM ──────────────────────────────────────────────────────────────────────


@router.get("/dkim", response_model=list[DkimKey])
async def list_dkim_keys(_admin: AdminDep) -> list[DkimKey]:
    """Return the generated DKIM public records to publish in DNS (admin only)."""
    return await run_in_threadpool(mailserver_service.list_dkim_keys)


@router.post("/dkim", response_model=list[DkimKey], status_code=status.HTTP_201_CREATED)
async def generate_dkim(payload: DkimGenerateRequest, _admin: AdminDep) -> list[DkimKey]:
    """Generate DKIM keys inside the mailserver container (admin only)."""
    return await run_in_threadpool(mailserver_service.generate_dkim, payload)


# ── Send/receive restrictions ─────────────────────────────────────────────────


@router.get("/restrictions/{kind}", response_model=list[Restriction])
async def list_restrictions(kind: str, _admin: AdminDep) -> list[Restriction]:
    """List the send or receive restrictions (admin only)."""
    return await run_in_threadpool(mailserver_service.list_restrictions, kind)


@router.post(
    "/restrictions/{kind}", response_model=Restriction, status_code=status.HTTP_201_CREATED
)
async def add_restriction(kind: str, payload: RestrictionCreate, _admin: AdminDep) -> Restriction:
    """Restrict an address from sending or receiving (admin only)."""
    return await run_in_threadpool(mailserver_service.add_restriction, kind, payload.address)


@router.delete("/restrictions/{kind}/{address}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_restriction(kind: str, address: str, _admin: AdminDep) -> None:
    """Remove a send or receive restriction (admin only)."""
    await run_in_threadpool(mailserver_service.delete_restriction, kind, address)


# ── Global Sieve scripts ──────────────────────────────────────────────────────


@router.get("/sieve/{scope}", response_model=SieveScript)
async def get_sieve_script(scope: SieveScope, _admin: AdminDep) -> SieveScript:
    """Return the global Sieve script running before/after user scripts (admin only)."""
    return await run_in_threadpool(mailserver_service.get_sieve_script, scope)


@router.put("/sieve/{scope}", response_model=SieveScript)
async def update_sieve_script(
    scope: SieveScope, payload: SieveScriptUpdate, _admin: AdminDep
) -> SieveScript:
    """Replace a global Sieve script; takes effect on restart (admin only)."""
    return await run_in_threadpool(mailserver_service.set_sieve_script, scope, payload.content)


# ── Postfix mail queue ────────────────────────────────────────────────────────


@router.get("/queue", response_model=QueueSummary)
async def get_queue(_admin: AdminDep) -> QueueSummary:
    """Return every message sitting in the Postfix queue (admin only)."""
    return await run_in_threadpool(mailserver_service.get_queue)


@router.post("/queue/flush", response_model=QueueActionResult)
async def flush_queue(_admin: AdminDep) -> QueueActionResult:
    """Attempt delivery of every deferred message now (admin only)."""
    return await run_in_threadpool(mailserver_service.flush_queue)


@router.delete("/queue", response_model=QueueActionResult)
async def delete_all_queued(_admin: AdminDep) -> QueueActionResult:
    """Delete every message currently in the Postfix queue (admin only)."""
    return await run_in_threadpool(mailserver_service.delete_all_queued)


@router.delete("/queue/{queue_id}", response_model=QueueActionResult)
async def delete_queued_message(queue_id: str, _admin: AdminDep) -> QueueActionResult:
    """Delete a single message from the Postfix queue (admin only)."""
    return await run_in_threadpool(mailserver_service.delete_queued_message, queue_id)


# ── TLS certificate, DNS records and environment (read-only) ──────────────────


@router.get("/tls", response_model=TlsCertificate)
async def get_tls_certificate(_admin: AdminDep) -> TlsCertificate:
    """Return the TLS certificate Postfix serves, with its expiry (admin only)."""
    return await run_in_threadpool(mailserver_service.get_tls_certificate)


@router.get("/dns", response_model=list[DomainDnsRecords])
async def list_dns_records(_admin: AdminDep) -> list[DomainDnsRecords]:
    """Return the MX, SPF, DMARC and DKIM records to publish (admin only)."""
    return await run_in_threadpool(mailserver_service.list_dns_records)


@router.get("/environment", response_model=MailserverEnvironment)
async def get_environment(_admin: AdminDep) -> MailserverEnvironment:
    """Return the mailserver's effective environment, set at startup (admin only)."""
    return await run_in_threadpool(mailserver_service.get_environment)


# ── Mail log (read-only) ──────────────────────────────────────────────────────


@router.get("/logs", response_model=MailLog)
async def get_mail_logs(_admin: AdminDep) -> MailLog:
    """Return the trailing lines of the mailserver mail log (admin only)."""
    return await run_in_threadpool(mailserver_service.get_mail_logs)


# ── Runtime health (read-only) ────────────────────────────────────────────────


@router.get("/services", response_model=list[ServiceStatus])
async def list_services(_admin: AdminDep) -> list[ServiceStatus]:
    """Report the state of every supervised process in the container (admin only)."""
    return await run_in_threadpool(mailserver_service.list_services)


@router.get("/stats", response_model=MailStats)
async def get_mail_stats(_admin: AdminDep) -> MailStats:
    """Count deliveries, rejections and bounces over the trailing window (admin only)."""
    return await run_in_threadpool(mailserver_service.get_mail_stats)


# ── Dovecot master accounts ───────────────────────────────────────────────────


@router.get("/dovecot-masters", response_model=list[DovecotMaster])
async def list_dovecot_masters(_admin: AdminDep) -> list[DovecotMaster]:
    """List the Dovecot master accounts (admin only, no passwords)."""
    return await run_in_threadpool(mailserver_service.list_dovecot_masters)


@router.post("/dovecot-masters", response_model=DovecotMaster, status_code=status.HTTP_201_CREATED)
async def create_dovecot_master(payload: DovecotMasterCreate, _admin: AdminDep) -> DovecotMaster:
    """Add a Dovecot master account (admin only)."""
    return await run_in_threadpool(
        mailserver_service.create_dovecot_master, payload.name, payload.password
    )


@router.delete("/dovecot-masters/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dovecot_master(name: str, _admin: AdminDep) -> None:
    """Remove a Dovecot master account (admin only)."""
    await run_in_threadpool(mailserver_service.delete_dovecot_master, name)
