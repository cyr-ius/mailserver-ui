/** Mail connector configuration as returned by GET /api/settings/mail. */
export interface MailSettings {
  enabled: boolean;
  host: string;
  port: number;
  username: string;
  /** STARTTLS on a plaintext connection (587). Exclusive with `use_ssl`. */
  use_tls: boolean;
  /** Implicit TLS (465). Exclusive with `use_tls`. */
  use_ssl: boolean;
  from_address: string;
  /** Comma-separated recipients of the notifications. */
  recipients: string;
  notify_auth_events: boolean;
  notify_audit_events: boolean;
  /** Whether an SMTP password is stored; the value itself is never returned. */
  password_set: boolean;
}

/**
 * Payload for PUT /api/settings/mail. Leave `password` empty/undefined to keep
 * the stored one unchanged.
 */
export interface MailSettingsUpdate {
  enabled: boolean;
  host: string;
  port: number;
  username: string;
  use_tls: boolean;
  use_ssl: boolean;
  from_address: string;
  recipients: string;
  notify_auth_events: boolean;
  notify_audit_events: boolean;
  password?: string;
}

/** Outcome of POST /api/settings/mail/test. */
export interface MailTestResult {
  sent: boolean;
  detail: string;
}

/** OIDC configuration as returned by GET /api/settings/oidc. */
export interface OidcSettings {
  enabled: boolean;
  issuer: string;
  client_id: string;
  redirect_uri: string;
  post_logout_redirect_uri: string;
  response_type: string;
  scope: string;
  oidc_only: boolean;
  admin_group_claim: string;
  admin_group: string;
  manager_group_claim: string;
  manager_group: string;
  restrict_to_groups: boolean;
  /** Whether a client secret is stored; the value itself is never returned. */
  client_secret_set: boolean;
}

/**
 * Payload for PUT /api/settings/oidc. Every field except `client_secret` is
 * required; leave `client_secret` empty/undefined to keep the stored secret.
 */
export interface OidcSettingsUpdate {
  enabled: boolean;
  issuer: string;
  client_id: string;
  redirect_uri: string;
  post_logout_redirect_uri: string;
  response_type: string;
  scope: string;
  oidc_only: boolean;
  admin_group_claim: string;
  admin_group: string;
  manager_group_claim: string;
  manager_group: string;
  restrict_to_groups: boolean;
  client_secret?: string;
}
