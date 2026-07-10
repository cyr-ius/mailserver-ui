"""API schemas for docker-mailserver global configuration.

Unlike mailboxes, these settings are not stored in the application database:
they live in flat files inside the shared docker-mailserver config volume
(``config.MAILSERVER_CONFIG_DIR``):

* ``postfix-relaymap.cf`` / ``postfix-sasl-password.cf`` — SMTP relay
  (smarthost) per sender domain, with optional SASL credentials;
* ``postfix-main.cf`` / ``postfix-master.cf`` — extra Postfix parameters;
* ``dovecot.cf`` — extra Dovecot configuration;
* ``postfix-aliases.cf`` / ``postfix-regexp.cf`` — system and regex aliases;
* ``fail2ban-jail.cf`` — fail2ban ban policy (see :mod:`app.fail2ban_models`);
* ``before.dovecot.sieve`` / ``after.dovecot.sieve`` — global Sieve scripts;
* ``rspamd/custom-commands.conf`` — Rspamd module and worker overrides;
* ``amavis.cf`` — Amavis overrides (see :class:`SpamConfig`);
* ``ldap-{users,groups,aliases,domains}.cf`` — Postfix LDAP maps, read only when
  ``ACCOUNT_PROVISIONER=LDAP``;
* ``opendkim/keys/<domain>/<selector>.txt`` or ``rspamd/dkim/*.public.txt`` —
  generated DKIM public records (key generation requires the container).

Only some of these are picked up live by docker-mailserver's file watcher
(accounts, aliases, relays, quotas, masters). The others are only read when the
mailserver starts, so the schemas that describe them carry a ``restart_required``
flag the UI surfaces. See ``_RESTART_REQUIRED`` in
:mod:`app.services.mailserver_service`.

These Pydantic schemas describe the request/response shapes only; persistence
is handled by :mod:`app.services.mailserver_service`.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RelayHost(BaseModel):
    """An SMTP relay (smarthost) applied to mail from a given sender domain."""

    # Sender key as stored in ``postfix-relaymap.cf``: a domain (``@example.com``)
    # or a full sender address (``user@example.com``).
    sender: str
    host: str
    port: int = 587
    username: str | None = None
    # Whether SASL credentials are stored; the password itself is never returned.
    has_credentials: bool = False


class RelayHostCreate(BaseModel):
    """Request schema for adding an SMTP relay."""

    sender: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1024)


class RelayExclusion(BaseModel):
    """A sender domain opted out of the global relay (``DEFAULT_RELAY_HOST``).

    Stored in ``postfix-relaymap.cf`` as a lone sender key with no relay target,
    which is what ``setup relay exclude-domain`` writes.
    """

    sender: str


class RelayExclusionCreate(BaseModel):
    """Request schema for excluding a sender domain from the global relay."""

    sender: str = Field(min_length=1, max_length=255)


class PostfixOverride(BaseModel):
    """A single ``key = value`` line of ``postfix-main.cf``."""

    key: str = Field(min_length=1, max_length=255)
    value: str = Field(default="", max_length=4096)


class PostfixOverridesUpdate(BaseModel):
    """Request schema replacing the full set of Postfix overrides."""

    overrides: list[PostfixOverride] = Field(default_factory=list)


class PostfixMasterOverride(BaseModel):
    """A single ``service/type/parameter = value`` line of ``postfix-master.cf``.

    docker-mailserver feeds each line to ``postconf -P``, so the key carries the
    service and its type, e.g. ``submission/inet/smtpd_sasl_security_options``.
    """

    key: str = Field(min_length=1, max_length=255)
    value: str = Field(default="", max_length=4096)


class PostfixMasterOverridesUpdate(BaseModel):
    """Request schema replacing the full set of Postfix master overrides."""

    overrides: list[PostfixMasterOverride] = Field(default_factory=list)


class DovecotConfig(BaseModel):
    """The raw contents of ``dovecot.cf``, copied to ``/etc/dovecot/local.conf``."""

    content: str = ""
    # ``dovecot.cf`` is only read when the mailserver starts.
    restart_required: bool = True


class DovecotConfigUpdate(BaseModel):
    """Request schema replacing the whole Dovecot configuration override."""

    content: str = Field(default="", max_length=65536)


class SystemAlias(BaseModel):
    """A local system alias from ``postfix-aliases.cf`` (appended to ``/etc/aliases``).

    Maps a *local* name (``root``, ``abuse``) to one or more destinations.
    """

    name: str
    targets: list[str] = Field(default_factory=list)


class SystemAliasCreate(BaseModel):
    """Request schema for adding or replacing a system alias."""

    name: str = Field(min_length=1, max_length=255)
    targets: list[str] = Field(min_length=1)


class RegexAlias(BaseModel):
    """A PCRE alias from ``postfix-regexp.cf`` (``virtual_alias_maps``)."""

    # A Postfix PCRE pattern including its delimiters, e.g. ``/^info@.*/``.
    pattern: str
    targets: list[str] = Field(default_factory=list)


class RegexAliasCreate(BaseModel):
    """Request schema for adding a regex alias."""

    pattern: str = Field(min_length=1, max_length=1024)
    targets: list[str] = Field(min_length=1)


class DkimKey(BaseModel):
    """A generated DKIM public record (read-only)."""

    domain: str
    selector: str
    # DNS record name to publish, e.g. ``mail._domainkey.example.com.``
    record_name: str
    # The base64 public key (the ``p=`` value of the TXT record).
    public_key: str
    # The full TXT record value, ready to publish (quoted segments joined).
    txt_value: str


class DkimGenerateRequest(BaseModel):
    """Request schema for generating DKIM keys (``setup config dkim``).

    When ``domain`` is omitted, docker-mailserver generates keys for every
    configured domain. Generation runs inside the mailserver container.
    """

    domain: str | None = Field(default=None, max_length=255)
    selector: str = Field(default="mail", min_length=1, max_length=63)
    key_size: Literal[1024, 2048, 4096] = 2048


class Restriction(BaseModel):
    """A send or receive restriction entry (``setup email restrict``)."""

    # Which access map this entry belongs to.
    kind: Literal["send", "receive"]
    # A full address (``user@example.com``) or a domain (``@example.com``).
    address: str


class RestrictionCreate(BaseModel):
    """Request schema for adding a send/receive restriction."""

    address: str = Field(min_length=1, max_length=255)


class MailLog(BaseModel):
    """The trailing lines of the mailserver's mail log (``show-mail-logs``)."""

    lines: list[str] = Field(default_factory=list)


