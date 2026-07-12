"""Mailserver service: manage docker-mailserver global config inside the container.

docker-mailserver reads part of its configuration from flat files inside its
configuration directory. This app does not bind-mount that directory: the files
are read and written *inside* the mailserver container over the Docker socket
(see :mod:`app.services.container`). This service edits the files that are not
mailbox-specific:

* ``postfix-relaymap.cf`` — maps a sender domain to a relay ``[host]:port``, or
  excludes it from the global relay when no target follows the sender;
* ``postfix-sasl-password.cf`` — SASL credentials for those relays;
* ``postfix-main.cf`` — extra Postfix ``main.cf`` parameters (key/value);
* ``postfix-master.cf`` — extra Postfix ``master.cf`` service parameters;
* ``dovecot.cf`` — extra Dovecot configuration (copied to ``local.conf``);
* ``postfix-aliases.cf`` / ``postfix-regexp.cf`` — system and PCRE aliases;
* ``before.dovecot.sieve`` / ``after.dovecot.sieve`` — global Sieve scripts;
* ``spamassassin-rules.cf`` — custom SpamAssassin rules and scores;
* ``amavis.cf`` — Amavis overrides, replacing ``/etc/amavis/conf.d/50-user``;
* ``whitelist_clients.local`` / ``whitelist_recipients`` — Postgrey whitelists;
* ``rspamd/custom-commands.conf`` — Rspamd module and worker overrides;
* ``ldap-{users,groups,aliases,domains}.cf`` — Postfix LDAP maps, only read when
  the container runs with ``ACCOUNT_PROVISIONER=LDAP``;
* ``opendkim/keys/<domain>/<selector>.txt`` or ``rspamd/dkim/*.public.txt`` —
  generated DKIM records (read-only; generation runs in the container).

It also exposes runtime-only views that no config file backs: the Postfix mail
queue, the TLS certificate, the mail log and the container's own environment.

Writes are atomic (temp file + ``mv`` in the container) so the mailserver's file
watcher never observes a half-written file. Files managed here are rewritten
wholesale and prefixed with a header noting they are owned by the UI; the header
is a comment in every format involved, so it is inert.

Only ``postfix-accounts.cf``, ``postfix-virtual.cf``, ``postfix-regexp.cf``,
``postfix-aliases.cf``, ``postfix-relaymap.cf``, ``postfix-sasl-password.cf``,
``dovecot-quotas.cf`` and ``dovecot-masters.cf`` are watched live. ``postfix-main.cf``,
``postfix-master.cf``, ``dovecot.cf``, the global Sieve scripts and the spam-filtering
files are read only when the mailserver starts, so changing them has no effect until
the container is restarted; the schemas that carry a single such file set
``restart_required``.
"""

import json
import logging
import re
from datetime import UTC, datetime, timedelta

from ..config import settings
from ..exceptions import BadRequestException, ConflictException, NotFoundException
from ..models.mailserver_models import (
    DkimGenerateRequest,
    DkimKey,
    DnsRecord,
    DomainDnsRecords,
    DovecotConfig,
    DovecotMaster,
    EnvironmentWarning,
    LdapConfig,
    LdapScope,
    MailLog,
    MailserverEnvironment,
    MailStats,
    PostfixMasterOverride,
    PostfixOverride,
    QueueActionResult,
    QueueMessage,
    QueueSummary,
    RegexAlias,
    RelayExclusion,
    RelayHost,
    RelayHostCreate,
    Restriction,
    RspamdCommand,
    RspamdOverrides,
    ServiceStatus,
    SieveScope,
    SieveScript,
    SpamConfig,
    SpamConfigScope,
    SpamFilter,
    SystemAlias,
    TlsCertificate,
)
from . import container
from .passwords import hash_dovecot_password

logger = logging.getLogger(__name__)

# docker-mailserver flat files inside the shared config directory.
_RELAYMAP_FILENAME = "postfix-relaymap.cf"
_SASL_FILENAME = "postfix-sasl-password.cf"
_POSTFIX_MAIN_FILENAME = "postfix-main.cf"
_POSTFIX_MASTER_FILENAME = "postfix-master.cf"
_DOVECOT_CONFIG_FILENAME = "dovecot.cf"
_SYSTEM_ALIASES_FILENAME = "postfix-aliases.cf"
_REGEX_ALIASES_FILENAME = "postfix-regexp.cf"
_OPENDKIM_KEYS_DIR = "opendkim/keys"
_RSPAMD_DKIM_DIR = "rspamd/dkim"
_ACCOUNTS_FILENAME = "postfix-accounts.cf"
_DOVECOT_MASTERS_FILENAME = "dovecot-masters.cf"
_SIEVE_FILENAMES: dict[str, str] = {
    "before": "before.dovecot.sieve",
    "after": "after.dovecot.sieve",
}

# Spam-filtering files docker-mailserver copies out of the config volume at
# startup: custom SpamAssassin rules, the two Postgrey whitelists that exempt a
# client or a recipient from greylisting, and the Amavis overrides that replace
# ``/etc/amavis/conf.d/50-user``.
_SPAM_CONFIG_FILENAMES: dict[str, str] = {
    "rules": "spamassassin-rules.cf",
    "whitelist-clients": "whitelist_clients.local",
    "whitelist-recipients": "whitelist_recipients",
    "amavis": "amavis.cf",
}

# The ``ENABLE_*`` toggle guarding each spam-filtering file: docker-mailserver
# only copies the file out of the config volume when its feature is on, so an
# edit made while the feature is off is stored and never read.
_SPAM_CONFIG_VARIABLES: dict[str, str] = {
    "rules": "ENABLE_SPAMASSASSIN",
    "whitelist-clients": "ENABLE_POSTGREY",
    "whitelist-recipients": "ENABLE_POSTGREY",
    "amavis": "ENABLE_AMAVIS",
}

# Rspamd's simplified override file, applied after ``rspamd/override.d/``.
_RSPAMD_COMMANDS_FILENAME = "rspamd/custom-commands.conf"

# Postfix LDAP maps, copied to ``/etc/postfix/`` when ``ACCOUNT_PROVISIONER=LDAP``.
_LDAP_FILENAMES: dict[str, str] = {
    "users": "ldap-users.cf",
    "groups": "ldap-groups.cf",
    "aliases": "ldap-aliases.cf",
    "domains": "ldap-domains.cf",
}

# Each map gets its ``query_filter`` from its own environment variable, which
# docker-mailserver exports as ``LDAP_QUERY_FILTER`` just before rewriting it.
_LDAP_QUERY_FILTER_VARIABLES: dict[str, str] = {
    "users": "LDAP_QUERY_FILTER_USER",
    "groups": "LDAP_QUERY_FILTER_GROUP",
    "aliases": "LDAP_QUERY_FILTER_ALIAS",
    "domains": "LDAP_QUERY_FILTER_DOMAIN",
}

# A Postfix LDAP map line: ``key = value``, the key a lower_snake identifier.
_LDAP_LINE_RE = re.compile(r"^[A-Za-z0-9_]+\s*=")

# The ``ENABLE_*`` toggles docker-mailserver ships enabled. Every other toggle
# defaults to ``0``, so only the exceptions are listed here.
_FEATURE_DEFAULTS: dict[str, str] = {
    "ENABLE_AMAVIS": "1",
    "ENABLE_OPENDKIM": "1",
    "ENABLE_POLICYD_SPF": "1",
    "ENABLE_QUOTAS": "1",
    "ENABLE_UPDATE_CHECK": "1",
}

# Variables docker-mailserver writes to ``/etc/dms-settings`` that hold a secret.
# They are read-only here, so their value is of no use to the UI.
_SECRET_VARIABLES = frozenset({"LDAP_BIND_PW", "SRS_SECRET"})

# What replaces a secret's value in the environment view.
_REDACTED = "••••••••"

# How many arguments each ``custom-commands.conf`` directive takes, and which of
# ``target``/``option``/``value`` they land in. ``value`` always swallows the
# rest of the line, so it is the last field of every directive that has one.
_RSPAMD_COMMAND_FIELDS: dict[str, tuple[str, ...]] = {
    "set-common-option": ("option", "value"),
    "set-option-for-controller": ("option", "value"),
    "set-option-for-proxy": ("option", "value"),
    "enable-module": ("target",),
    "disable-module": ("target",),
    "set-option-for-module": ("target", "option", "value"),
    "add-line": ("target", "value"),
}

