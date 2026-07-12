/** A personal access token, as returned by /api/users/me/pats. Never carries a secret. */
export interface Pat {
  id: number;
  name: string;
  /** Masked token (`AbCd…Wx12`), enough to tell two tokens apart. */
  token_hint: string;
  created_at: string;
  /** Null when the token never expires. */
  expires_at: string | null;
  last_used_at: string | null;
}

/** Creation response: the only time the plaintext secret is returned by the API. */
export interface PatCreated extends Pat {
  /** The token, `pat_`-prefixed, sent as `Authorization: Bearer`. */
  token: string;
}

/** Payload issuing a token. A null `expires_in_days` issues one that never expires. */
export interface PatCreateRequest {
  name: string;
  expires_in_days: number | null;
}
