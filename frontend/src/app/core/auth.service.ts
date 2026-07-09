import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { AuthConfig, LoginRequest, SessionUser, roleGrants } from './auth.models';

/**
 * Central authentication state. Sessions are cookie-based (HttpOnly), so this
 * service never stores tokens; it only mirrors the server session as signals.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  private readonly _user = signal<SessionUser | null>(null);
  private readonly _config = signal<AuthConfig | null>(null);
  private readonly _loaded = signal(false);

  /** The current authenticated user, or null. */
  readonly user = this._user.asReadonly();
  /** Available login methods (local / OIDC). */
  readonly config = this._config.asReadonly();
  /** True once the initial session probe has completed. */
  readonly loaded = this._loaded.asReadonly();
  readonly isAuthenticated = computed(() => this._user() !== null);
  /** Administrators reach every section of the application. */
  readonly isAdmin = computed(() => roleGrants(this._user()?.role, 'admin'));
  /** Mailbox managers reach the Mailbox section; administrators do too. */
  readonly canManageMailboxes = computed(() => roleGrants(this._user()?.role, 'mailbox_manager'));

  /** Load the public auth configuration (which methods are enabled). */
  async loadConfig(): Promise<AuthConfig> {
    const config = await firstValueFrom(this.http.get<AuthConfig>('/api/auth/config'));
    this._config.set(config);
    return config;
  }

  /** Probe the current session; safe to call repeatedly. */
  async refreshSession(): Promise<SessionUser | null> {
    try {
      const user = await firstValueFrom(this.http.get<SessionUser>('/api/auth/me'));
      this._user.set(user);
      return user;
    } catch {
      this._user.set(null);
      return null;
    } finally {
      this._loaded.set(true);
    }
  }

  /** Authenticate with local credentials. Throws on failure. */
  async login(credentials: LoginRequest): Promise<SessionUser> {
    const user = await firstValueFrom(this.http.post<SessionUser>('/api/auth/login', credentials));
    this._user.set(user);
    return user;
  }

  /** Kick off the OIDC redirect flow via a full-page navigation. */
  loginWithOidc(): void {
    window.location.href = '/api/auth/oidc/login';
  }

  /** Clear the server session and local state. */
  async logout(): Promise<void> {
    try {
      await firstValueFrom(this.http.post('/api/auth/logout', {}));
    } finally {
      this._user.set(null);
    }
  }
}
