import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { ApiKeysService } from '../../core/api-keys.service';
import { AuthService } from '../../core/auth.service';
import { UsersService } from '../../core/users.service';
import { API_KEY_HEADER, ApiKey, ApiKeyCreated } from '../../core/api-key.models';
import { Role, User, roleLabel } from '../../core/auth.models';

const MIN_PASSWORD_LENGTH = 8;

/** Lifetimes offered when issuing a key; `null` never expires. */
const EXPIRY_OPTIONS: readonly { readonly label: string; readonly days: number | null }[] = [
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
  { label: '1 year', days: 365 },
  { label: 'Never', days: null },
];

/** Bootstrap contextual colour per role, most privileged first in the UI. */
const ROLE_BADGE: Record<Role, string> = {
  admin: 'text-bg-danger',
  mailbox_manager: 'text-bg-primary',
  guest: 'text-bg-secondary',
};

/** Self-service page: account details and password rotation for the current user. */
@Component({
  selector: 'app-profile',
  imports: [FormField, DatePipe],
  templateUrl: './profile.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Profile {
  private readonly usersService = inject(UsersService);
  private readonly apiKeysService = inject(ApiKeysService);
  private readonly auth = inject(AuthService);

  /** API keys are hidden when the backend rejects them (API_KEYS_ENABLED=false). */
  protected readonly apiKeysEnabled = this.auth.apiKeysEnabled;

  protected readonly profile = signal<User | null>(null);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);

  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);

  protected readonly minLength = MIN_PASSWORD_LENGTH;
  protected readonly roleLabel = roleLabel;

  /** The password form is useless for accounts whose credentials live in the IdP. */
  protected readonly isLocalAccount = computed(() => this.profile()?.provider === 'local');

  protected readonly model = signal({ current: '', password: '', confirm: '' });
  protected readonly passwordForm = form(this.model, (path) => {
    required(path.current, { message: 'Your current password is required' });
    required(path.password, { message: 'A new password is required' });
    required(path.confirm, { message: 'Please confirm the new password' });
  });

  // ── Personal API keys ──────────────────────────────────────────────────────

  protected readonly apiKeyHeader = API_KEY_HEADER;
  protected readonly expiryOptions = EXPIRY_OPTIONS;

  protected readonly apiKeys = signal<ApiKey[]>([]);
  protected readonly loadingKeys = signal(true);
  protected readonly keysError = signal<string | null>(null);

  protected readonly showKeyForm = signal(false);
  protected readonly creatingKey = signal(false);
  protected readonly keyFormError = signal<string | null>(null);
  protected readonly revokingKeyId = signal<number | null>(null);
  protected readonly expiresInDays = signal<number | null>(EXPIRY_OPTIONS[0].days);

  /** The key just issued, shown once: the API never returns its secret again. */
  protected readonly newKey = signal<ApiKeyCreated | null>(null);
  protected readonly keyCopied = signal(false);

  protected readonly keyModel = signal({ name: '' });
  protected readonly keyForm = form(this.keyModel, (path) => {
    required(path.name, { message: 'A name is required' });
  });

  constructor() {
    void this.loadProfile();
    if (this.apiKeysEnabled()) {
      void this.loadApiKeys();
    }
  }

  /** An expired key is kept in the list, greyed out, until its owner revokes it. */
  protected isExpired(key: ApiKey): boolean {
    return key.expires_at !== null && new Date(key.expires_at) <= new Date();
  }

  protected onExpiryChange(event: Event): void {
    const raw = (event.target as HTMLSelectElement).value;
    this.expiresInDays.set(raw === '' ? null : Number(raw));
  }

  protected startCreateKey(): void {
    this.newKey.set(null);
    this.keyFormError.set(null);
    this.keyModel.set({ name: '' });
    this.expiresInDays.set(EXPIRY_OPTIONS[0].days);
    this.showKeyForm.set(true);
  }

  protected cancelCreateKey(): void {
    this.showKeyForm.set(false);
    this.keyFormError.set(null);
    this.keyModel.set({ name: '' });
  }

  protected createKey(): void {
    this.keyFormError.set(null);
    submit(this.keyForm, async () => {
      const name = this.keyModel().name.trim();
      if (!name) {
        this.keyFormError.set('A name is required.');
        return;
      }
      this.creatingKey.set(true);
      try {
        const created = await this.apiKeysService.create(name, this.expiresInDays());
        this.newKey.set(created);
        this.keyCopied.set(false);
        this.showKeyForm.set(false);
        this.keyModel.set({ name: '' });
        await this.loadApiKeys();
      } catch (err) {
        this.keyFormError.set(this.apiErrorFor(err, 'Unable to create the API key.'));
      } finally {
        this.creatingKey.set(false);
      }
    });
  }

  protected async revokeKey(key: ApiKey): Promise<void> {
    if (!confirm(`Revoke the API key "${key.name}"? Calls using it will stop working.`)) {
      return;
    }
    this.keysError.set(null);
    this.revokingKeyId.set(key.id);
    try {
      await this.apiKeysService.revoke(key.id);
      if (this.newKey()?.id === key.id) {
        this.newKey.set(null);
      }
      await this.loadApiKeys();
    } catch (err) {
      this.keysError.set(this.apiErrorFor(err, `Unable to revoke "${key.name}".`));
    } finally {
      this.revokingKeyId.set(null);
    }
  }

  protected async copyKey(): Promise<void> {
    const secret = this.newKey()?.key;
    if (!secret) {
      return;
    }
    try {
      await navigator.clipboard.writeText(secret);
      this.keyCopied.set(true);
    } catch {
      this.keysError.set('Unable to copy the key. Select it and copy it manually.');
    }
  }

  protected dismissNewKey(): void {
    this.newKey.set(null);
    this.keyCopied.set(false);
  }

  private async loadApiKeys(): Promise<void> {
    this.loadingKeys.set(true);
    try {
      this.apiKeys.set(await this.apiKeysService.list());
    } catch {
      this.keysError.set('Unable to load your API keys.');
    } finally {
      this.loadingKeys.set(false);
    }
  }

  protected roleBadge(role: Role): string {
    return ROLE_BADGE[role] ?? 'text-bg-secondary';
  }

  private async loadProfile(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      this.profile.set(await this.usersService.me());
    } catch {
      this.loadError.set('Unable to load your profile.');
    } finally {
      this.loading.set(false);
    }
  }

  protected onSubmit(): void {
    this.formError.set(null);
    this.successMessage.set(null);
    submit(this.passwordForm, async () => {
      const { current, password, confirm } = this.model();
      if (password.length < MIN_PASSWORD_LENGTH) {
        this.formError.set(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
        return;
      }
      if (password !== confirm) {
        this.formError.set('Passwords do not match.');
        return;
      }
      this.saving.set(true);
      try {
        await this.usersService.changeOwnPassword(current, password);
        this.successMessage.set('Your password has been updated.');
        this.model.set({ current: '', password: '', confirm: '' });
      } catch (err) {
        this.formError.set(this.messageFor(err));
      } finally {
        this.saving.set(false);
      }
    });
  }

  private messageFor(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      const detail: unknown = err.error?.detail;
      if (typeof detail === 'string' && detail) {
        return detail;
      }
      if (err.status === 422) {
        return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
      }
    }
    return 'Unable to update the password. Please try again.';
  }

  /** Surfaces the API `detail` when there is one, otherwise a caller-supplied fallback. */
  private apiErrorFor(err: unknown, fallback: string): string {
    if (err instanceof HttpErrorResponse) {
      const detail: unknown = err.error?.detail;
      if (typeof detail === 'string' && detail) {
        return detail;
      }
    }
    return fallback;
  }
}
