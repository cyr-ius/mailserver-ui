"""Mailbox service: manage docker-mailserver accounts inside the container.

docker-mailserver stores its provisioning data in flat files inside its
configuration directory. This app does not bind-mount that directory: the files
are read and written *inside* the mailserver container over the Docker socket
(see :mod:`app.services.container`):

* ``postfix-accounts.cf`` — accounts, one ``user@domain|{SHA512-CRYPT}...`` line
  each. The password portion is a Dovecot-style hash, generated here with
  ``passlib``'s SHA512-CRYPT scheme to match ``setup email add``.
* ``postfix-virtual.cf`` — aliases, one ``alias target`` (whitespace-separated)
  line each; a line may carry several comma-separated targets.
* ``dovecot-quotas.cf`` — per-account quotas, one ``user@domain:5G`` line each.
* ``<user@domain>.dovecot.sieve`` — the account's personal Sieve filter, one
  file per account. Unlike the three above it is *not* watched: the mailserver
  compiles it into the maildir at startup.

docker-mailserver watches these files and reacts automatically, so editing them
is all that is required. Writes are atomic (temp file + ``mv`` in the container)
so the mailserver's file watcher never observes a half-written file.
"""

import logging
import re

from ..config import settings
from ..exceptions import BadRequestException, ConflictException, NotFoundException
from ..models.mailbox_models import (
    Alias,
    Mailbox,
    MailboxSieveScript,
    MailboxUsage,
    MailboxUsageSummary,
)
from ..services import container
from ..services.passwords import hash_dovecot_password

logger = logging.getLogger(__name__)

# docker-mailserver flat files inside the container config directory.
_ACCOUNTS_FILENAME = "postfix-accounts.cf"
_VIRTUAL_FILENAME = "postfix-virtual.cf"
_QUOTAS_FILENAME = "dovecot-quotas.cf"

# ``doveadm quota get`` reports STORAGE in kibibytes and MESSAGE as a raw count.
_DOVEADM_STORAGE_UNIT = 1024

# An address safe to build a file name from: no slash, no "..", no whitespace.
_SIEVE_ADDRESS_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+$")


# ── Hashing ───────────────────────────────────────────────────────────────────


def _hash_password(password: str) -> str:
    """Return a Dovecot ``{SHA512-CRYPT}`` hash for ``password``."""
    return hash_dovecot_password(password)


def _normalise_email(email: str) -> str:
    """Lower-case and strip an email address for consistent comparison."""
    return email.strip().lower()


# ── Generic file access ───────────────────────────────────────────────────────


def _read_lines(filename: str) -> list[str]:
    """Return the non-empty stripped lines of ``filename`` (empty if absent)."""
    content = container.read_config(filename)
    return [line.strip() for line in content.splitlines() if line.strip()]


def _write_lines(filename: str, lines: list[str]) -> None:
    """Atomically write ``lines`` to ``filename`` (trailing newline each)."""
    payload = "".join(f"{line}\n" for line in lines)
    container.write_config(filename, payload)


# ── Accounts ──────────────────────────────────────────────────────────────────


def _split_account(line: str) -> tuple[str, str]:
    """Split an ``email|hash`` account line into its two parts."""
    email, _, password_hash = line.partition("|")
    return email.strip().lower(), password_hash.strip()


def _account_addresses() -> list[str]:
    """Return every existing account email address."""
    return [addr for addr, _ in map(_split_account, _read_lines(_ACCOUNTS_FILENAME)) if addr]


def _require_mailbox(address: str) -> None:
    """Raise ``NotFoundException`` when no account exists for ``address``."""
    if address not in _account_addresses():
        raise NotFoundException("Mailbox", address)


def list_mailboxes() -> list[Mailbox]:
    """Return every mail account (with quota), ordered by email address."""
    quotas = _read_quotas()
    mailboxes: list[Mailbox] = []
    for line in _read_lines(_ACCOUNTS_FILENAME):
        email, _hash = _split_account(line)
        if not email or "@" not in email:
            continue
        mailboxes.append(
            Mailbox(email=email, domain=email.rpartition("@")[2], quota=quotas.get(email))
        )
    mailboxes.sort(key=lambda m: m.email)
    return mailboxes


