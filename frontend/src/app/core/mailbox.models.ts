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

/** An alias address forwarding to a mailbox. */
export interface Alias {
  alias: string;
}

export interface AliasCreateRequest {
  alias: string;
}
