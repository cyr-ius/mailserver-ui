import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { AuthService } from '../../core/auth.service';
import { MailboxesService } from '../../core/mailboxes.service';
import { Alias, Mailbox } from '../../core/mailbox.models';

const MIN_PASSWORD_LENGTH = 8;
const QUOTA_PATTERN = /^\d+[KMGT]$/;

@Component({
  selector: 'app-mailboxes',
  imports: [FormField],
  templateUrl: './mailboxes.html',
  styleUrl: './mailboxes.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Mailboxes {
  private readonly auth = inject(AuthService);
  private readonly mailboxesService = inject(MailboxesService);
  private readonly router = inject(Router);

  protected readonly currentUser = this.auth.user;
  protected readonly mailboxes = signal<Mailbox[]>([]);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly loggingOut = signal(false);

  protected readonly successMessage = signal<string | null>(null);
  protected readonly minLength = MIN_PASSWORD_LENGTH;

  // ── Create mailbox form ─────────────────────────────────────────────────────
  protected readonly creating = signal(false);
  protected readonly createError = signal<string | null>(null);
  protected readonly createModel = signal({ email: '', password: '', confirm: '', quota: '' });
  protected readonly createForm = form(this.createModel, (path) => {
    required(path.email, { message: 'An email address is required' });
    required(path.password, { message: 'A password is required' });
    required(path.confirm, { message: 'Please confirm the password' });
  });

  /** Email of the mailbox whose management panel is open, or null. */
  protected readonly managingEmail = signal<string | null>(null);

  // ── Reset password ──────────────────────────────────────────────────────────
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly pwModel = signal({ password: '', confirm: '' });
  protected readonly passwordForm = form(this.pwModel, (path) => {
    required(path.password, { message: 'A password is required' });
    required(path.confirm, { message: 'Please confirm the password' });
  });

  // ── Quota ───────────────────────────────────────────────────────────────────
  protected readonly quotaValue = signal('');
  protected readonly savingQuota = signal(false);
  protected readonly quotaError = signal<string | null>(null);

  // ── Aliases ─────────────────────────────────────────────────────────────────
  protected readonly aliases = signal<Alias[]>([]);
  protected readonly aliasesLoading = signal(false);
  protected readonly aliasError = signal<string | null>(null);
  protected readonly addingAlias = signal(false);
  protected readonly removingAlias = signal<string | null>(null);
  protected readonly aliasModel = signal({ alias: '' });
  protected readonly aliasForm = form(this.aliasModel, (path) => {
    required(path.alias, { message: 'An alias address is required' });
  });

  /** Email of the mailbox being deleted, or null (drives the row spinner). */
  protected readonly deletingEmail = signal<string | null>(null);

  constructor() {
    void this.loadMailboxes();
  }

  private async loadMailboxes(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      this.mailboxes.set(await this.mailboxesService.list());
    } catch {
      this.loadError.set('Unable to load mailboxes.');
    } finally {
      this.loading.set(false);
    }
  }

  // ── Create ──────────────────────────────────────────────────────────────────

  protected onCreate(): void {
    this.createError.set(null);
    this.successMessage.set(null);
    submit(this.createForm, async () => {
      const { email, password, confirm, quota } = this.createModel();
      if (password.length < MIN_PASSWORD_LENGTH) {
        this.createError.set(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
        return;
      }
      if (password !== confirm) {
        this.createError.set('Passwords do not match.');
        return;
      }
      const cleanQuota = quota.trim().toUpperCase();
      if (cleanQuota && !QUOTA_PATTERN.test(cleanQuota)) {
        this.createError.set('Quota must be a number followed by K, M, G or T (e.g. 5G).');
        return;
      }
      const address = email.trim().toLowerCase();
      this.creating.set(true);
      try {
        await this.mailboxesService.create(address, password, cleanQuota || null);
        this.successMessage.set(`Mailbox ${address} created.`);
        this.createModel.set({ email: '', password: '', confirm: '', quota: '' });
        await this.loadMailboxes();
      } catch (err) {
        this.createError.set(this.messageFor(err));
      } finally {
        this.creating.set(false);
      }
    });
  }

  // ── Manage panel ────────────────────────────────────────────────────────────

  protected async toggleManage(mailbox: Mailbox): Promise<void> {
    if (this.managingEmail() === mailbox.email) {
      this.managingEmail.set(null);
      return;
    }
    this.managingEmail.set(mailbox.email);
    this.formError.set(null);
    this.quotaError.set(null);
    this.aliasError.set(null);
    this.successMessage.set(null);
    this.pwModel.set({ password: '', confirm: '' });
    this.aliasModel.set({ alias: '' });
    this.quotaValue.set(mailbox.quota ?? '');
    await this.loadAliases(mailbox.email);
  }

  // ── Reset password ──────────────────────────────────────────────────────────

  protected onResetPassword(): void {
    this.formError.set(null);
    this.successMessage.set(null);
    submit(this.passwordForm, async () => {
      const { password, confirm } = this.pwModel();
      const email = this.managingEmail();
      if (!email) {
        return;
      }
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
        await this.mailboxesService.resetPassword(email, password);
        this.successMessage.set(`Password updated for ${email}.`);
        this.pwModel.set({ password: '', confirm: '' });
      } catch (err) {
        this.formError.set(this.messageFor(err));
      } finally {
        this.saving.set(false);
      }
    });
  }

  // ── Quota ───────────────────────────────────────────────────────────────────

  protected async onSaveQuota(): Promise<void> {
    const email = this.managingEmail();
    if (!email) {
      return;
    }
    const value = this.quotaValue().trim().toUpperCase();
    if (value && !QUOTA_PATTERN.test(value)) {
      this.quotaError.set('Quota must be a number followed by K, M, G or T (e.g. 5G).');
      return;
    }
    this.quotaError.set(null);
    this.successMessage.set(null);
    this.savingQuota.set(true);
    try {
      await this.mailboxesService.setQuota(email, value || null);
      this.successMessage.set(
        value ? `Quota set to ${value} for ${email}.` : `Quota cleared for ${email}.`,
      );
      await this.loadMailboxes();
    } catch (err) {
      this.quotaError.set(this.messageFor(err));
    } finally {
      this.savingQuota.set(false);
    }
  }

  // ── Aliases ─────────────────────────────────────────────────────────────────

  private async loadAliases(email: string): Promise<void> {
    this.aliasesLoading.set(true);
    this.aliases.set([]);
    try {
      this.aliases.set(await this.mailboxesService.listAliases(email));
    } catch {
      this.aliasError.set('Unable to load aliases.');
    } finally {
      this.aliasesLoading.set(false);
    }
  }

  protected onAddAlias(): void {
    this.aliasError.set(null);
    submit(this.aliasForm, async () => {
      const email = this.managingEmail();
      const alias = this.aliasModel().alias.trim().toLowerCase();
      if (!email || !alias) {
        return;
      }
      this.addingAlias.set(true);
      try {
        await this.mailboxesService.addAlias(email, alias);
        this.aliasModel.set({ alias: '' });
        await this.loadAliases(email);
      } catch (err) {
        this.aliasError.set(this.messageFor(err));
      } finally {
        this.addingAlias.set(false);
      }
    });
  }

  protected async onRemoveAlias(alias: string): Promise<void> {
    const email = this.managingEmail();
    if (!email) {
      return;
    }
    this.aliasError.set(null);
    this.removingAlias.set(alias);
    try {
      await this.mailboxesService.deleteAlias(email, alias);
      await this.loadAliases(email);
    } catch (err) {
      this.aliasError.set(this.messageFor(err));
    } finally {
      this.removingAlias.set(null);
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────────

  protected async onDelete(mailbox: Mailbox): Promise<void> {
    if (!confirm(`Delete mailbox ${mailbox.email}? The stored mail is left on disk.`)) {
      return;
    }
    this.successMessage.set(null);
    this.loadError.set(null);
    this.deletingEmail.set(mailbox.email);
    try {
      await this.mailboxesService.delete(mailbox.email);
      if (this.managingEmail() === mailbox.email) {
        this.managingEmail.set(null);
      }
      this.successMessage.set(`Mailbox ${mailbox.email} deleted.`);
      await this.loadMailboxes();
    } catch (err) {
      this.loadError.set(this.messageFor(err));
    } finally {
      this.deletingEmail.set(null);
    }
  }

  // ── Misc ────────────────────────────────────────────────────────────────────

  protected onQuotaInput(event: Event): void {
    this.quotaValue.set((event.target as HTMLInputElement).value);
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

  private messageFor(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 409) {
        return 'This address is already in use (mailbox or alias).';
      }
      if (err.status === 404) {
        return 'This mailbox or alias no longer exists.';
      }
      if (err.status === 400) {
        return 'Invalid request. Check the address and the mailserver config volume.';
      }
      if (err.status === 422) {
        return 'Invalid input. Check the email, password (min 8 chars) and quota format.';
      }
    }
    return 'Something went wrong. Please try again.';
  }
}