# An Rspamd module or option name, and an override file name. Neither may carry
# a separator: they are pasted into a path under ``/etc/rspamd/override.d/``.
_RSPAMD_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_RSPAMD_FILENAME_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")

# The mailserver dumps its effective environment here when it starts.
_DMS_SETTINGS_PATH = "/etc/dms-settings"

# Where docker-mailserver's rsyslog writes the Postfix/Dovecot mail log.
_MAIL_LOG_PATH = "/var/log/mail/mail.log"

# Supervisor states meaning the process tried to run and could not. ``STOPPED``
# is deliberately absent: docker-mailserver leaves every disabled feature in
# that state, so treating it as a failure would flag a healthy container.
_FAILED_SERVICE_STATES = frozenset({"FATAL", "BACKOFF", "EXITED", "UNKNOWN"})

# Access maps backing ``setup email restrict <send|receive>``.
_RESTRICTION_FILENAMES = {
    "send": "postfix-send-access.cf",
    "receive": "postfix-receive-access.cf",
}
# Action stored next to each restricted address (docker-mailserver rejects them).
_RESTRICTION_ACTION = "REJECT"

# Header written at the top of every file this service owns.
_MANAGED_HEADER = "# Managed by Mailserver UI — manual edits may be overwritten.\n"

# Postfix parameter names are lower_snake identifiers (letters, digits, "_").
_POSTFIX_KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")

# A ``postfix-master.cf`` key: the service, its type and the parameter, as
# ``postconf -P`` expects, e.g. ``submission/inet/smtpd_sasl_security_options``.
_POSTFIX_MASTER_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[a-z]+/[A-Za-z0-9_]+$")

# A DKIM selector / domain label: letters, digits, dots and hyphens.
_DKIM_TOKEN_RE = re.compile(r"^[A-Za-z0-9.-]+$")

# A local alias name in ``/etc/aliases``: no "@", no whitespace, no ":".
_SYSTEM_ALIAS_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

# A Postfix PCRE pattern, delimiters included, with optional trailing flags.
_REGEX_ALIAS_PATTERN_RE = re.compile(r"^/.+/[imxs]*$")

# A Postfix queue ID as printed by ``postqueue``; ``postsuper`` also accepts
# ``ALL``, which is why only alphanumerics are allowed through here.
_QUEUE_ID_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")

# The two timestamps rsyslog may open a mail log line with: RFC 3339
# (``2026-07-10T12:34:56.123456+00:00``) and the traditional, year-less
# ``Jul 10 12:34:56`` — where a single-digit day is space-padded.
_LOG_ISO_DATE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\S+)?)"
)
_LOG_BSD_DATE_RE = re.compile(r"^([A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2})")

# The message-id Postfix's ``cleanup`` prints, chevrons included, e.g.
# ``message-id=<a@b>``. It identifies a message across the two cleanup lines an
# Amavis round trip produces.
_LOG_MESSAGE_ID_RE = re.compile(r"message-id=(<[^>]*>|\S+)")

# Substrings marking a rejection that only defers the sender. Postgrey answers
# with ``POSTGREY_TEXT`` (``Delayed by Postgrey``, reworded by some operators)
# and Rspamd with ``Try again later``; both are matched lower-cased.
_GREYLIST_MARKERS = ("greylist", "postgrey", "try again later")

# Amavis prints ``Blocked INFECTED (Eicar-Test-Signature)`` for a virus, and
# ``Blocked SPAM`` / ``Passed SPAMMY`` for spam. Rspamd rejects through the
# milter with its own wording.
_LOG_VIRUS_RE = re.compile(r"\bINFECTED\b")
_LOG_SPAM_RE = re.compile(
    r"\b(?:Blocked|Passed) SPAM(?:MY)?\b|\bSpam message rejected\b"
)


# ── Generic file access ───────────────────────────────────────────────────────


