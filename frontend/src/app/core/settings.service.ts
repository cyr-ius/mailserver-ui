import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { OidcSettings, OidcSettingsUpdate } from './settings.models';

/**
 * Access to the application settings API (admin only). Stateless: callers own
 * the resulting data; the service just wraps the HTTP calls.
 */
@Injectable({ providedIn: 'root' })
export class SettingsService {
  private readonly http = inject(HttpClient);

  /** Fetch the current OIDC configuration (secret never included). */
  async getOidc(): Promise<OidcSettings> {
    return firstValueFrom(this.http.get<OidcSettings>('/api/settings/oidc'));
  }

  /** Persist a new OIDC configuration. */
  async updateOidc(payload: OidcSettingsUpdate): Promise<OidcSettings> {
    return firstValueFrom(this.http.put<OidcSettings>('/api/settings/oidc', payload));
  }
}