class DovecotMaster(BaseModel):
    """A Dovecot master account (``setup dovecot-master``); no password returned."""

    name: str


class DovecotMasterCreate(BaseModel):
    """Request schema for adding a Dovecot master account."""

    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


# ── Global Sieve scripts ──────────────────────────────────────────────────────


# Which global Sieve script: run before or after the user's own scripts.
SieveScope = Literal["before", "after"]


class SieveScript(BaseModel):
    """A global Sieve script (``before.dovecot.sieve`` / ``after.dovecot.sieve``)."""

    scope: SieveScope
    content: str = ""
    # Global Sieve scripts are compiled when the mailserver starts.
    restart_required: bool = True


class SieveScriptUpdate(BaseModel):
    """Request schema replacing a global Sieve script."""

    content: str = Field(default="", max_length=65536)


# ── Spam filter configuration files ───────────────────────────────────────────


# Which spam-filtering file to edit: custom SpamAssassin rules, the Postgrey
# whitelists that exempt a client or a recipient from greylisting, or the Amavis
# overrides replacing ``/etc/amavis/conf.d/50-user``.
SpamConfigScope = Literal["rules", "whitelist-clients", "whitelist-recipients", "amavis"]


class SpamConfig(BaseModel):
    """A free-form spam-filtering file from the docker-mailserver config volume."""

    scope: SpamConfigScope
    content: str = ""
    # The ``ENABLE_*`` toggle guarding this file, and whether the container
    # started with it on. False means the file is written but never read.
    feature: str = ""
    feature_enabled: bool = False
    # docker-mailserver copies these files into place when it starts, so an edit
    # only takes effect after the container is restarted.
    restart_required: bool = True


class SpamConfigUpdate(BaseModel):
    """Request schema replacing a spam-filtering file."""

    content: str = Field(default="", max_length=65536)


# ── Rspamd overrides ──────────────────────────────────────────────────────────


# The directives ``rspamd/custom-commands.conf`` accepts. Each one writes into a
# file under ``/etc/rspamd/override.d/`` when the mailserver starts:
#
# * ``set-common-option``         — ``options.inc``
# * ``set-option-for-controller`` — ``worker-controller.inc``
# * ``set-option-for-proxy``      — ``worker-proxy.inc``
# * ``enable-module`` / ``disable-module`` / ``set-option-for-module``
#                                 — ``<module>.conf``
# * ``add-line``                  — a verbatim line appended to ``<file>``
RspamdCommandKind = Literal[
    "set-common-option",
    "set-option-for-controller",
    "set-option-for-proxy",
    "enable-module",
    "disable-module",
    "set-option-for-module",
    "add-line",
]


