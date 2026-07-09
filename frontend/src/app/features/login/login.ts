import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField, required, submit } from '@angular/forms/signals';
import { CommonModule } from '@angular/common';

import { AuthService } from '../../core/auth.service';
import { ThemeService, ThemeMode } from '../../core/theme.service';

@Component({
  selector: 'app-login',
  imports: [FormField, CommonModule],
  templateUrl: './login.html',
  styleUrl: './login.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  protected readonly theme = inject(ThemeService);

  /** Which login methods the backend exposes. */
  protected readonly config = this.auth.config;
  protected readonly loadingConfig = signal(true);
  protected readonly submitting = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly model = signal({ username: '', password: '' });
  protected readonly loginForm = form(this.model, (path) => {
    required(path.username, { message: 'Username is required' });
    required(path.password, { message: 'Password is required' });
  });

  protected readonly themeModes: ThemeMode[] = ['light', 'dark', 'auto'];

  constructor() {
    this.readOidcError();
    void this.loadConfig();
  }

  private async loadConfig(): Promise<void> {
    try {
      await this.auth.loadConfig();
    } catch {
      this.error.set('Unable to load authentication configuration.');
    } finally {
      this.loadingConfig.set(false);
    }
  }

  /** Surface an error passed back by the OIDC redirect (?error=...). */
  private readOidcError(): void {
    const reason = new URLSearchParams(window.location.search).get('error');
    if (!reason) {
      return;
    }
    const messages: Record<string, string> = {
      oidc: 'OIDC sign-in failed. Please try again.',
      state: 'OIDC session expired. Please retry.',
      forbidden: 'Your account is not allowed to access this application.',
    };
    this.error.set(messages[reason] ?? 'Sign-in failed.');
  }

  protected onSubmit(): void {
    this.error.set(null);
    submit(this.loginForm, async () => {
      this.submitting.set(true);
      try {
        await this.auth.login(this.model());
        await this.router.navigate(['/dashboard']);
      } catch (err) {
        this.error.set(this.messageFor(err));
      } finally {
        this.submitting.set(false);
      }
    });
  }

  protected onOidcLogin(): void {
    this.auth.loginWithOidc();
  }

  protected onThemeChange(mode: ThemeMode): void {
    this.theme.setThemeMode(mode);
  }

  private messageFor(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 401) {
        return 'Invalid username or password.';
      }
      if (err.status === 429) {
        return 'Too many attempts. Please try again later.';
      }
    }
    return 'Unable to sign in. Please try again.';
  }
}
