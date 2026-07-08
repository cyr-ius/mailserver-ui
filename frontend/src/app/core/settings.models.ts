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
  user_group_claim: string;
  user_group: string;
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
  user_group_claim: string;
  user_group: string;
  restrict_to_groups: boolean;
  client_secret?: string;
}
