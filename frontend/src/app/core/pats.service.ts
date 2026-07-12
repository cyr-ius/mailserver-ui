import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { Pat, PatCreateRequest, PatCreated } from './pat.models';

/**
 * Access to the personal access token endpoints. Every call is scoped to the
 * signed-in user: tokens can only be issued, listed and revoked by their owner,
 * and only from an interactive session (never with a token itself).
 */
@Injectable({ providedIn: 'root' })
export class PatsService {
  private readonly http = inject(HttpClient);

  /** List the tokens owned by the signed-in user. Secrets are never returned. */
  async list(): Promise<Pat[]> {
    return firstValueFrom(this.http.get<Pat[]>('/api/users/me/pats'));
  }

  /** Issue a token. The returned secrets are shown once and never again. */
  async create(name: string, expiresInDays: number | null): Promise<PatCreated> {
    const body: PatCreateRequest = { name, expires_in_days: expiresInDays };
    return firstValueFrom(this.http.post<PatCreated>('/api/users/me/pats', body));
  }

  /** Revoke a token: requests presenting it are rejected from then on. */
  async revoke(patId: number): Promise<void> {
    return firstValueFrom(this.http.delete<void>(`/api/users/me/pats/${patId}`));
  }
}
