/** An SMTP relay (smarthost) as returned by GET /api/mailserver/relays. */
export interface RelayHost {
  /** Sender key: a domain ("@example.com") or a full sender address. */
  sender: string;
  host: string;
  port: number;
  username: string | null;
  /** Whether SASL credentials are stored; the password is never returned. */
  has_credentials: boolean;
}

export interface RelayHostCreateRequest {
  sender: string;
  host: string;
  port: number;
  username?: string | null;
  password?: string | null;
}

/** A sender domain opted out of the global relay (DEFAULT_RELAY_HOST). */
export interface RelayExclusion {
  sender: string;
}

export interface RelayExclusionCreateRequest {
  sender: string;
}

/** A single Postfix main.cf override (key = value). */
export interface PostfixOverride {
  key: string;
  value: string;
}

export interface PostfixOverridesUpdateRequest {
  overrides: PostfixOverride[];
}

/**
 * A single Postfix master.cf override. The key carries the service and its
 * type, e.g. "submission/inet/smtpd_sasl_security_options".
 */
export interface PostfixMasterOverride {
  key: string;
  value: string;
}

export interface PostfixMasterOverridesUpdateRequest {
  overrides: PostfixMasterOverride[];
}

/** The raw dovecot.cf override, copied to /etc/dovecot/local.conf at startup. */
export interface DovecotConfig {
  content: string;
  restart_required: boolean;
}

export interface DovecotConfigUpdateRequest {
  content: string;
}

/** A local system alias from postfix-aliases.cf (appended to /etc/aliases). */
export interface SystemAlias {
  /** A local name without a domain, e.g. "root". */
  name: string;
  targets: string[];
}

export interface SystemAliasCreateRequest {
  name: string;
  targets: string[];
}

/** A PCRE alias from postfix-regexp.cf (virtual_alias_maps). */
export interface RegexAlias {
  /** A Postfix PCRE pattern including its slash delimiters, e.g. "/^info@example\.com$/". */
  pattern: string;
  targets: string[];
}

export interface RegexAliasCreateRequest {
  pattern: string;
  targets: string[];
}

/** A generated DKIM public record (read-only). */
export interface DkimKey {
  domain: string;
  selector: string;
  /** DNS record name to publish, e.g. "mail._domainkey.example.com.". */
  record_name: string;
  /** The base64 public key (the "p=" value). */
  public_key: string;
  /** The full TXT record value, ready to publish. */
  txt_value: string;
}

/** Request to generate DKIM keys (POST /api/mailserver/dkim). */
export interface DkimGenerateRequest {
  /** Optional target domain; when omitted, keys are generated for all domains. */
  domain?: string | null;
  selector: string;
  key_size: 1024 | 2048 | 4096;
}

/** A send or receive restriction kind. */
export type RestrictionKind = 'send' | 'receive';

/** A send/receive restriction entry (setup email restrict). */
export interface Restriction {
  kind: RestrictionKind;
  /** A full address ("user@example.com") or a domain ("@example.com"). */
  address: string;
}

export interface RestrictionCreateRequest {
  address: string;
}

/** The trailing lines of the mailserver mail log. */
export interface MailLog {
  lines: string[];
}

/** A Dovecot master account (no password returned). */
export interface DovecotMaster {
  name: string;
}

export interface DovecotMasterCreateRequest {
  name: string;
  password: string;
}

/** Which global Sieve script: run before or after the user's own scripts. */
export type SieveScope = 'before' | 'after';

/** A global Sieve script (before.dovecot.sieve / after.dovecot.sieve). */
export interface SieveScript {
  scope: SieveScope;
  content: string;
  /** Global Sieve scripts are compiled when the mailserver starts. */
  restart_required: boolean;
}

export interface SieveScriptUpdateRequest {
  content: string;
}

/** A message sitting in the Postfix queue. */
export interface QueueMessage {
  queue_id: string;
  /** incoming, active, deferred, hold, … */
  queue_name: string;
  sender: string;
  recipients: string[];
  message_size: number;
  arrival_time: string | null;
  /** Why Postfix could not deliver the message yet (deferred queue only). */
  delay_reason: string;
}

/** The Postfix queue: every message plus a per-queue count. */
export interface QueueSummary {
  messages: QueueMessage[];
  counts: Record<string, number>;
}

/** Raw command output returned after a queue action. */
export interface QueueActionResult {
  output: string;
}

/** The TLS certificate Postfix serves (read-only). */
export interface TlsCertificate {
  /** SSL_TYPE as configured on the container ("" when TLS is disabled). */
  ssl_type: string;
  /** False when no certificate is configured; every field below is then empty. */
  configured: boolean;
  subject: string;
  issuer: string;
  not_before: string | null;
  not_after: string | null;
  /** Whole days until expiry; negative once the certificate has expired. */
  days_remaining: number | null;
  /** Subject Alternative Names the certificate covers. */
  domains: string[];
}

/** A DNS record to publish for a hosted domain. */
export interface DnsRecord {
  name: string;
  type: 'MX' | 'TXT' | 'A' | 'CNAME';
  value: string;
  /** False for DKIM records, which are read from the mailserver's own keys. */
  suggested: boolean;
}

/** Every DNS record to publish for one hosted domain. */
export interface DomainDnsRecords {
  domain: string;
  records: DnsRecord[];
}

/**
 * The mailserver's effective environment, read from /etc/dms-settings. These
 * values are baked in when the container starts and cannot be changed here.
 */
export interface MailserverEnvironment {
  variables: Record<string, string>;
  /** Which implementation signs outgoing mail, and where its DKIM keys live. */
  dkim_backend: 'opendkim' | 'rspamd';
  /** DEFAULT_RELAY_HOST / RELAY_HOST: the relay applied to every sender. */
  global_relay_host: string;
  postmaster_address: string;
  ssl_type: string;
  account_provisioner: string;
  managesieve_enabled: boolean;
  quotas_enabled: boolean;
}

/**
 * One supervised process inside the mailserver container. A healthy container
 * normally holds many STOPPED processes — the features its environment left
 * disabled — so `failed` is not the negation of `running`.
 */
export interface ServiceStatus {
  name: string;
  /** The raw supervisor state: RUNNING, STOPPED, FATAL, EXITED, STARTING, … */
  state: string;
  /** True only for RUNNING. */
  running: boolean;
  /** True when supervisor gave up on the process: broken, as opposed to disabled. */
  failed: boolean;
  /** What supervisor prints next to the state, e.g. "pid 42, uptime 1:02:03". */
  detail: string;
}

/** Delivery counters parsed from the mail log over a trailing time window. */
export interface MailStats {
  period_hours: number;
  received: number;
  sent: number;
  rejected: number;
  bounced: number;
  deferred: number;
  /** False when no log line could be dated: the counters are then meaningless. */
  parsed: boolean;
  /** Lines scanned; a full scan means the window may be truncated. */
  scanned_lines: number;
}