def _read_config_lines(filename: str) -> list[str]:
    """Return the meaningful lines of ``filename`` (no blanks, no comments)."""
    content = container.read_config(filename)
    return [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _write_managed(filename: str, lines: list[str]) -> None:
    """Atomically (re)write ``filename`` with the managed header and ``lines``."""
    payload = _MANAGED_HEADER + "".join(f"{line}\n" for line in lines)
    container.write_config(filename, payload)


def _read_managed_body(filename: str) -> str:
    """Return ``filename`` without the managed header, for free-form contents."""
    content = container.read_config(filename)
    if content.startswith(_MANAGED_HEADER):
        content = content[len(_MANAGED_HEADER) :]
    return content.strip()


def _write_managed_body(filename: str, content: str) -> None:
    """Atomically (re)write ``filename`` with the managed header and free-form text."""
    body = content.strip()
    container.write_config(
        filename, f"{_MANAGED_HEADER}{body}\n" if body else _MANAGED_HEADER
    )


def _normalise_sender(sender: str) -> str:
    """Lower-case and strip a relay sender key for consistent comparison."""
    return sender.strip().lower()


# ── SMTP relay (smarthost) ────────────────────────────────────────────────────


def _parse_relay_target(token: str) -> tuple[str, int]:
    """Split a relay target ``[host]:port`` / ``host:port`` / ``host`` into parts."""
    token = token.strip()
    port = 587
    if token.startswith("["):
        host, _, after = token[1:].partition("]")
        suffix = after.lstrip(":")
        if suffix.isdigit():
            port = int(suffix)
    elif ":" in token:
        host, _, raw_port = token.rpartition(":")
        if raw_port.isdigit():
            port = int(raw_port)
    else:
        host = token
    return host.strip(), port


def _parse_relaymap() -> dict[str, tuple[str, int] | None]:
    """Return a mapping of ``sender -> (host, port)`` from ``postfix-relaymap.cf``.

    A sender with no relay target maps to ``None``: that is how
    ``setup relay exclude-domain`` opts a domain out of the global relay host.
    Such lines are kept so rewriting the file never drops an exclusion.
    """
    relays: dict[str, tuple[str, int] | None] = {}
    for line in _read_config_lines(_RELAYMAP_FILENAME):
        parts = line.split()
        sender = parts[0].lower()
        if len(parts) < 2:
            relays[sender] = None
            continue
        host, port = _parse_relay_target(parts[1])
        if host:
            relays[sender] = (host, port)
    return relays


def _parse_sasl() -> dict[str, tuple[str, str]]:
    """Return a mapping of ``sender -> (username, password)`` from the SASL file."""
    creds: dict[str, tuple[str, str]] = {}
    for line in _read_config_lines(_SASL_FILENAME):
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        username, _, password = parts[1].partition(":")
        creds[parts[0].lower()] = (username.strip(), password.strip())
    return creds


def _write_relaymap(relays: dict[str, tuple[str, int] | None]) -> None:
    """Persist the relay map, one ``sender\t[host]:port`` line per entry.

    Senders mapped to ``None`` are written as a lone sender key, preserving the
    global-relay exclusions ``setup relay exclude-domain`` creates.
    """
    lines = [
        sender if target is None else f"{sender}\t[{target[0]}]:{target[1]}"
        for sender, target in sorted(relays.items())
    ]
    _write_managed(_RELAYMAP_FILENAME, lines)


def _write_sasl(creds: dict[str, tuple[str, str]]) -> None:
    """Persist the SASL credentials, dropping entries without a username."""
    lines = [
        f"{sender}\t{username}:{password}"
        for sender, (username, password) in sorted(creds.items())
        if username
    ]
    _write_managed(_SASL_FILENAME, lines)


def _require_relay_sender(sender: str) -> str:
    """Return the normalised sender key, rejecting anything that is not a sender."""
    key = _normalise_sender(sender)
    if "@" not in key:
        raise BadRequestException(
            "A relay sender must be a domain (e.g. @example.com) or a full address"
        )
    return key


def list_relays() -> list[RelayHost]:
    """Return every configured SMTP relay, ordered by sender (no passwords).

    Global-relay exclusions are not relays; see :func:`list_relay_exclusions`.
    """
    creds = _parse_sasl()
    relays: list[RelayHost] = []
    for sender, target in sorted(_parse_relaymap().items()):
        if target is None:
            continue
        host, port = target
        username, _password = creds.get(sender, ("", ""))
        relays.append(
            RelayHost(
                sender=sender,
                host=host,
                port=port,
                username=username or None,
                has_credentials=bool(username),
            )
        )
    return relays


def create_relay(payload: RelayHostCreate) -> RelayHost:
    """Add an SMTP relay for a sender domain, rejecting duplicates."""
    sender = _require_relay_sender(payload.sender)

    relays = _parse_relaymap()
    if sender in relays:
        raise ConflictException(f"A relay or exclusion already exists for {sender}")

    relays[sender] = (payload.host.strip(), payload.port)
    _write_relaymap(relays)

    username = (payload.username or "").strip()
    if username:
        creds = _parse_sasl()
        creds[sender] = (username, payload.password or "")
        _write_sasl(creds)

    logger.info("Added SMTP relay for %s -> %s:%s", sender, payload.host, payload.port)
    return RelayHost(
        sender=sender,
        host=payload.host.strip(),
        port=payload.port,
        username=username or None,
        has_credentials=bool(username),
    )


def delete_relay(sender: str) -> None:
    """Remove the SMTP relay (and any credentials) for ``sender``."""
    key = _normalise_sender(sender)
    relays = _parse_relaymap()
    if relays.get(key) is None:
        raise NotFoundException("Relay", key)
    del relays[key]
    _write_relaymap(relays)

    creds = _parse_sasl()
    if creds.pop(key, None) is not None:
        _write_sasl(creds)
    logger.info("Removed SMTP relay for %s", key)


# ── Global relay exclusions ───────────────────────────────────────────────────


def list_relay_exclusions() -> list[RelayExclusion]:
    """Return the senders opted out of the global relay, ordered by sender."""
    return [
        RelayExclusion(sender=sender)
        for sender, target in sorted(_parse_relaymap().items())
        if target is None
    ]


def create_relay_exclusion(sender: str) -> RelayExclusion:
    """Opt a sender domain out of the global relay, rejecting duplicates."""
    key = _require_relay_sender(sender)
    relays = _parse_relaymap()
    if key in relays:
        raise ConflictException(f"A relay or exclusion already exists for {key}")

    relays[key] = None
    _write_relaymap(relays)
    logger.info("Excluded %s from the global relay host", key)
    return RelayExclusion(sender=key)


def delete_relay_exclusion(sender: str) -> None:
    """Send ``sender``'s mail through the global relay again."""
    key = _normalise_sender(sender)
    relays = _parse_relaymap()
    if key not in relays or relays[key] is not None:
        raise NotFoundException("Relay exclusion", key)
    del relays[key]
    _write_relaymap(relays)
    logger.info("Removed the global relay exclusion for %s", key)


# ── Postfix overrides (main.cf) ───────────────────────────────────────────────


def list_postfix_overrides() -> list[PostfixOverride]:
    """Return the ``key = value`` overrides stored in ``postfix-main.cf``."""
    overrides: list[PostfixOverride] = []
    for line in _read_config_lines(_POSTFIX_MAIN_FILENAME):
        key, sep, value = line.partition("=")
        key = key.strip()
        if key and sep:
            overrides.append(PostfixOverride(key=key, value=value.strip()))
    return overrides


def set_postfix_overrides(overrides: list[PostfixOverride]) -> list[PostfixOverride]:
    """Replace the full set of Postfix overrides, validating parameter names.

    Insertion order is preserved; duplicate keys keep their last value.
    """
    cleaned: dict[str, str] = {}
    for override in overrides:
        key = override.key.strip()
        if not key:
            continue
        if not _POSTFIX_KEY_RE.match(key):
            raise BadRequestException(f"Invalid Postfix parameter name: {key!r}")
        cleaned[key] = override.value.strip()

    _write_managed(
        _POSTFIX_MAIN_FILENAME, [f"{key} = {value}" for key, value in cleaned.items()]
    )
    logger.info("Updated %d Postfix override(s)", len(cleaned))
    return [PostfixOverride(key=key, value=value) for key, value in cleaned.items()]


# ── Postfix master overrides (master.cf) ──────────────────────────────────────


def list_postfix_master_overrides() -> list[PostfixMasterOverride]:
    """Return the ``service/type/parameter = value`` lines of ``postfix-master.cf``."""
    overrides: list[PostfixMasterOverride] = []
    for line in _read_config_lines(_POSTFIX_MASTER_FILENAME):
        key, sep, value = line.partition("=")
        key = key.strip()
        if key and sep:
            overrides.append(PostfixMasterOverride(key=key, value=value.strip()))
    return overrides


def set_postfix_master_overrides(
    overrides: list[PostfixMasterOverride],
) -> list[PostfixMasterOverride]:
    """Replace the full set of Postfix master overrides, validating each key.

    Lines are written without spaces around ``=`` because docker-mailserver
    passes each one straight to ``postconf -P``, which expects that form.
    """
    cleaned: dict[str, str] = {}
    for override in overrides:
        key = override.key.strip()
        if not key:
            continue
        if not _POSTFIX_MASTER_KEY_RE.match(key):
            raise BadRequestException(
                f"Invalid Postfix master parameter: {key!r}. Expected "
                "service/type/parameter, e.g. submission/inet/smtpd_tls_security_level"
            )
        cleaned[key] = override.value.strip()

    _write_managed(
        _POSTFIX_MASTER_FILENAME, [f"{key}={value}" for key, value in cleaned.items()]
    )
    logger.info("Updated %d Postfix master override(s)", len(cleaned))
    return [
        PostfixMasterOverride(key=key, value=value) for key, value in cleaned.items()
    ]


# ── Dovecot configuration override (dovecot.cf) ───────────────────────────────


def get_dovecot_config() -> DovecotConfig:
    """Return the raw ``dovecot.cf`` override (empty when the file is absent)."""
    return DovecotConfig(content=_read_managed_body(_DOVECOT_CONFIG_FILENAME))


def set_dovecot_config(content: str) -> DovecotConfig:
    """Replace ``dovecot.cf`` wholesale; docker-mailserver copies it at startup.

    The contents are Dovecot's own configuration syntax and are not validated
    here: a bad file only surfaces when the mailserver restarts.
    """
    payload = content.strip()
    _write_managed_body(_DOVECOT_CONFIG_FILENAME, payload)
    logger.info("Updated the Dovecot configuration override (%d bytes)", len(payload))
    return DovecotConfig(content=payload)


# ── DKIM (read-only) ──────────────────────────────────────────────────────────


def _parse_dkim_txt(raw: str) -> tuple[str, str]:
    """Return ``(txt_value, public_key)`` from a BIND-format DKIM ``.txt`` file."""
    txt_value = "".join(re.findall(r'"([^"]*)"', raw))
    match = re.search(r"p=([A-Za-z0-9+/=]+)", txt_value)
    return txt_value, (match.group(1) if match else "")


def _opendkim_keys() -> list[DkimKey]:
    """Return the DKIM records under ``opendkim/keys/<domain>/<selector>.txt``."""
    keys: list[DkimKey] = []
    for rel in container.list_config_files(_OPENDKIM_KEYS_DIR, ".txt"):
        domain, sep, filename = rel.partition("/")
        if not sep or "/" in filename:
            continue
        selector = filename[: -len(".txt")]
        txt_value, public_key = _parse_dkim_txt(
            container.read_config(f"{_OPENDKIM_KEYS_DIR}/{rel}")
        )
        keys.append(
            DkimKey(
                domain=domain,
                selector=selector,
                record_name=f"{selector}._domainkey.{domain}.",
                public_key=public_key,
                txt_value=txt_value,
            )
        )
    return keys


def _rspamd_keys() -> list[DkimKey]:
    """Return the DKIM records under ``rspamd/dkim/*.public.txt``.

    ``rspamd-dkim`` names each file ``<keytype>[-<keysize>]-<selector>-<domain>``,
    which cannot be split reliably since a selector may itself contain hyphens.
    The selector is therefore read from the record (``<selector>._domainkey``)
    and the domain is whatever follows it in the file name.
    """
    keys: list[DkimKey] = []
    for rel in container.list_config_files(_RSPAMD_DKIM_DIR, ".public.txt"):
        raw = container.read_config(f"{_RSPAMD_DKIM_DIR}/{rel}")
        match = re.search(r"^(\S+)\._domainkey", raw)
        if not match:
            continue
        selector = match.group(1)
        _, marker, domain = rel[: -len(".public.txt")].partition(f"-{selector}-")
        if not marker or not domain:
            continue
        txt_value, public_key = _parse_dkim_txt(raw)
        keys.append(
            DkimKey(
                domain=domain,
                selector=selector,
                record_name=f"{selector}._domainkey.{domain}.",
                public_key=public_key,
                txt_value=txt_value,
            )
        )
    return keys


def list_dkim_keys() -> list[DkimKey]:
    """Return the generated DKIM public records, from whichever backend signs mail.

    OpenDKIM and Rspamd store their keys in different directories, and only the
    one selected by ``ENABLE_RSPAMD`` is authoritative: reading the other would
    advertise records the mailserver does not actually sign with.
    """
    keys = _rspamd_keys() if dkim_backend() == "rspamd" else _opendkim_keys()
    return sorted(keys, key=lambda key: (key.domain, key.selector))


def generate_dkim(payload: DkimGenerateRequest) -> list[DkimKey]:
    """Generate DKIM keys via ``setup config dkim`` inside the container.

    When no domain is given, keys are generated for every configured domain.
    Returns the refreshed key list.
    """
    selector = payload.selector.strip()
    if not _DKIM_TOKEN_RE.match(selector):
        raise BadRequestException(f"Invalid DKIM selector: {selector!r}")

    args = [
        "setup",
        "config",
        "dkim",
        "keysize",
        str(payload.key_size),
        "selector",
        selector,
    ]
    if payload.domain:
        domain = payload.domain.strip().lower()
        if not _DKIM_TOKEN_RE.match(domain):
            raise BadRequestException(f"Invalid domain: {domain!r}")
        args += ["domain", domain]

    container.run_in_container(args, timeout=settings.mailserver_command_timeout)
    logger.info(
        "Generated DKIM keys (selector=%s, domain=%s)",
        selector,
        payload.domain or "all",
    )
    return list_dkim_keys()


# ── Send/receive restrictions ─────────────────────────────────────────────────


def _restriction_filename(kind: str) -> str:
    """Return the access-map filename for ``kind`` (``send`` or ``receive``)."""
    filename = _RESTRICTION_FILENAMES.get(kind)
    if filename is None:
        raise BadRequestException("Restriction kind must be 'send' or 'receive'")
    return filename


def _restriction_addresses(kind: str) -> list[str]:
    """Return the restricted addresses stored in the access map for ``kind``."""
    addresses: list[str] = []
    for line in _read_config_lines(_restriction_filename(kind)):
        address = line.split()[0].strip().lower()
        if address:
            addresses.append(address)
    return addresses


def list_restrictions(kind: str) -> list[Restriction]:
    """Return every restricted address for ``kind``, ordered alphabetically."""
    return [
        Restriction(kind=kind, address=address)
        for address in sorted(set(_restriction_addresses(kind)))
    ]


def add_restriction(kind: str, address: str) -> Restriction:
    """Restrict ``address`` from sending/receiving, rejecting duplicates."""
    filename = _restriction_filename(kind)
    entry = address.strip().lower()
    if "@" not in entry:
        raise BadRequestException(
            "A restriction must target an address or a domain (@example.com)"
        )

    addresses = _restriction_addresses(kind)
    if entry in addresses:
        raise ConflictException(f"{entry} is already restricted")

    addresses.append(entry)
    _write_managed(
        filename, [f"{addr}\t{_RESTRICTION_ACTION}" for addr in sorted(set(addresses))]
    )
    logger.info("Added %s restriction for %s", kind, entry)
    return Restriction(kind=kind, address=entry)


def delete_restriction(kind: str, address: str) -> None:
    """Remove the ``kind`` restriction for ``address``."""
    filename = _restriction_filename(kind)
    entry = address.strip().lower()
    addresses = _restriction_addresses(kind)
    if entry not in addresses:
        raise NotFoundException("Restriction", entry)
    remaining = [addr for addr in addresses if addr != entry]
    _write_managed(
        filename, [f"{addr}\t{_RESTRICTION_ACTION}" for addr in sorted(set(remaining))]
    )
    logger.info("Removed %s restriction for %s", kind, entry)


# ── Mail log (read-only) ──────────────────────────────────────────────────────


def get_mail_logs() -> MailLog:
    """Return the trailing lines of the mailserver mail log via ``docker exec``."""
    output = container.run_in_container(
        ["tail", "-n", str(settings.mailserver_log_lines), _MAIL_LOG_PATH],
        timeout=settings.mailserver_command_timeout,
    )
    return MailLog(lines=output.splitlines())


# ── Runtime health (read-only) ────────────────────────────────────────────────


def _parse_service_line(line: str) -> ServiceStatus | None:
    """Build a :class:`ServiceStatus` from one ``supervisorctl status`` row.

    Rows read ``<name> <STATE> <detail…>``, columns padded with spaces.
    """
    fields = line.split(None, 2)
    if len(fields) < 2:
        return None
    name, state = fields[0], fields[1]
    return ServiceStatus(
        name=name,
        state=state,
        running=state == "RUNNING",
        failed=state in _FAILED_SERVICE_STATES,
        detail=fields[2].strip() if len(fields) > 2 else "",
    )


def list_services() -> list[ServiceStatus]:
    """Return every supervised process in the mailserver container, by name.

    ``supervisorctl status`` exits 3 as soon as one process is not RUNNING —
    which a healthy docker-mailserver always is, since it supervises the
    features its environment disabled. Hence ``check=False``.
    """
    output = container.run_in_container(
        ["supervisorctl", "status"],
        timeout=settings.mailserver_command_timeout,
        check=False,
    )
    services = [
        service
        for service in map(_parse_service_line, output.splitlines())
        if service is not None
    ]
    return sorted(services, key=lambda service: service.name)


def _parse_log_timestamp(line: str, now: datetime) -> datetime | None:
    """Return the timestamp of a mail log line, or ``None`` when undated.

    rsyslog writes either an RFC 3339 stamp or the traditional ``Mon DD
    HH:MM:SS`` form, which carries no year: it is read as the most recent such
    date not in the future. An undated stamp is assumed to be UTC, as the
    mailserver container is.
    """
    iso_match = _LOG_ISO_DATE_RE.match(line)
    if iso_match:
        try:
            parsed = datetime.fromisoformat(iso_match.group(1))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    bsd_match = _LOG_BSD_DATE_RE.match(line)
    if not bsd_match:
        return None
    try:
        parsed = datetime.strptime(bsd_match.group(1), "%b %d %H:%M:%S").replace(
            year=now.year, tzinfo=UTC
        )
    except ValueError:  # Feb 29 of a non-leap current year.
        return None
    # A stamp in the future can only be last year's: the log crossed a new year.
    return parsed.replace(year=now.year - 1) if parsed > now else parsed


def _is_greylisted(line: str) -> bool:
    """Return whether a rejection line is a greylisting deferral, not a refusal.

    Postgrey answers a temporary 4xx carrying ``POSTGREY_TEXT`` — ``Delayed by
    Postgrey`` by default, but operators reword it — while Rspamd soft-rejects
    with ``Try again later``. Postfix logs both as a rejection, yet the sender is
    expected back: counting them as refused mail would slander every legitimate
    stranger.
    """
    lowered = line.lower()
    return any(marker in lowered for marker in _GREYLIST_MARKERS)


def get_mail_stats() -> MailStats:
    """Count deliveries, rejections and bounces over the trailing stats window.

    Postfix logs one line per delivery attempt; the counters below key off the
    ``status=`` field it prints, plus the ``cleanup`` line every accepted message
    produces. Lines older than the window, or that carry no timestamp this app
    can read, are skipped.

    Amavis reinjects each message it scanned into Postfix, which logs a second
    ``cleanup`` line under a fresh queue ID but the same message-id, so
    ``received`` counts distinct message-ids. Postfix synthesises one for the
    rare message that arrives without: only a literal empty ``<>`` escapes the
    deduplication, and it is counted every time rather than collapsing unrelated
    messages into one.
    """
    hours = settings.mailserver_stats_hours
    output = container.run_in_container(
        ["tail", "-n", str(settings.mailserver_stats_log_lines), _MAIL_LOG_PATH],
        timeout=settings.mailserver_command_timeout,
    )

    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(hours=hours)
    stats = MailStats(period_hours=hours, scanned_lines=0)
    seen_message_ids: set[str] = set()
    for line in output.splitlines():
        stats.scanned_lines += 1
        timestamp = _parse_log_timestamp(line, now)
        if timestamp is None or timestamp < cutoff:
            continue
        stats.parsed = True

        # What became of this delivery attempt — one outcome per line.
        if "status=sent" in line:
            stats.sent += 1
        elif "status=deferred" in line:
            stats.deferred += 1
        elif "status=bounced" in line:
            stats.bounced += 1
        elif " reject: " in line or "milter-reject:" in line:
            if _is_greylisted(line):
                stats.greylisted += 1
            else:
                stats.rejected += 1
        elif "postfix/cleanup" in line:
            match = _LOG_MESSAGE_ID_RE.search(line)
            if match and (
                match.group(1) == "<>" or match.group(1) not in seen_message_ids
            ):
                seen_message_ids.add(match.group(1))
                stats.received += 1

        # Why it was refused — a second, independent axis: a rejected spam adds
        # to both ``rejected`` and ``spam``.
        if _LOG_VIRUS_RE.search(line):
            stats.virus += 1
        elif _LOG_SPAM_RE.search(line):
            stats.spam += 1
    return stats


# ── Dovecot master accounts ───────────────────────────────────────────────────


def _split_master(line: str) -> str:
    """Return the master account name from a ``name|hash`` line."""
    return line.partition("|")[0].strip().lower()


def _master_names() -> list[str]:
    """Return every existing Dovecot master account name."""
    return [
        name
        for name in map(_split_master, _read_config_lines(_DOVECOT_MASTERS_FILENAME))
        if name
    ]


def list_dovecot_masters() -> list[DovecotMaster]:
    """Return every Dovecot master account, ordered by name (no passwords)."""
    return [DovecotMaster(name=name) for name in sorted(set(_master_names()))]


def create_dovecot_master(name: str, password: str) -> DovecotMaster:
    """Add a Dovecot master account, rejecting duplicates."""
    username = name.strip().lower()
    if not username or "@" in username:
        raise BadRequestException("A Dovecot master name must not contain '@'")

    lines = _read_config_lines(_DOVECOT_MASTERS_FILENAME)
    if any(_split_master(line) == username for line in lines):
        raise ConflictException(f"Dovecot master {username} already exists")

    lines.append(f"{username}|{hash_dovecot_password(password)}")
    _write_managed(_DOVECOT_MASTERS_FILENAME, lines)
    logger.info("Created Dovecot master account %s", username)
    return DovecotMaster(name=username)


def delete_dovecot_master(name: str) -> None:
    """Remove a Dovecot master account."""
    username = name.strip().lower()
    lines = _read_config_lines(_DOVECOT_MASTERS_FILENAME)
    remaining = [line for line in lines if _split_master(line) != username]
    if len(remaining) == len(lines):
        raise NotFoundException("Dovecot master", username)
    _write_managed(_DOVECOT_MASTERS_FILENAME, remaining)
    logger.info("Deleted Dovecot master account %s", username)


# ── System aliases (postfix-aliases.cf) ───────────────────────────────────────


def _parse_system_alias(line: str) -> tuple[str, list[str]]:
    """Split a ``name: target1, target2`` line into its name and destinations."""
    name, _, raw_targets = line.partition(":")
    targets = [target.strip() for target in raw_targets.split(",") if target.strip()]
    return name.strip().lower(), targets


def list_system_aliases() -> list[SystemAlias]:
    """Return the local aliases appended to ``/etc/aliases``, ordered by name."""
    aliases = [
        SystemAlias(name=name, targets=targets)
        for name, targets in map(
            _parse_system_alias, _read_config_lines(_SYSTEM_ALIASES_FILENAME)
        )
        if name and targets
    ]
    return sorted(aliases, key=lambda alias: alias.name)


def _write_system_aliases(aliases: list[SystemAlias]) -> None:
    """Persist the system aliases, one ``name: t1, t2`` line per entry."""
    _write_managed(
        _SYSTEM_ALIASES_FILENAME,
        [
            f"{alias.name}: {', '.join(alias.targets)}"
            for alias in sorted(aliases, key=lambda alias: alias.name)
        ],
    )


def create_system_alias(name: str, targets: list[str]) -> SystemAlias:
    """Add a local system alias, rejecting duplicates.

    ``name`` is a local name such as ``root`` or ``abuse``: ``/etc/aliases`` maps
    local names only, so an address with a domain would never be matched.
    """
    alias_name = name.strip().lower()
    if not _SYSTEM_ALIAS_NAME_RE.match(alias_name):
        raise BadRequestException(
            f"Invalid alias name: {alias_name!r}. A system alias is a local name "
            "without a domain, e.g. 'root'"
        )
    cleaned = [target.strip() for target in targets if target.strip()]
    if not cleaned:
        raise BadRequestException("A system alias needs at least one destination")

    aliases = list_system_aliases()
    if any(alias.name == alias_name for alias in aliases):
        raise ConflictException(f"The system alias {alias_name} already exists")

    alias = SystemAlias(name=alias_name, targets=cleaned)
    aliases.append(alias)
    _write_system_aliases(aliases)
    logger.info("Added system alias %s -> %s", alias_name, ", ".join(cleaned))
    return alias


def delete_system_alias(name: str) -> None:
    """Remove a local system alias."""
    alias_name = name.strip().lower()
    aliases = list_system_aliases()
    remaining = [alias for alias in aliases if alias.name != alias_name]
    if len(remaining) == len(aliases):
        raise NotFoundException("System alias", alias_name)
    _write_system_aliases(remaining)
    logger.info("Deleted system alias %s", alias_name)


# ── Regex aliases (postfix-regexp.cf) ─────────────────────────────────────────


def _parse_regex_alias(line: str) -> tuple[str, list[str]]:
    """Split a ``/pattern/ target1,target2`` line into its pattern and targets."""
    parts = line.split(None, 1)
    pattern = parts[0].strip()
    targets = (
        [target.strip().lower() for target in parts[1].split(",") if target.strip()]
        if len(parts) > 1
        else []
    )
    return pattern, targets


def list_regex_aliases() -> list[RegexAlias]:
    """Return the PCRE aliases of ``postfix-regexp.cf``, ordered by pattern."""
    aliases = [
        RegexAlias(pattern=pattern, targets=targets)
        for pattern, targets in map(
            _parse_regex_alias, _read_config_lines(_REGEX_ALIASES_FILENAME)
        )
        if pattern and targets
    ]
    return sorted(aliases, key=lambda alias: alias.pattern)


def _write_regex_aliases(aliases: list[RegexAlias]) -> None:
    """Persist the regex aliases, one ``/pattern/\ttarget`` line per entry."""
    _write_managed(
        _REGEX_ALIASES_FILENAME,
        [f"{alias.pattern}\t{','.join(alias.targets)}" for alias in aliases],
    )


def _validate_regex_pattern(pattern: str) -> str:
    """Return the trimmed PCRE pattern, rejecting anything Postfix would not map."""
    cleaned = pattern.strip()
    if not _REGEX_ALIAS_PATTERN_RE.match(cleaned):
        raise BadRequestException(
            f"Invalid pattern: {cleaned!r}. A regex alias is delimited by slashes, "
            "e.g. /^info@example\\.com$/"
        )
    body = cleaned[1 : cleaned.rindex("/")]
    try:
        re.compile(body)
    except re.error as exc:
        raise BadRequestException(f"Invalid regular expression: {exc}") from exc
    return cleaned


def create_regex_alias(pattern: str, targets: list[str]) -> RegexAlias:
    """Add a PCRE alias, rejecting duplicate patterns."""
    cleaned_pattern = _validate_regex_pattern(pattern)
    cleaned_targets = [target.strip().lower() for target in targets if target.strip()]
    if not cleaned_targets:
        raise BadRequestException("A regex alias needs at least one destination")

    aliases = list_regex_aliases()
    if any(alias.pattern == cleaned_pattern for alias in aliases):
        raise ConflictException(f"A regex alias already exists for {cleaned_pattern}")

    alias = RegexAlias(pattern=cleaned_pattern, targets=cleaned_targets)
    aliases.append(alias)
    _write_regex_aliases(aliases)
    logger.info(
        "Added regex alias %s -> %s", cleaned_pattern, ", ".join(cleaned_targets)
    )
    return alias


def delete_regex_alias(pattern: str) -> None:
    """Remove a PCRE alias."""
    cleaned = pattern.strip()
    aliases = list_regex_aliases()
    remaining = [alias for alias in aliases if alias.pattern != cleaned]
    if len(remaining) == len(aliases):
        raise NotFoundException("Regex alias", cleaned)
    _write_regex_aliases(remaining)
    logger.info("Deleted regex alias %s", cleaned)


# ── Global Sieve scripts ──────────────────────────────────────────────────────


def _sieve_filename(scope: str) -> str:
    """Return the Sieve script filename for ``scope`` (``before`` or ``after``)."""
    filename = _SIEVE_FILENAMES.get(scope)
    if filename is None:
        raise BadRequestException("A Sieve scope must be 'before' or 'after'")
    return filename


def get_sieve_script(scope: SieveScope) -> SieveScript:
    """Return the global Sieve script for ``scope`` (empty when absent)."""
    return SieveScript(scope=scope, content=_read_managed_body(_sieve_filename(scope)))


def set_sieve_script(scope: SieveScope, content: str) -> SieveScript:
    """Replace the global Sieve script for ``scope``.

    The script is compiled by ``sievec`` when the mailserver starts, so a syntax
    error surfaces there rather than here.
    """
    body = content.strip()
    _write_managed_body(_sieve_filename(scope), body)
    logger.info("Updated the global '%s' Sieve script (%d bytes)", scope, len(body))
    return SieveScript(scope=scope, content=body)


# ── Spam filter configuration files ───────────────────────────────────────────


def _spam_config_filename(scope: str) -> str:
    """Return the config-volume filename backing the spam config ``scope``."""
    filename = _SPAM_CONFIG_FILENAMES.get(scope)
    if filename is None:
        scopes = ", ".join(sorted(_SPAM_CONFIG_FILENAMES))
        raise BadRequestException(
            f"A spam configuration scope must be one of: {scopes}"
        )
    return filename


def _spam_config_view(scope: SpamConfigScope, content: str) -> SpamConfig:
    """Return the spam-filtering file for ``scope``, next to the toggle guarding it."""
    variable = _SPAM_CONFIG_VARIABLES[scope]
    return SpamConfig(
        scope=scope,
        content=content,
        feature=variable,
        feature_enabled=feature_enabled(variable),
    )


def get_spam_config(scope: SpamConfigScope) -> SpamConfig:
    """Return the spam-filtering file for ``scope`` (empty when absent)."""
    return _spam_config_view(scope, _read_managed_body(_spam_config_filename(scope)))


def set_spam_config(scope: SpamConfigScope, content: str) -> SpamConfig:
    """Replace the spam-filtering file for ``scope``.

    docker-mailserver copies these files out of the config volume when it starts,
    so the mailserver keeps using the previous contents until it is restarted.
    SpamAssassin rules are only validated then, by ``spamassassin --lint``.
    """
    body = content.strip()
    _write_managed_body(_spam_config_filename(scope), body)
    logger.info("Updated the '%s' spam configuration (%d bytes)", scope, len(body))
    return _spam_config_view(scope, body)


# ── Rspamd overrides (custom-commands.conf) ───────────────────────────────────


def _parse_rspamd_command(line: str) -> RspamdCommand | None:
    """Build a :class:`RspamdCommand` from one ``custom-commands.conf`` line.

    Returns ``None`` for a directive this app does not know, or one missing an
    argument: the file may have been written by hand, and a line nobody can map
    back to a form is better dropped from the view than shown mangled.
    """
    head = line.split(None, 1)
    kind, remainder = head[0], head[1] if len(head) > 1 else ""
    fields = _RSPAMD_COMMAND_FIELDS.get(kind)
    if fields is None:
        return None

    # ``value`` is the rest of the line, so it never takes part in the split.
    parts = remainder.split(None, len(fields) - 1)
    if len(parts) != len(fields):
        return None
    return RspamdCommand(
        kind=kind,  # type: ignore[arg-type]  # kind is a key of _RSPAMD_COMMAND_FIELDS
        **dict(zip(fields, (part.strip() for part in parts), strict=True)),
    )


def _format_rspamd_command(command: RspamdCommand) -> str:
    """Render a :class:`RspamdCommand` back to its ``custom-commands.conf`` line."""
    fields = _RSPAMD_COMMAND_FIELDS[command.kind]
    return " ".join([command.kind, *(getattr(command, field) for field in fields)])


def _validate_rspamd_command(command: RspamdCommand) -> RspamdCommand:
    """Return the trimmed command, rejecting names or arguments Rspamd would not take."""
    fields = _RSPAMD_COMMAND_FIELDS[command.kind]
    cleaned = RspamdCommand(
        kind=command.kind,
        **{field: getattr(command, field).strip() for field in fields},
    )

    for field in fields:
        if not getattr(cleaned, field):
            raise BadRequestException(f"{command.kind} requires a non-empty {field}")

    # The value ends the line, so a newline in it would forge a second directive.
    if "\n" in cleaned.value or "\r" in cleaned.value:
        raise BadRequestException("An Rspamd option value must fit on a single line")

    if cleaned.option and not _RSPAMD_NAME_RE.match(cleaned.option):
        raise BadRequestException(f"Invalid Rspamd option name: {cleaned.option!r}")

    if cleaned.target:
        # ``add-line`` targets a file under override.d/, every other a module.
        pattern = _RSPAMD_FILENAME_RE if cleaned.kind == "add-line" else _RSPAMD_NAME_RE
        if not pattern.match(cleaned.target):
            noun = "override file name" if cleaned.kind == "add-line" else "module name"
            raise BadRequestException(f"Invalid Rspamd {noun}: {cleaned.target!r}")
    return cleaned


def get_rspamd_overrides() -> RspamdOverrides:
    """Return the directives of ``rspamd/custom-commands.conf``, in file order."""
    commands = [
        command
        for command in map(
            _parse_rspamd_command, _read_config_lines(_RSPAMD_COMMANDS_FILENAME)
        )
        if command is not None
    ]
    return RspamdOverrides(
        commands=commands,
        rspamd_enabled=_flag(_dms_settings(), "ENABLE_RSPAMD"),
    )


def set_rspamd_overrides(commands: list[RspamdCommand]) -> RspamdOverrides:
    """Replace the full set of Rspamd custom commands, validating each directive.

    Order is preserved and duplicates are kept: ``add-line`` is append-only, so
    two identical lines are two lines.
    """
    cleaned = [_validate_rspamd_command(command) for command in commands]
    _write_managed(
        _RSPAMD_COMMANDS_FILENAME, [_format_rspamd_command(c) for c in cleaned]
    )
    logger.info("Updated %d Rspamd command(s)", len(cleaned))
    return RspamdOverrides(
        commands=cleaned,
        rspamd_enabled=_flag(_dms_settings(), "ENABLE_RSPAMD"),
    )


# ── LDAP provisioner maps ─────────────────────────────────────────────────────


def _ldap_filename(scope: str) -> str:
    """Return the config-volume file name backing the LDAP map ``scope``."""
    filename = _LDAP_FILENAMES.get(scope)
    if filename is None:
        scopes = ", ".join(sorted(_LDAP_FILENAMES))
        raise BadRequestException(f"An LDAP map scope must be one of: {scopes}")
    return filename


def _ldap_file_keys(content: str) -> list[str]:
    """Return the ``key`` of every ``key = value`` line of an LDAP map, in order."""
    keys: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and _LDAP_LINE_RE.match(stripped):
            keys.append(stripped.partition("=")[0].strip().lower())
    return keys


def _ldap_overridden_keys(scope: str, content: str) -> list[str]:
    """Return the keys of this map that the container's environment overwrites.

    At startup docker-mailserver rewrites every ``key = value`` line for which an
    ``LDAP_<KEY>`` variable is exported, and feeds each map its own
    ``LDAP_QUERY_FILTER_<SCOPE>`` as ``query_filter``. A variable left empty is
    treated as unset: ``/etc/dms-settings`` records the defaulted-to-empty ones
    the same way it records those never given, and only an exported variable
    reaches the rewrite.
    """
    variables = _dms_settings()
    filter_variable = _LDAP_QUERY_FILTER_VARIABLES[scope]

    overridden: list[str] = []
    for key in _ldap_file_keys(content):
        variable = filter_variable if key == "query_filter" else f"LDAP_{key.upper()}"
        if variables.get(variable):
            overridden.append(key)
    return overridden


def _ldap_view(scope: LdapScope, content: str) -> LdapConfig:
    """Build the response for an LDAP map from its raw contents."""
    provisioner = _dms_settings().get("ACCOUNT_PROVISIONER", "")
    return LdapConfig(
        scope=scope,
        content=content,
        configured=bool(content),
        provisioner=provisioner,
        ldap_enabled=provisioner.upper() == "LDAP",
        overridden_keys=_ldap_overridden_keys(scope, content),
    )


def get_ldap_config(scope: LdapScope) -> LdapConfig:
    """Return the Postfix LDAP map for ``scope`` (empty when absent).

    The map may hold the LDAP bind password in clear text, exactly as the file on
    disk does; it is returned as-is because an operator cannot edit a file whose
    contents the editor hides from them.
    """
    return _ldap_view(scope, _read_managed_body(_ldap_filename(scope)))


def set_ldap_config(scope: LdapScope, content: str) -> LdapConfig:
    """Replace the Postfix LDAP map for ``scope``; applies once the container restarts.

    An empty map deletes the file rather than leaving a comment-only one behind:
    docker-mailserver would copy that into ``/etc/postfix/`` and point Postfix at
    a map with no ``server_host``, which is worse than falling back to the
    default map it ships.

    Only the ``key = value`` shape is checked here. Postfix parses the map when
    it starts, and an unknown key or a bad LDAP query only surfaces then.
    """
    body = content.strip()
    if not body:
        container.delete_config(_ldap_filename(scope))
        logger.info("Removed the '%s' LDAP map", scope)
        return _ldap_view(scope, "")

    for line in body.splitlines():
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and not _LDAP_LINE_RE.match(stripped)
        ):
            raise BadRequestException(
                f"Invalid LDAP map line: {stripped!r}. Expected 'key = value', "
                "e.g. search_base = ou=people,dc=example,dc=com"
            )

    _write_managed_body(_ldap_filename(scope), body)
    logger.info("Updated the '%s' LDAP map (%d bytes)", scope, len(body))
    return _ldap_view(scope, body)


