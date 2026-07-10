import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { ApiKey, ApiKeyCreateRequest, ApiKeyCreated } from './api-key.models';

/**
 * Access to the personal API key endpoints. Every call is scoped to the
 * signed-in user: keys can only be issued, listed and revoked by their owner,
 * and only from an interactive session (never with a key itself).
 */
@Injectable({ providedIn: 'root' })
export class ApiKeysService {
  private readonly http = inject(HttpClient);

  /** List the keys owned by the signed-in user. Secrets are never returned. */
  async list(): Promise<ApiKey[]> {
    return firstValueFrom(this.http.get<ApiKey[]>('/api/users/me/api-keys'));
  }

  /** Issue a key. The returned plaintext secret is shown once and never again. */
  async create(name: string, expiresInDays: number | null): Promise<ApiKeyCreated> {
    const body: ApiKeyCreateRequest = { name, expires_in_days: expiresInDays };
    return firstValueFrom(this.http.post<ApiKeyCreated>('/api/users/me/api-keys', body));
  }

  /** Revoke a key: requests presenting it are rejected from then on. */
  async revoke(keyId: number): Promise<void> {
    return firstValueFrom(this.http.delete<void>(`/api/users/me/api-keys/${keyId}`));
  }
}