def create_mailbox(email: str, password: str, quota: str | None = None) -> Mailbox:
    """Append a new mail account, rejecting duplicates. Optionally set a quota."""
    address = _normalise_email(email)
    if "@" not in address:
        raise BadRequestException("A mailbox address must contain a domain")

    lines = _read_lines(_ACCOUNTS_FILENAME)
    if any(_split_account(line)[0] == address for line in lines):
        raise ConflictException(f"Mailbox {address} already exists")

    lines.append(f"{address}|{_hash_password(password)}")
    _write_lines(_ACCOUNTS_FILENAME, lines)
    if quota:
        _set_quota_line(address, quota)
    logger.info("Created mailbox %s", address)
    return Mailbox(email=address, domain=address.rpartition("@")[2], quota=quota)


def delete_mailbox(email: str) -> None:
    """Remove a mail account along with its quota, aliases and Sieve filter.

    The maildir itself is left untouched on disk.
    """
    address = _normalise_email(email)
    lines = _read_lines(_ACCOUNTS_FILENAME)
    remaining = [line for line in lines if _split_account(line)[0] != address]
    if len(remaining) == len(lines):
        raise NotFoundException("Mailbox", address)
    _write_lines(_ACCOUNTS_FILENAME, remaining)
    _remove_quota_line(address)
    _remove_target_from_aliases(address)
    if _SIEVE_ADDRESS_RE.match(address):
        container.delete_config(_sieve_filename(address))
    logger.info("Deleted mailbox %s", address)


def set_password(email: str, new_password: str) -> Mailbox:
    """Replace the password hash of an existing mail account."""
    address = _normalise_email(email)
    lines = _read_lines(_ACCOUNTS_FILENAME)
    updated: list[str] = []
    found = False
    for line in lines:
        if _split_account(line)[0] == address:
            updated.append(f"{address}|{_hash_password(new_password)}")
            found = True
        else:
            updated.append(line)
    if not found:
        raise NotFoundException("Mailbox", address)
    _write_lines(_ACCOUNTS_FILENAME, updated)
    logger.info("Reset password for mailbox %s", address)
    return _mailbox_view(address)


# ── Quotas ────────────────────────────────────────────────────────────────────


def _read_quotas() -> dict[str, str]:
    """Return a mapping of ``email -> quota`` from ``dovecot-quotas.cf``."""
    quotas: dict[str, str] = {}
    for line in _read_lines(_QUOTAS_FILENAME):
        email, _, quota = line.partition(":")
        email, quota = email.strip().lower(), quota.strip()
        if email and quota:
            quotas[email] = quota
    return quotas


def _set_quota_line(address: str, quota: str) -> None:
    """Insert or replace the quota line for ``address``."""
    quotas = _read_quotas()
    quotas[address] = quota
    _write_lines(_QUOTAS_FILENAME, [f"{email}:{q}" for email, q in sorted(quotas.items())])


def _remove_quota_line(address: str) -> None:
    """Drop the quota line for ``address`` if present."""
    quotas = _read_quotas()
    if quotas.pop(address, None) is None:
        return
    _write_lines(_QUOTAS_FILENAME, [f"{email}:{q}" for email, q in sorted(quotas.items())])


