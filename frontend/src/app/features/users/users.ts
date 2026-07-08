import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { AuthService } from '../../core/auth.service';
import { UsersService } from '../../core/users.service';
import { User } from '../../core/auth.models';

const MIN_PASSWORD_LENGTH = 8;

@Component({
  selector: 'app-users',
  imports: [FormField, RouterLink, DatePipe],
  templateUrl: './users.html',
  styleUrl: './users.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Users {
  private readonly auth = inject(AuthService);
  private readonly usersService = inject(UsersService);
  private readonly router = inject(Router);

  protected readonly currentUser = this.auth.user;
  protected readonly users = signal<User[]>([]);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly loggingOut = signal(false);

  /** Id of the local user whose password is being edited, or null. */
  protected readonly editingId = signal<number | null>(null);
  protected readonly saving = signal(false);
  protected readonly formError = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);

  protected readonly model = signal({ password: '', confirm: '' });
  protected readonly passwordForm = form(this.model, (path) => {
    required(path.password, { message: 'A password is required' });
    required(path.confirm, { message: 'Please confirm the password' });
  });

  protected readonly minLength = MIN_PASSWORD_LENGTH;

  protected readonly editingUser = computed(
    () => this.users().find((u) => u.id === this.editingId()) ?? null,
  );

  constructor() {
    void this.loadUsers();
  }

  private async loadUsers(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      this.users.set(await this.usersService.list());
    } catch {
      this.loadError.set('Unable to load users.');
    } finally {
      this.loading.set(false);
    }
  }

  protected startEdit(user: User): void {
    this.editingId.set(user.id);
    this.formError.set(null);
    this.successMessage.set(null);
    this.model.set({ password: '', confirm: '' });
  }

  protected cancelEdit(): void {
    this.editingId.set(null);
    this.formError.set(null);
  }

  protected onSubmit(): void {
    this.formError.set(null);
    this.successMessage.set(null);
    submit(this.passwordForm, async () => {
      const { password, confirm } = this.model();
      if (password.length < MIN_PASSWORD_LENGTH) {
        this.formError.set(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
        return;
      }
      if (password !== confirm) {
        this.formError.set('Passwords do not match.');
        return;
      }
      const target = this.editingUser();
      if (!target) {
        return;
      }
      this.saving.set(true);
      try {
        await this.usersService.changePassword(target.id, password);
        this.successMessage.set(`Password updated for ${target.username}.`);
        this.editingId.set(null);
      } catch (err) {
        this.formError.set(this.messageFor(err));
      } finally {
        this.saving.set(false);
      }
    });
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
        return 'This account is managed by the identity provider.';
      }
      if (err.status === 422) {
        return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
      }
    }
    return 'Unable to update the password. Please try again.';
  }
}
