import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import {
  MailSettings,
  MailSettingsUpdate,
  MailTestResult,
  OidcSettings,
  OidcSettingsUpdate,
} from './settings.models';

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

  /** Fetch the current mail connector configuration (password never included). */
  async getMail(): Promise<MailSettings> {
    return firstValueFrom(this.http.get<MailSettings>('/api/settings/mail'));
  }

  /** Persist a new mail connector configuration. */
  async updateMail(payload: MailSettingsUpdate): Promise<MailSettings> {
    return firstValueFrom(this.http.put<MailSettings>('/api/settings/mail', payload));
  }

  /**
   * Send a test message with the stored configuration. Resolves with the outcome
   * rather than rejecting on a delivery failure: diagnosing it is the point.
   */
  async testMail(recipient: string): Promise<MailTestResult> {
    return firstValueFrom(this.http.post<MailTestResult>('/api/settings/mail/test', { recipient }));
  }
}
