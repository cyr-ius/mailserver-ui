import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField } from '@angular/forms/signals';

import { SettingsService } from '../../../core/settings.service';
import { MailSettings, MailSettingsUpdate } from '../../../core/settings.models';

/** Form shape for the mail page (mirrors MailSettingsUpdate). */
interface MailForm {
  enabled: boolean;
  host: string;
  port: number;
  username: string;
  /** Left empty keeps the stored password unchanged. */
  password: string;
  use_tls: boolean;
  use_ssl: boolean;
  from_address: string;
  recipients: string;
  notify_auth_events: boolean;
  notify_audit_events: boolean;
}

const EMPTY_MAIL: MailForm = {
  enabled: false,
  host: '',
  port: 587,
  username: '',
  password: '',
  use_tls: true,
  use_ssl: false,
  from_address: '',
  recipients: '',
  notify_auth_events: false,
  notify_audit_events: false,
};

/** Outgoing mail (SMTP) connector: notifications and the test message. */
@Component({
  selector: 'app-settings-mail',
  imports: [FormField],
  templateUrl: './mail.html',
  styleUrl: './mail.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Mail {
  private readonly settings = inject(SettingsService);

  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);

  /** Whether an SMTP password is already stored (drives the placeholder). */
  protected readonly passwordStored = signal(false);

  // Test-send state. The result is reported in place: a failure here is a
  // diagnosis, not an error to swallow.
  protected readonly testing = signal(false);
  protected readonly testRecipient = signal('');
  protected readonly testResult = signal<{ sent: boolean; detail: string } | null>(null);

  protected readonly model = signal<MailForm>({ ...EMPTY_MAIL });
  protected readonly mailForm = form(this.model);

  /** Testing an unsaved form would test the *stored* config, which misleads. */
  protected readonly canTest = computed(() => this.model().enabled && !this.saving());

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      const cfg = await this.settings.getMail();
      this.passwordStored.set(cfg.password_set);
      this.model.set(this.toForm(cfg));
    } catch {
      this.loadError.set('Unable to load the mail configuration.');
    } finally {
      this.loading.set(false);
    }
  }

  protected async onSubmit(): Promise<void> {
    this.formError.set(null);
    this.successMessage.set(null);
    this.testResult.set(null);

    const value = this.model();
    if (value.enabled && !value.host.trim()) {
      this.formError.set('An SMTP host is required when the connector is enabled.');
      return;
    }
    if (value.enabled && !value.from_address.trim()) {
      this.formError.set('A sender address is required when the connector is enabled.');
      return;
    }
    if (value.use_tls && value.use_ssl) {
      this.formError.set('Choose either implicit TLS (SSL) or STARTTLS, not both.');
      return;
    }

    this.saving.set(true);
    try {
      const updated = await this.settings.updateMail(this.toPayload(value));
      this.passwordStored.set(updated.password_set);
      this.model.set(this.toForm(updated));
      this.successMessage.set('Mail configuration saved.');
    } catch (err) {
      this.formError.set(this.messageFor(err));
    } finally {
      this.saving.set(false);
    }
  }

  /** Send a test message with the *stored* configuration. */
  protected async onTest(): Promise<void> {
    this.testResult.set(null);
    this.testing.set(true);
    try {
      const result = await this.settings.testMail(this.testRecipient().trim());
      this.testResult.set(result);
    } catch (err) {
      this.testResult.set({ sent: false, detail: this.messageFor(err) });
    } finally {
      this.testing.set(false);
    }
  }

  /** Implicit TLS and STARTTLS are exclusive: turning one on turns the other off. */
  protected onTlsModeChange(mode: 'starttls' | 'ssl' | 'none'): void {
    this.model.update((value) => ({
      ...value,
      use_tls: mode === 'starttls',
      use_ssl: mode === 'ssl',
    }));
  }

  protected readonly tlsMode = computed<'starttls' | 'ssl' | 'none'>(() => {
    const value = this.model();
    if (value.use_ssl) {
      return 'ssl';
    }
    return value.use_tls ? 'starttls' : 'none';
  });

  private toForm(cfg: MailSettings): MailForm {
    return {
      enabled: cfg.enabled,
      host: cfg.host,
      port: cfg.port,
      username: cfg.username,
      password: '',
      use_tls: cfg.use_tls,
      use_ssl: cfg.use_ssl,
      from_address: cfg.from_address,
      recipients: cfg.recipients,
      notify_auth_events: cfg.notify_auth_events,
      notify_audit_events: cfg.notify_audit_events,
    };
  }

  private toPayload(value: MailForm): MailSettingsUpdate {
    const { password, ...rest } = value;
    const payload: MailSettingsUpdate = { ...rest, port: Number(rest.port) };
    // Only send the password when the admin typed a new one.
    if (password.trim()) {
      payload.password = password;
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
