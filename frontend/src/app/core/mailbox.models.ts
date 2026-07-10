/** A docker-mailserver mail account, as returned by /api/mailboxes. */
export interface Mailbox {
  email: string;
  domain: string;
  /** Dovecot quota (e.g. "5G"), or null when unlimited. */
  quota: string | null;
}

export interface MailboxCreateRequest {
  email: string;
  password: string;
  /** Optional quota (e.g. "5G"); omitted/empty means unlimited. */
  quota?: string | null;
}

export interface MailboxPasswordUpdateRequest {
  new_password: string;
}

export interface QuotaUpdateRequest {
  /** Quota (e.g. "5G"); null clears any existing limit. */
  quota: string | null;
}

/**
 * How much disk a mail account really occupies, as returned by
 * /api/mailboxes/usage. Distinct from `Mailbox.quota`, which is the configured
 * limit rather than the storage consumed.
 */
export interface MailboxUsage {
  email: string;
  used_bytes: number;
  /** The storage limit in bytes, or null when unlimited. */
  limit_bytes: number | null;
  /** Percentage of the limit consumed, or null when unlimited. */
  percent: number | null;
  message_count: number;
}

/** Disk usage of every mail account, ordered by usage, plus the totals. */
export interface MailboxUsageSummary {
  mailboxes: MailboxUsage[];
  total_used_bytes: number;
  /** Null as soon as one account is unlimited. */
  total_limit_bytes: number | null;
}

/** An alias address forwarding to a mailbox. */
export interface Alias {
  alias: string;
}

export interface AliasCreateRequest {
  alias: string;
}

/** The personal Sieve filter of one account (<email>.dovecot.sieve). */
export interface MailboxSieveScript {
  email: string;
  content: string;
  /** False when the account has no personal script yet. */
  configured: boolean;
  /** The script is compiled into the maildir when the mailserver starts. */
  restart_required: boolean;
}

export interface MailboxSieveScriptUpdateRequest {
  content: string;
}
