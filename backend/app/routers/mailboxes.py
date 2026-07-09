"""Mailbox management endpoints (mailbox managers and administrators).

Manages docker-mailserver mail accounts (``postfix-accounts.cf``), their quotas
(``dovecot-quotas.cf``) and their inbound aliases (``postfix-virtual.cf``),
stored in the shared config volume. Every operation requires at least the
``mailbox_manager`` role.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from ..auth import SessionUser
from ..depends import require_mailbox_manager
from ..models.mailbox_models import (
    Alias,
    AliasCreate,
    Mailbox,
    MailboxCreate,
    MailboxPasswordUpdate,
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