def _parse_doveadm_amount(value: str) -> int | None:
    """Return a ``doveadm`` numeric cell, or ``None`` for ``-`` (no limit)."""
    cleaned = value.strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def get_usage() -> MailboxUsageSummary:
    """Return the disk each mail account really occupies, via ``doveadm quota get``.

    ``doveadm -f tab quota get -A`` prints a header row then two rows per account
    (``STORAGE`` and ``MESSAGE``). An unlimited account carries ``-`` as its
    limit. Accounts that have never been accessed have no maildir yet and are
    reported with a zero usage rather than omitted, so every account is listed.

    Dovecot also answers for addresses that are not accounts — an alias with a
    maildir of its own, for one. ``postfix-accounts.cf`` is this app's source of
    truth, so those rows are dropped: the usage list must hold exactly the
    mailboxes :func:`list_mailboxes` returns, or the dashboard contradicts itself.
    """
    output = container.run_in_container(
        ["doveadm", "-f", "tab", "quota", "get", "-A"],
        timeout=settings.mailserver_command_timeout,
    )

    usages: dict[str, MailboxUsage] = {
        mailbox.email: MailboxUsage(email=mailbox.email) for mailbox in list_mailboxes()
    }
    for line in output.splitlines()[1:]:  # Skip the header row.
        fields = line.split("\t")
        if len(fields) < 5:
            continue
        email, _quota_name, kind, raw_value, raw_limit = (f.strip() for f in fields[:5])
        usage = usages.get(email.lower())
        if usage is None:  # An alias or a stale maildir, not a mail account.
            continue
        value, limit = _parse_doveadm_amount(raw_value), _parse_doveadm_amount(raw_limit)
        if kind == "STORAGE":
            usage.used_bytes = (value or 0) * _DOVEADM_STORAGE_UNIT
            usage.limit_bytes = limit * _DOVEADM_STORAGE_UNIT if limit else None
        elif kind == "MESSAGE":
            usage.message_count = value or 0

    for usage in usages.values():
        if usage.limit_bytes:
            usage.percent = min(round(usage.used_bytes / usage.limit_bytes * 100), 100)

    mailboxes = sorted(usages.values(), key=lambda u: u.used_bytes, reverse=True)
    # A single unlimited account makes the overall limit meaningless.
    every_account_capped = bool(mailboxes) and all(u.limit_bytes for u in mailboxes)
    return MailboxUsageSummary(
        mailboxes=mailboxes,
        total_used_bytes=sum(u.used_bytes for u in mailboxes),
        total_limit_bytes=sum(u.limit_bytes or 0 for u in mailboxes)
        if every_account_capped
        else None,
    )


def set_quota(email: str, quota: str | None) -> Mailbox:
    """Set (or clear, when ``quota`` is falsy) the quota for a mailbox."""
    address = _normalise_email(email)
    _require_mailbox(address)
    if quota:
        _set_quota_line(address, quota)
        logger.info("Set quota %s for mailbox %s", quota, address)
    else:
        _remove_quota_line(address)
        logger.info("Cleared quota for mailbox %s", address)
    return _mailbox_view(address)


# ── Aliases ───────────────────────────────────────────────────────────────────


def _parse_alias(line: str) -> tuple[str, list[str]]:
    """Split an ``alias target1,target2`` line into its source and targets."""
    parts = line.split(None, 1)
    source = parts[0].strip().lower()
    targets = (
        [t.strip().lower() for t in parts[1].split(",") if t.strip()] if len(parts) > 1 else []
    )
    return source, targets


def list_aliases_for(email: str) -> list[Alias]:
    """Return every alias address that forwards to ``email``."""
    target = _normalise_email(email)
    _require_mailbox(target)
    aliases = [
        source
        for source, targets in map(_parse_alias, _read_lines(_VIRTUAL_FILENAME))
        if target in targets
    ]
    return [Alias(alias=a) for a in sorted(set(aliases))]


def add_alias(email: str, alias: str) -> Alias:
    """Add an alias address that forwards to ``email``."""
    target = _normalise_email(email)
    source = _normalise_email(alias)
    _require_mailbox(target)
    if "@" not in source:
        raise BadRequestException("An alias address must contain a domain")
    if source == target:
        raise BadRequestException("An alias cannot point to itself")
    if source in _account_addresses():
        raise ConflictException(f"{source} is already a mailbox and cannot be an alias")

    lines = _read_lines(_VIRTUAL_FILENAME)
    for existing_source, targets in map(_parse_alias, lines):
        if existing_source == source and target in targets:
            raise ConflictException(f"Alias {source} already forwards to {target}")

    lines.append(f"{source} {target}")
    _write_lines(_VIRTUAL_FILENAME, lines)
    logger.info("Added alias %s -> %s", source, target)
    return Alias(alias=source)