# ── Postfix mail queue ────────────────────────────────────────────────────────


def _parse_queue_message(entry: dict) -> QueueMessage:
    """Build a :class:`QueueMessage` from one ``postqueue -j`` JSON object."""
    recipients = entry.get("recipients") or []
    arrival = entry.get("arrival_time")
    delay_reason = next(
        (r.get("delay_reason", "") for r in recipients if r.get("delay_reason")),
        "",
    )
    return QueueMessage(
        queue_id=str(entry.get("queue_id", "")),
        queue_name=str(entry.get("queue_name", "")),
        sender=str(entry.get("sender", "")),
        recipients=[str(r.get("address", "")) for r in recipients if r.get("address")],
        message_size=int(entry.get("message_size", 0)),
        arrival_time=datetime.fromtimestamp(arrival, tz=UTC) if arrival else None,
        delay_reason=delay_reason,
    )


def get_queue() -> QueueSummary:
    """Return every message in the Postfix queue, with a count per queue name.

    ``postqueue -j`` prints one JSON object per message and nothing at all when
    the queue is empty.
    """
    output = container.run_in_container(
        ["postqueue", "-j"], timeout=settings.mailserver_command_timeout
    )
    messages: list[QueueMessage] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            messages.append(_parse_queue_message(json.loads(line)))
        except ValueError, TypeError:
            logger.warning("Skipping an unparsable postqueue entry")

    counts: dict[str, int] = {}
    for message in messages:
        counts[message.queue_name] = counts.get(message.queue_name, 0) + 1
    return QueueSummary(messages=messages, counts=counts)


