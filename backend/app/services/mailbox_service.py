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

docker-mailserver watches these files and reacts automatically, so editing them
is all that is required. Writes are atomic (temp file + ``mv`` in the container)
so the mailserver's file watcher never observes a half-written file.
"""

import logging

from ..exceptions import BadRequestException, ConflictException, NotFoundException
from ..models.mailbox_models import Alias, Mailbox
from ..services import container
from ..services.passwords import hash_dovecot_password

logger = logging.getLogger(__name__)

# docker-mailserver flat files inside the container config directory.
_ACCOUNTS_FILENAME = "postfix-accounts.cf"
_VIRTUAL_FILENAME = "postfix-virtual.cf"
_QUOTAS_FILENAME = "dovecot-quotas.cf"


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
    """Remove a mail account along with its quota and inbound aliases.

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


# ── Internal helpers ──────────────────────────────────────────────────────────


def _mailbox_view(address: str) -> Mailbox:
    """Build a ``Mailbox`` response for an existing account address."""
    return Mailbox(
        email=address,
        domain=address.rpartition("@")[2],
        quota=_read_quotas().get(address),
    )
