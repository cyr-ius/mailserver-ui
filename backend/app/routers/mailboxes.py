"""Mailbox management endpoints (mailbox managers and administrators).

Manages docker-mailserver mail accounts (``postfix-accounts.cf``), their quotas
(``dovecot-quotas.cf``), their inbound aliases (``postfix-virtual.cf``) and their
personal Sieve filter (``<email>.dovecot.sieve``), stored in the shared config
volume. Every operation requires at least the ``mailbox_manager`` role.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.concurrency import run_in_threadpool

from ..auth import SessionUser
from ..depends import require_mailbox_manager
from ..models.mailbox_models import (
    Alias,
    AliasCreate,
    Mailbox,
    MailboxCreate,
    MailboxFeatures,
    MailboxPasswordUpdate,
    MailboxSieveScript,
    MailboxSieveScriptUpdate,
    MailboxUsageSummary,
    QuotaUpdate,
)
from ..services import mailbox_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])

ManagerDep = Annotated[SessionUser, Depends(require_mailbox_manager)]


# ── Accounts ──────────────────────────────────────────────────────────────────


@router.get("", response_model=list[Mailbox])
async def list_mailboxes(_manager: ManagerDep) -> list[Mailbox]:
    """List all mail accounts (mailbox manager)."""
    return mailbox_service.list_mailboxes()


@router.get("/features", response_model=MailboxFeatures)
async def get_features(_manager: ManagerDep) -> MailboxFeatures:
    """Report the mailserver toggles bearing on mailbox management (mailbox manager).

    Declared before ``/{email}`` so that "features" is not read as an address.
    """
    return await run_in_threadpool(mailbox_service.get_features)


@router.get("/usage", response_model=MailboxUsageSummary)
async def get_usage(_manager: ManagerDep) -> MailboxUsageSummary:
    """Report the disk each mail account really occupies (mailbox manager).

    Declared before ``/{email}`` so that "usage" is not read as an address.
    Unlike the ``quota`` field of a mailbox — the configured limit — this asks
    Dovecot what is actually stored, so it shells out to the container.
    """
    return await run_in_threadpool(mailbox_service.get_usage)


@router.post("", response_model=Mailbox, status_code=status.HTTP_201_CREATED)
async def create_mailbox(payload: MailboxCreate, _manager: ManagerDep) -> Mailbox:
    """Create a new mail account, optionally with a quota (mailbox manager)."""
    return mailbox_service.create_mailbox(str(payload.email), payload.password, payload.quota)


@router.patch("/{email}/password", response_model=Mailbox)
async def reset_password(
    email: str,
    payload: MailboxPasswordUpdate,
    _manager: ManagerDep,
) -> Mailbox:
    """Reset the password of an existing mail account (mailbox manager)."""
    return mailbox_service.set_password(email, payload.new_password)


@router.put("/{email}/quota", response_model=Mailbox)
async def set_quota(email: str, payload: QuotaUpdate, _manager: ManagerDep) -> Mailbox:
    """Set or clear the quota of a mail account (mailbox manager).

    An empty/omitted ``quota`` clears any existing limit.
    """
    return mailbox_service.set_quota(email, payload.quota)


@router.delete("/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mailbox(email: str, _manager: ManagerDep) -> None:
    """Delete a mail account with its quota and inbound aliases (mailbox manager).

    The maildir is left on disk.
    """
    mailbox_service.delete_mailbox(email)


# ── Aliases ───────────────────────────────────────────────────────────────────


@router.get("/{email}/aliases", response_model=list[Alias])
async def list_aliases(email: str, _manager: ManagerDep) -> list[Alias]:
    """List the aliases forwarding to a mail account (mailbox manager)."""
    return mailbox_service.list_aliases_for(email)


@router.post("/{email}/aliases", response_model=Alias, status_code=status.HTTP_201_CREATED)
async def add_alias(email: str, payload: AliasCreate, _manager: ManagerDep) -> Alias:
    """Add an alias forwarding to a mail account (mailbox manager)."""
    return mailbox_service.add_alias(email, str(payload.alias))


@router.delete("/{email}/aliases/{alias}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alias(email: str, alias: str, _manager: ManagerDep) -> None:
    """Remove an alias forwarding to a mail account (mailbox manager)."""
    mailbox_service.delete_alias(email, alias)


# ── Personal Sieve filter ─────────────────────────────────────────────────────


@router.get("/{email}/sieve", response_model=MailboxSieveScript)
async def get_sieve_script(email: str, _manager: ManagerDep) -> MailboxSieveScript:
    """Return the personal Sieve filter of a mail account (mailbox manager)."""
    return await run_in_threadpool(mailbox_service.get_sieve_script, email)


@router.put("/{email}/sieve", response_model=MailboxSieveScript)
async def set_sieve_script(
    email: str,
    payload: MailboxSieveScriptUpdate,
    _manager: ManagerDep,
) -> MailboxSieveScript:
    """Replace the personal Sieve filter of a mail account (mailbox manager).

    An empty script removes the filter. It takes effect on the next restart.
    """
    return await run_in_threadpool(mailbox_service.set_sieve_script, email, payload.content)


@router.delete("/{email}/sieve", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sieve_script(email: str, _manager: ManagerDep) -> None:
    """Remove the personal Sieve filter of a mail account (mailbox manager)."""
    await run_in_threadpool(mailbox_service.delete_sieve_script, email)
