"""API schemas for docker-mailserver mailbox management.

Mailboxes are not stored in the application database: they live in the
docker-mailserver flat files shared with the mailserver container through a
common volume:

* ``postfix-accounts.cf`` — one ``email|{scheme}hash`` line per account;
* ``postfix-virtual.cf``  — one ``alias target`` line per alias mapping;
* ``dovecot-quotas.cf``   — one ``email:quota`` line per quota-limited account.

These Pydantic schemas describe the request/response shapes only; persistence is
handled by :mod:`app.services.mailbox_service`.
"""

from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

# A Dovecot quota, e.g. ``5G`` or ``512M``. Units: K/M/G/T (binary suffixes).
QuotaStr = Annotated[str, Field(pattern=r"^\d+[KMGT]$")]


class Mailbox(BaseModel):
    """A single mail account, as exposed by the API (never the password hash)."""

    email: EmailStr
    domain: str
    quota: str | None = None


class MailboxCreate(BaseModel):
    """Request schema for creating a mailbox."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=1024)
    quota: QuotaStr | None = None


class MailboxPasswordUpdate(BaseModel):
    """Request schema for resetting a mailbox password."""

    new_password: str = Field(min_length=8, max_length=1024)


class QuotaUpdate(BaseModel):
    """Request schema for setting or clearing a mailbox quota.

    A ``null`` (or omitted) value clears any existing quota limit.
    """

    quota: QuotaStr | None = None


class MailboxUsage(BaseModel):
    """How much disk one mail account actually occupies, as Dovecot sees it.

    ``quota`` in :class:`Mailbox` is the *configured limit*; this is the storage
    really consumed, reported by ``doveadm quota get``.
    """

    email: str
    # Bytes currently stored in the maildir.
    used_bytes: int = 0
    # The account's storage limit in bytes, or ``None`` when unlimited.
    limit_bytes: int | None = None
    # Percentage of the limit consumed, or ``None`` when unlimited.
    percent: int | None = None
    # Messages currently stored in the maildir.
    message_count: int = 0


class MailboxUsageSummary(BaseModel):
    """Disk usage of every mail account plus the totals across all of them."""

    mailboxes: list[MailboxUsage] = Field(default_factory=list)
    total_used_bytes: int = 0
    # Sum of the configured limits; ``None`` as soon as one account is unlimited.
    total_limit_bytes: int | None = None


class Alias(BaseModel):
    """An alias address that forwards to a mailbox."""

    alias: EmailStr


class AliasCreate(BaseModel):
    """Request schema for adding an alias to a mailbox."""

    alias: EmailStr
