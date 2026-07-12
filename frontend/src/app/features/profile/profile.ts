import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { AuthService } from '../../core/auth.service';
import { PatsService } from '../../core/pats.service';
import { UsersService } from '../../core/users.service';
import { Pat, PatCreated } from '../../core/pat.models';
import { Role, User, roleLabel } from '../../core/auth.models';

const MIN_PASSWORD_LENGTH = 8;

/** Lifetimes offered when issuing a token; `null` never expires. */
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
  private readonly patsService = inject(PatsService);
  private readonly auth = inject(AuthService);

  /** Tokens are hidden when the backend rejects them (PATS_ENABLED=false). */
  protected readonly patsEnabled = this.auth.patsEnabled;

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

  // ── Personal access tokens ─────────────────────────────────────────────────

  protected readonly expiryOptions = EXPIRY_OPTIONS;

  protected readonly pats = signal<Pat[]>([]);
  protected readonly loadingPats = signal(true);
  protected readonly patsError = signal<string | null>(null);

  protected readonly showPatForm = signal(false);
  protected readonly creatingPat = signal(false);
  protected readonly patFormError = signal<string | null>(null);
  protected readonly revokingPatId = signal<number | null>(null);
  protected readonly expiresInDays = signal<number | null>(EXPIRY_OPTIONS[0].days);

  /** The token just issued, shown once: the API never returns its secret again. */
  protected readonly newPat = signal<PatCreated | null>(null);
  /** Whether the secret just issued has been copied to the clipboard. */
  protected readonly copiedSecret = signal(false);

  protected readonly patModel = signal({ name: '' });
  protected readonly patForm = form(this.patModel, (path) => {
    required(path.name, { message: 'A name is required' });
  });

  constructor() {
    void this.loadProfile();
    if (this.patsEnabled()) {
      void this.loadPats();
    }
  }

  /** An expired token stays in the list, greyed out, until its owner revokes it. */
  protected isExpired(pat: Pat): boolean {
    return pat.expires_at !== null && new Date(pat.expires_at) <= new Date();
  }

  protected onExpiryChange(event: Event): void {
    const raw = (event.target as HTMLSelectElement).value;
    this.expiresInDays.set(raw === '' ? null : Number(raw));
  }

  protected startCreatePat(): void {
    this.newPat.set(null);
    this.patFormError.set(null);
    this.patModel.set({ name: '' });
    this.expiresInDays.set(EXPIRY_OPTIONS[0].days);
    this.showPatForm.set(true);
  }

  protected cancelCreatePat(): void {
    this.showPatForm.set(false);
    this.patFormError.set(null);
    this.patModel.set({ name: '' });
  }

  protected createPat(): void {
    this.patFormError.set(null);
    submit(this.patForm, async () => {
      const name = this.patModel().name.trim();
      if (!name) {
        this.patFormError.set('A name is required.');
        return;
      }
      this.creatingPat.set(true);
      try {
        const created = await this.patsService.create(name, this.expiresInDays());
        this.newPat.set(created);
        this.copiedSecret.set(false);
        this.showPatForm.set(false);
        this.patModel.set({ name: '' });
        await this.loadPats();
      } catch (err) {
        this.patFormError.set(this.apiErrorFor(err, 'Unable to create the token.'));
      } finally {
        this.creatingPat.set(false);
      }
    });
  }

  protected async revokePat(pat: Pat): Promise<void> {
    if (!confirm(`Revoke the token "${pat.name}"? Calls using it will stop working.`)) {
      return;
    }
    this.patsError.set(null);
    this.revokingPatId.set(pat.id);
    try {
      await this.patsService.revoke(pat.id);
      if (this.newPat()?.id === pat.id) {
        this.newPat.set(null);
      }
      await this.loadPats();
    } catch (err) {
      this.patsError.set(this.apiErrorFor(err, `Unable to revoke "${pat.name}".`));
    } finally {
      this.revokingPatId.set(null);
    }
  }

  /** Copy the secret of the token just issued. */
  protected async copySecret(): Promise<void> {
    const secret = this.newPat()?.token;
    if (!secret) {
      return;
    }
    try {
      await navigator.clipboard.writeText(secret);
      this.copiedSecret.set(true);
    } catch {
      this.patsError.set('Unable to copy the token. Select it and copy it manually.');
    }
  }

  protected dismissNewPat(): void {
    this.newPat.set(null);
    this.copiedSecret.set(false);
  }

  private async loadPats(): Promise<void> {
    this.loadingPats.set(true);
    try {
      this.pats.set(await this.patsService.list());
    } catch {
      this.patsError.set('Unable to load your access tokens.');
    } finally {
      this.loadingPats.set(false);
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