def _validate_queue_id(queue_id: str) -> str:
    """Return the queue ID, rejecting anything ``postsuper`` could misread.

    ``postsuper`` treats ``ALL`` as "every message", so only alphanumeric IDs are
    accepted here and deleting everything goes through :func:`delete_all_queued`.
    """
    cleaned = queue_id.strip()
    if not _QUEUE_ID_RE.match(cleaned) or cleaned == "ALL":
        raise BadRequestException(f"Invalid queue ID: {queue_id!r}")
    return cleaned


def flush_queue() -> QueueActionResult:
    """Ask Postfix to attempt delivery of every deferred message now."""
    output = container.run_in_container(
        ["postqueue", "-f"], timeout=settings.mailserver_command_timeout
    )
    logger.info("Flushed the Postfix queue")
    return QueueActionResult(output=output.strip())


def delete_queued_message(queue_id: str) -> QueueActionResult:
    """Delete a single message from the Postfix queue."""
    cleaned = _validate_queue_id(queue_id)
    output = container.run_in_container(
        ["postsuper", "-d", cleaned], timeout=settings.mailserver_command_timeout
    )
    logger.info("Deleted queued message %s", cleaned)
    return QueueActionResult(output=output.strip())


def delete_all_queued() -> QueueActionResult:
    """Delete every message currently in the Postfix queue."""
    output = container.run_in_container(
        ["postsuper", "-d", "ALL"], timeout=settings.mailserver_command_timeout
    )
    logger.info("Deleted every queued message")
    return QueueActionResult(output=output.strip())