def delete_alias(email: str, alias: str) -> None:
    """Remove the alias ``alias`` forwarding to ``email``.

    Only the mapping to this mailbox is removed: any other targets on the same
    alias line are preserved.
    """
    target = _normalise_email(email)
    source = _normalise_email(alias)
    _require_mailbox(target)

    lines = _read_lines(_VIRTUAL_FILENAME)
    rebuilt: list[str] = []
    found = False
    for line in lines:
        line_source, targets = _parse_alias(line)
        if line_source == source and target in targets:
            found = True
            remaining = [t for t in targets if t != target]
            if remaining:
                rebuilt.append(f"{line_source} {','.join(remaining)}")
        else:
            rebuilt.append(line)
    if not found:
        raise NotFoundException("Alias", source)
    _write_lines(_VIRTUAL_FILENAME, rebuilt)
    logger.info("Removed alias %s -> %s", source, target)


def _remove_target_from_aliases(target: str) -> None:
    """Strip ``target`` from every alias line, dropping now-empty aliases."""
    lines = _read_lines(_VIRTUAL_FILENAME)
    rebuilt: list[str] = []
    changed = False
    for line in lines:
        source, targets = _parse_alias(line)
        if target in targets:
            changed = True
            remaining = [t for t in targets if t != target]
            if remaining:
                rebuilt.append(f"{source} {','.join(remaining)}")
        else:
            rebuilt.append(line)
    if changed:
        _write_lines(_VIRTUAL_FILENAME, rebuilt)


# ── Personal Sieve filter ─────────────────────────────────────────────────────


def _sieve_filename(address: str) -> str:
    """Return the config-volume file name holding ``address``'s Sieve filter."""
    return f"{address}.dovecot.sieve"


def _require_sieve_address(email: str) -> str:
    """Return the normalised address, rejecting anything unsafe as a file name."""
    address = _normalise_email(email)
    if not _SIEVE_ADDRESS_RE.match(address):
        raise BadRequestException(f"Invalid mailbox address: {email!r}")
    return address


def get_sieve_script(email: str) -> MailboxSieveScript:
    """Return the personal Sieve filter of an account (empty when it has none)."""
    address = _require_sieve_address(email)
    _require_mailbox(address)
    content = container.read_config(_sieve_filename(address)).strip()
    return MailboxSieveScript(email=address, content=content, configured=bool(content))


def set_sieve_script(email: str, content: str) -> MailboxSieveScript:
    """Replace the personal Sieve filter of an account.

    An empty script deletes the file rather than leaving an empty one behind:
    Dovecot would compile it into an inert script that shadows nothing, but the
    account would keep reporting a filter it does not have. The script itself is
    compiled by ``sievec`` when the mailserver starts, so a syntax error surfaces
    there rather than here.
    """
    address = _require_sieve_address(email)
    _require_mailbox(address)

    body = content.strip()
    if not body:
        container.delete_config(_sieve_filename(address))
        logger.info("Removed the Sieve filter of %s", address)
        return MailboxSieveScript(email=address, content="", configured=False)

    container.write_config(_sieve_filename(address), f"{body}\n")
    logger.info("Updated the Sieve filter of %s (%d bytes)", address, len(body))
    return MailboxSieveScript(email=address, content=body, configured=True)


def delete_sieve_script(email: str) -> None:
    """Remove the personal Sieve filter of an account."""
    address = _require_sieve_address(email)
    _require_mailbox(address)
    container.delete_config(_sieve_filename(address))
    logger.info("Deleted the Sieve filter of %s", address)


# ── Internal helpers ──────────────────────────────────────────────────────────


def _mailbox_view(address: str) -> Mailbox:
    """Build a ``Mailbox`` response for an existing account address."""
    return Mailbox(
        email=address,
        domain=address.rpartition("@")[2],
        quota=_read_quotas().get(address),
    )
