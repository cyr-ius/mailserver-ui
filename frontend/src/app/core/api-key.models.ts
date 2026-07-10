/** Header carrying a personal API key on REST calls. */
export const API_KEY_HEADER = 'X-API-Key';

/** A personal API key, as returned by /api/users/me/api-keys. Never carries the secret. */
export interface ApiKey {
  id: number;
  name: string;
  /** Leading characters of the key, enough to tell two keys apart. */
  prefix: string;
  created_at: string;
  /** Null when the key never expires. */
  expires_at: string | null;
  last_used_at: string | null;
}

/** Creation response: the only time the plaintext key is returned by the API. */
export interface ApiKeyCreated extends ApiKey {
  key: string;
}

/** Payload issuing a key. A null `expires_in_days` issues a key that never expires. */
export interface ApiKeyCreateRequest {
  name: string;
  expires_in_days: number | null;
}
