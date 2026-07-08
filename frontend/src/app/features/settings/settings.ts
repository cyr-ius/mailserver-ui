import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField } from '@angular/forms/signals';

import { AuthService } from '../../core/auth.service';
import { SettingsService } from '../../core/settings.service';
import { OidcSettings, OidcSettingsUpdate } from '../../core/settings.models';

/** Editable settings tabs. Only OIDC is implemented for now. */
type Tab = 'oidc' | 'syslog' | 'email';

/** Form shape for the OIDC tab (mirrors OidcSettingsUpdate). */
interface OidcForm {
  enabled: boolean;
  issuer: string;
  client_id: string;
  /** Left empty keeps the stored secret unchanged. */
  client_secret: string;
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
}

const EMPTY_OIDC: OidcForm = {
  enabled: false,
  issuer: '',
  client_id: '',
  client_secret: '',
  redirect_uri: '',
  post_logout_redirect_uri: '',
  response_type: 'code',
  scope: 'openid profile email groups',
  oidc_only: false,
  admin_group_claim: '',
  admin_group: '',
  user_group_claim: '',
  user_group: '',
  restrict_to_groups: false,
};

@Component({
  selector: 'app-settings',
  imports: [FormField, RouterLink],
  templateUrl: './settings.html',
  styleUrl: './settings.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Settings {
  private readonly auth = inject(AuthService);
  private readonly settings = inject(SettingsService);
  private readonly router = inject(Router);

  protected readonly user = this.auth.user;
  protected readonly loggingOut = signal(false);

  protected readonly activeTab = signal<Tab>('oidc');

  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);

  /** Whether a client secret is already stored (drives the placeholder). */
  protected readonly secretStored = signal(false);

  protected readonly model = signal<OidcForm>({ ...EMPTY_OIDC });
  protected readonly oidcForm = form(this.model);

  constructor() {
    void this.loadOidc();
  }

  protected setTab(tab: Tab): void {
    this.activeTab.set(tab);
  }

  private async loadOidc(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      const cfg = await this.settings.getOidc();
      this.secretStored.set(cfg.client_secret_set);
      this.model.set(this.toForm(cfg));
    } catch {
      this.loadError.set('Unable to load the OIDC configuration.');
    } finally {
      this.loading.set(false);
    }
  }

  protected async onSubmit(): Promise<void> {
    this.formError.set(null);
    this.successMessage.set(null);

    const value = this.model();
    if (value.enabled && !(value.issuer.trim() && value.client_id.trim())) {
      this.formError.set('Issuer and Client ID are required when OIDC is enabled.');
      return;
    }

    this.saving.set(true);
    try {
      const updated = await this.settings.updateOidc(this.toPayload(value));
      this.secretStored.set(updated.client_secret_set);
      this.model.set(this.toForm(updated));
      this.successMessage.set('OIDC configuration saved.');
    } catch (err) {
      this.formError.set(this.messageFor(err));
    } finally {
      this.saving.set(false);
    }
  }

  protected async onLogout(): Promise<void> {
    this.loggingOut.set(true);
    try {
      await this.auth.logout();
      await this.router.navigate(['/login']);
    } finally {
      this.loggingOut.set(false);
    }
  }

  private toForm(cfg: OidcSettings): OidcForm {
    return {
      enabled: cfg.enabled,
      issuer: cfg.issuer,
      client_id: cfg.client_id,
      client_secret: '',
      redirect_uri: cfg.redirect_uri,
      post_logout_redirect_uri: cfg.post_logout_redirect_uri,
      response_type: cfg.response_type,
      scope: cfg.scope,
      oidc_only: cfg.oidc_only,
      admin_group_claim: cfg.admin_group_claim,
      admin_group: cfg.admin_group,
      user_group_claim: cfg.user_group_claim,
      user_group: cfg.user_group,
      restrict_to_groups: cfg.restrict_to_groups,
    };
  }

  private toPayload(value: OidcForm): OidcSettingsUpdate {
    const { client_secret, ...rest } = value;
    const payload: OidcSettingsUpdate = { ...rest };
    // Only send the secret when the admin typed a new one.
    if (client_secret.trim()) {
      payload.client_secret = client_secret;
    }
    return payload;
  }

  private messageFor(err: unknown): string {
    if (err instanceof HttpErrorResponse && err.status === 400) {
      return typeof err.error?.detail === 'string'
        ? err.error.detail
        : 'The configuration is invalid.';
    }
    return 'Unable to save the configuration. Please try again.';
  }
}