class RspamdCommand(BaseModel):
    """One directive of ``rspamd/custom-commands.conf``.

    The three fields below carry whichever arguments the directive takes; the
    unused ones stay empty. ``target`` is the module name (module directives) or
    the override file name (``add-line``); ``value`` is the option value, or the
    verbatim line for ``add-line``.
    """

    kind: RspamdCommandKind
    target: str = Field(default="", max_length=255)
    option: str = Field(default="", max_length=255)
    value: str = Field(default="", max_length=4096)


class RspamdCommandsUpdate(BaseModel):
    """Request schema replacing the full set of Rspamd commands."""

    commands: list[RspamdCommand] = Field(default_factory=list)


class RspamdOverrides(BaseModel):
    """The Rspamd custom commands, plus whether Rspamd is the active filter."""

    commands: list[RspamdCommand] = Field(default_factory=list)
    # False when ``ENABLE_RSPAMD=0``: the file is written but nothing reads it.
    rspamd_enabled: bool = False
    # ``custom-commands.conf`` is only applied when the mailserver starts.
    restart_required: bool = True


# ── LDAP provisioner maps ─────────────────────────────────────────────────────


# Which Postfix LDAP map to edit. Each one answers a different lookup: the
# mailboxes, the distribution groups, the aliases and the hosted domains.
LdapScope = Literal["users", "groups", "aliases", "domains"]


class LdapConfig(BaseModel):
    """One ``ldap-<scope>.cf`` Postfix LDAP map from the config volume.

    docker-mailserver copies the file to ``/etc/postfix/`` when it starts, then
    overwrites every key for which a matching ``LDAP_<KEY>`` variable is set in
    the container's environment. The keys it would overwrite are listed in
    ``overridden_keys``: whatever this file says about them is discarded.
    """

    scope: LdapScope
    content: str = ""
    # False when no such file exists: docker-mailserver then uses its own default.
    configured: bool = False
    # ``ACCOUNT_PROVISIONER``; these maps are only read when it is ``LDAP``.
    provisioner: str = ""
    ldap_enabled: bool = False
    # Keys of this file the environment overrides at startup, lower-cased.
    overridden_keys: list[str] = Field(default_factory=list)
    restart_required: bool = True


class LdapConfigUpdate(BaseModel):
    """Request schema replacing one Postfix LDAP map."""

    content: str = Field(default="", max_length=65536)


# ── Postfix mail queue ────────────────────────────────────────────────────────


class QueueMessage(BaseModel):
    """A single message sitting in the Postfix queue (``postqueue -j``)."""

    queue_id: str
    # Queue name reported by Postfix: incoming, active, deferred, hold, …
    queue_name: str = ""
    sender: str = ""
    recipients: list[str] = Field(default_factory=list)
    # Message size in bytes.
    message_size: int = 0
    arrival_time: datetime | None = None
    # Why Postfix could not deliver the message yet (deferred queue only).
    delay_reason: str = ""


class QueueSummary(BaseModel):
    """The Postfix queue: every message plus a per-queue count."""

    messages: list[QueueMessage] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class QueueActionResult(BaseModel):
    """Result of a queue action (flush/delete): the raw command output."""

    output: str = ""


# ── TLS certificate ───────────────────────────────────────────────────────────


class TlsCertificate(BaseModel):
    """The TLS certificate Postfix serves, read with ``openssl x509``."""

    # ``SSL_TYPE`` as configured on the mailserver container ("" when disabled).
    ssl_type: str = ""
    # False when no certificate is configured; every field below is then empty.
    configured: bool = False
    subject: str = ""
    issuer: str = ""
    not_before: datetime | None = None
    not_after: datetime | None = None
    # Whole days until expiry; negative once the certificate has expired.
    days_remaining: int | None = None
    # Subject Alternative Names the certificate covers.
    domains: list[str] = Field(default_factory=list)


# ── DNS records ───────────────────────────────────────────────────────────────


class DnsRecord(BaseModel):
    """A DNS record to publish for a hosted domain."""

    name: str
    type: Literal["MX", "TXT", "A", "CNAME"]
    value: str
    # Whether the record is generated from live data (DKIM) or is a suggestion.
    suggested: bool = True


class DomainDnsRecords(BaseModel):
    """Every DNS record to publish for one hosted domain."""

    domain: str
    records: list[DnsRecord] = Field(default_factory=list)


# ── Mailserver environment (read-only) ────────────────────────────────────────


# Which content filter scans incoming mail. Rspamd is a whole stack of its own;
# ``spamassassin`` means SpamAssassin driven by Amavis.
SpamFilter = Literal["rspamd", "spamassassin", "none"]

