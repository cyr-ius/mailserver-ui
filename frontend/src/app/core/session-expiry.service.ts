import { Injectable, signal } from '@angular/core';

/**
 * Flags a session the backend has rejected. Kept apart from `AuthService` so the
 * HTTP interceptor can report an expiry without depending on `HttpClient`.
 */
@Injectable({ providedIn: 'root' })
export class SessionExpiryService {
  private readonly _expired = signal(false);

  /** True once an API call came back with 401 on an established session. */
  readonly expired = this._expired.asReadonly();

  /** Raise the flag; repeated calls (parallel requests) collapse into one. */
  notifyExpired(): void {
    this._expired.set(true);
  }

  /** Lower the flag, once the user has been sent back to the login page. */
  clear(): void {
    this._expired.set(false);
  }
}