# ── TLS certificate (read-only) ───────────────────────────────────────────────


def _postconf(parameter: str) -> str:
    """Return the effective value of a Postfix ``main.cf`` parameter."""
    return container.run_in_container(
        ["postconf", "-h", parameter], timeout=settings.mailserver_command_timeout
    ).strip()


def _parse_openssl_date(value: str) -> datetime | None:
    """Parse an ``openssl -dateopt iso_8601`` timestamp (``2026-07-09 10:50:07Z``)."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except ValueError:
        logger.warning("Unparsable certificate date: %r", value)
        return None


def _parse_certificate(raw: str) -> dict[str, str]:
    """Return the ``label=value`` pairs printed by ``openssl x509 -noout``."""
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        label, sep, value = line.partition("=")
        if sep:
            fields[label.strip()] = value.strip()
    return fields


def _parse_certificate_domains(raw: str) -> list[str]:
    """Return the DNS names of the certificate's subjectAltName extension."""
    return sorted(
        {
            entry.removeprefix("DNS:").strip()
            for entry in re.findall(r"DNS:[^,\s]+", raw)
            if entry.strip()
        }
    )


def get_tls_certificate() -> TlsCertificate:
    """Return the certificate Postfix serves, or an unconfigured placeholder.

    The path comes from Postfix itself rather than ``SSL_TYPE`` so that whatever
    the mailserver actually presents is what gets reported.
    """
    ssl_type = _dms_settings().get("SSL_TYPE", "")
    cert_path = _postconf("smtpd_tls_cert_file")
    if not cert_path:
        return TlsCertificate(ssl_type=ssl_type, configured=False)

    raw = container.run_in_container(
        [
            "openssl",
            "x509",
            "-in",
            cert_path,
            "-noout",
            "-dateopt",
            "iso_8601",
            "-subject",
            "-issuer",
            "-startdate",
            "-enddate",
            "-ext",
            "subjectAltName",
        ],
        timeout=settings.mailserver_command_timeout,
    )
    fields = _parse_certificate(raw)
    not_after = _parse_openssl_date(fields.get("notAfter", ""))
    return TlsCertificate(
        ssl_type=ssl_type,
        configured=True,
        subject=fields.get("subject", ""),
        issuer=fields.get("issuer", ""),
        not_before=_parse_openssl_date(fields.get("notBefore", "")),
        not_after=not_after,
        days_remaining=(not_after - datetime.now(tz=UTC)).days if not_after else None,
        domains=_parse_certificate_domains(raw),
    )