# How badly a misconfiguration bites: ``danger`` breaks a feature outright,
# ``warning`` is a redundancy or an ambiguity the operator should resolve.
WarningLevel = Literal["danger", "warning"]


class EnvironmentWarning(BaseModel):
    """One inconsistency found in the environment the container started with.

    docker-mailserver accepts environments it cannot honour — Rspamd next to
    SpamAssassin, ClamAV without Amavis to drive it — and simply lets the loser
    sit idle. Nothing reports that, so these checks name the contradiction.
    """

    level: WarningLevel = "warning"
    # The variables the message is about, so the UI can point at them.
    variables: list[str] = Field(default_factory=list)
    message: str


class MailserverEnvironment(BaseModel):
    """The mailserver's effective environment, read from ``/etc/dms-settings``.

    These values are baked in when the container starts and cannot be changed
    from this UI; they are surfaced so the operator can tell why a feature is
    unavailable (for instance a Rspamd DKIM backend, or a global relay host).
    """

    # Every ``KEY='value'`` pair the mailserver wrote at startup, except the ones
    # holding a secret: those are redacted, as nothing here can be changed anyway.
    variables: dict[str, str] = Field(default_factory=dict)
    # Which implementation signs outgoing mail, and therefore where the DKIM
    # keys this app reads are stored.
    dkim_backend: Literal["opendkim", "rspamd"] = "opendkim"
    # ``DEFAULT_RELAY_HOST`` / ``RELAY_HOST``: the relay applied to all senders,
    # configurable only through the container's environment.
    global_relay_host: str = ""
    postmaster_address: str = ""
    ssl_type: str = ""
    account_provisioner: str = ""
    managesieve_enabled: bool = False
    quotas_enabled: bool = False
    # Which content filter is in charge, and the services backing it.
    spam_filter: SpamFilter = "none"
    amavis_enabled: bool = False
    clamav_enabled: bool = False
    postgrey_enabled: bool = False
    update_check_enabled: bool = False
    # Contradictions between the toggles above, worst first.
    warnings: list[EnvironmentWarning] = Field(default_factory=list)


# ── Runtime health (read-only) ────────────────────────────────────────────────


class ServiceStatus(BaseModel):
    """One supervised process inside the mailserver container.

    docker-mailserver supervises every optional feature it ships, so a healthy
    container normally holds a dozen ``STOPPED`` processes — the ones its
    environment left disabled. Only ``failed`` marks a process that tried to run
    and could not, which is why the two flags are not each other's negation.
    """

    name: str
    # The raw supervisor state: RUNNING, STOPPED, FATAL, EXITED, STARTING, …
    state: str
    # True only for RUNNING, so the UI never has to know supervisor's vocabulary.
    running: bool = False
    # True when supervisor gave up on the process: it is broken, not disabled.
    failed: bool = False
    # The detail supervisor prints, e.g. "pid 42, uptime 1:02:03".
    detail: str = ""


class MailStats(BaseModel):
    """Delivery counters parsed from the mail log over a trailing time window.

    The mail log is rotated and this app only reads its tail, so the counters
    describe what the log still holds inside the window — not the mailserver's
    whole history.

    ``sent``/``deferred``/``bounced``/``rejected``/``greylisted`` are the
    mutually exclusive outcomes of one delivery attempt. ``spam`` and ``virus``
    are a separate axis — *why* a message was refused — so a rejected spam is
    counted once in each, and they do not add up with the outcomes.
    """

    # Width of the window the counters cover.
    period_hours: int = 24
    # Distinct messages accepted by Postfix, deduplicated by message-id: Amavis
    # reinjects every message it scanned, which logs a second ``cleanup`` line.
    received: int = 0
    # Deliveries Postfix completed (``status=sent``).
    sent: int = 0
    # Connections Postfix turned away for good: relaying attempts, spam, …
    rejected: int = 0
    # Senders Postgrey (or Rspamd) deferred on purpose, to be retried shortly.
    # Split out of ``rejected``: the mail is not lost, only delayed.
    greylisted: int = 0
    # Deliveries that permanently failed (``status=bounced``).
    bounced: int = 0
    # Deliveries postponed and still to be retried (``status=deferred``).
    deferred: int = 0
    # Messages the content filter marked or blocked as spam.
    spam: int = 0
    # Messages ClamAV found a virus in.
    virus: int = 0
    # False when the log held no line this app could date: every counter is then
    # zero because nothing could be attributed to the window, not because the
    # mailserver was idle.
    parsed: bool = False
    # How many log lines were scanned, so the UI can say the window is truncated.
    scanned_lines: int = 0