# ── DNS records ───────────────────────────────────────────────────────────────


def _hosted_domains() -> list[str]:
    """Return every domain the mailserver hosts, from its accounts and DKIM keys."""
    domains = {
        line.partition("|")[0].strip().lower().rpartition("@")[2]
        for line in _read_config_lines(_ACCOUNTS_FILENAME)
    }
    domains.update(key.domain for key in list_dkim_keys())
    return sorted(domain for domain in domains if domain)


def list_dns_records() -> list[DomainDnsRecords]:
    """Return the DNS records to publish for every hosted domain.

    DKIM records are read from the mailserver's generated keys; MX, SPF and DMARC
    are suggestions built from its hostname, and are flagged as such.
    """
    hostname = _postconf("myhostname")
    dkim_by_domain: dict[str, list[DkimKey]] = {}
    for key in list_dkim_keys():
        dkim_by_domain.setdefault(key.domain, []).append(key)

    entries: list[DomainDnsRecords] = []
    for domain in _hosted_domains():
        records = [
            DnsRecord(name=f"{domain}.", type="MX", value=f"10 {hostname}."),
            DnsRecord(name=f"{domain}.", type="TXT", value="v=spf1 mx -all"),
            DnsRecord(
                name=f"_dmarc.{domain}.",
                type="TXT",
                value=f"v=DMARC1; p=none; rua=mailto:postmaster@{domain}; adkim=s; aspf=s",
            ),
        ]
        records += [
            DnsRecord(
                name=key.record_name, type="TXT", value=key.txt_value, suggested=False
            )
            for key in dkim_by_domain.get(domain, [])
        ]
        entries.append(DomainDnsRecords(domain=domain, records=records))
    return entries


# ── Mailserver environment (read-only) ────────────────────────────────────────


def _dms_settings() -> dict[str, str]:
    """Return the ``KEY='value'`` pairs the mailserver wrote to ``/etc/dms-settings``."""
    variables: dict[str, str] = {}
    for line in container.read_file(_DMS_SETTINGS_PATH).splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if key and sep and not key.startswith("#"):
            variables[key] = value.strip().strip("'\"")
    return variables


def _flag(variables: dict[str, str], name: str) -> bool:
    """Return whether the ``ENABLE_*`` toggle ``name`` is on.

    docker-mailserver omits a variable from ``/etc/dms-settings`` only when it
    never defaulted it, so a missing one falls back to the value the mailserver
    would have assumed: ``1`` for the features it ships enabled.
    """
    return variables.get(name, _FEATURE_DEFAULTS.get(name, "0")) == "1"


def feature_enabled(name: str) -> bool:
    """Return whether the container started with the ``ENABLE_*`` toggle ``name`` on.

    Read straight from ``/etc/dms-settings`` so that any service can tell an
    unused configuration file — one docker-mailserver never copies into place —
    from a live one.
    """
    return _flag(_dms_settings(), name)


def dkim_backend() -> str:
    """Return which implementation signs outgoing mail: ``rspamd`` or ``opendkim``.

    The two store their generated keys in different directories, so every DKIM
    read has to pick a side.
    """
    return "rspamd" if _flag(_dms_settings(), "ENABLE_RSPAMD") else "opendkim"


def _spam_filter(variables: dict[str, str]) -> SpamFilter:
    """Return the content filter in charge: ``rspamd``, ``spamassassin`` or ``none``.

    Rspamd wins when both are on: docker-mailserver starts it either way, and it
    is the one that ends up milting the mail.
    """
    if _flag(variables, "ENABLE_RSPAMD"):
        return "rspamd"
    return "spamassassin" if _flag(variables, "ENABLE_SPAMASSASSIN") else "none"


def _environment_warnings(variables: dict[str, str]) -> list[EnvironmentWarning]:
    """Return the contradictions in the environment the container started with.

    docker-mailserver accepts these combinations and silently lets one side win,
    so nothing else surfaces them. Rspamd reimplements the whole Amavis stack:
    running both means two filters, two DKIM signers and two greylists.
    """
    rspamd = _flag(variables, "ENABLE_RSPAMD")
    amavis = _flag(variables, "ENABLE_AMAVIS")
    spamassassin = _flag(variables, "ENABLE_SPAMASSASSIN")
    clamav = _flag(variables, "ENABLE_CLAMAV")
    warnings: list[EnvironmentWarning] = []

    provisioner = variables.get("ACCOUNT_PROVISIONER", "")
    if provisioner.upper() == "LDAP":
        warnings.append(
            EnvironmentWarning(
                level="danger",
                variables=["ACCOUNT_PROVISIONER"],
                message=(
                    "Accounts come from LDAP, so the mailbox, alias and quota pages "
                    "of this UI cannot manage them. Edit the LDAP maps instead."
                ),
            )
        )
    elif provisioner != "FILE":
        warnings.append(
            EnvironmentWarning(
                level="danger",
                variables=["ACCOUNT_PROVISIONER"],
                message=(
                    "This UI writes the account files directly and needs "
                    "ACCOUNT_PROVISIONER=FILE. Mailbox management will not work."
                ),
            )
        )
    if rspamd and spamassassin:
        warnings.append(
            EnvironmentWarning(
                level="danger",
                variables=["ENABLE_RSPAMD", "ENABLE_SPAMASSASSIN"],
                message=(
                    "Rspamd and SpamAssassin both filter incoming mail; running them "
                    "together is unsupported. Disable one of the two."
                ),
            )
        )
    if spamassassin and not amavis:
        warnings.append(
            EnvironmentWarning(
                level="danger",
                variables=["ENABLE_SPAMASSASSIN", "ENABLE_AMAVIS"],
                message=(
                    "SpamAssassin runs inside Amavis. With ENABLE_AMAVIS=0 nothing "
                    "scans incoming mail for spam."
                ),
            )
        )
    if clamav and not amavis and not rspamd:
        warnings.append(
            EnvironmentWarning(
                level="danger",
                variables=["ENABLE_CLAMAV", "ENABLE_AMAVIS"],
                message=(
                    "ClamAV is driven by Amavis or by Rspamd. With both disabled no "
                    "message is ever scanned for viruses."
                ),
            )
        )
    if rspamd and _flag(variables, "ENABLE_OPENDKIM"):
        warnings.append(
            EnvironmentWarning(
                level="warning",
                variables=["ENABLE_RSPAMD", "ENABLE_OPENDKIM"],
                message=(
                    "Rspamd and OpenDKIM both sign outgoing mail, and they store their "
                    "keys apart. This UI reads Rspamd's keys, so any key generated for "
                    "OpenDKIM is invisible here."
                ),
            )
        )
    if rspamd and amavis:
        warnings.append(
            EnvironmentWarning(
                level="warning",
                variables=["ENABLE_RSPAMD", "ENABLE_AMAVIS"],
                message="Rspamd replaces Amavis as the content filter; Amavis is redundant.",
            )
        )
    if rspamd and _flag(variables, "ENABLE_POSTGREY"):
        warnings.append(
            EnvironmentWarning(
                level="warning",
                variables=["ENABLE_RSPAMD", "ENABLE_POSTGREY"],
                message=(
                    "Rspamd greylists on its own through RSPAMD_GREYLISTING; Postgrey "
                    "greylists a second time."
                ),
            )
        )
    if rspamd and _flag(variables, "ENABLE_POLICYD_SPF"):
        warnings.append(
            EnvironmentWarning(
                level="warning",
                variables=["ENABLE_RSPAMD", "ENABLE_POLICYD_SPF"],
                message=(
                    "Rspamd checks SPF itself. docker-mailserver recommends "
                    "ENABLE_POLICYD_SPF=0 alongside it."
                ),
            )
        )
    if _flag(variables, "ENABLE_UPDATE_CHECK") and not variables.get(
        "POSTMASTER_ADDRESS"
    ):
        warnings.append(
            EnvironmentWarning(
                level="warning",
                variables=["ENABLE_UPDATE_CHECK", "POSTMASTER_ADDRESS"],
                message=(
                    "Update notices are mailed to POSTMASTER_ADDRESS, which is unset: "
                    "every check will bounce."
                ),
            )
        )
    # Dangers first: they break a feature, the rest only muddles one.
    return sorted(warnings, key=lambda warning: warning.level != "danger")


def get_environment() -> MailserverEnvironment:
    """Return the mailserver's effective environment (read-only, set at startup).

    ``/etc/dms-settings`` holds the LDAP bind password and the SRS secret next to
    the harmless toggles. Nothing here is editable, so their values are redacted
    rather than echoed back to every administrator who opens the page.
    """
    variables = _dms_settings()
    redacted = {
        name: (_REDACTED if name in _SECRET_VARIABLES and value else value)
        for name, value in variables.items()
    }
    return MailserverEnvironment(
        variables=redacted,
        dkim_backend="rspamd" if _flag(variables, "ENABLE_RSPAMD") else "opendkim",
        global_relay_host=variables.get("DEFAULT_RELAY_HOST")
        or variables.get("RELAY_HOST", ""),
        postmaster_address=variables.get("POSTMASTER_ADDRESS", ""),
        ssl_type=variables.get("SSL_TYPE", ""),
        account_provisioner=variables.get("ACCOUNT_PROVISIONER", ""),
        managesieve_enabled=_flag(variables, "ENABLE_MANAGESIEVE"),
        quotas_enabled=_flag(variables, "ENABLE_QUOTAS"),
        spam_filter=_spam_filter(variables),
        amavis_enabled=_flag(variables, "ENABLE_AMAVIS"),
        clamav_enabled=_flag(variables, "ENABLE_CLAMAV"),
        postgrey_enabled=_flag(variables, "ENABLE_POSTGREY"),
        update_check_enabled=_flag(variables, "ENABLE_UPDATE_CHECK"),
        warnings=_environment_warnings(variables),
    )
