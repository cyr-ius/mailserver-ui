import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { PasswordChangeRequest, User } from './auth.models';

/**
 * Access to the user-management API (admin only). Stateless: callers own the
 * resulting data; the service just wraps the HTTP calls.
 */
@Injectable({ providedIn: 'root' })
export class UsersService {
  private readonly http = inject(HttpClient);

  /** List all local and OIDC users. */
  async list(): Promise<User[]> {
    return firstValueFrom(this.http.get<User[]>('/api/users'));
  }

  /** Change the password of a local user. */
  async changePassword(userId: number, newPassword: string): Promise<User> {
    const body: PasswordChangeRequest = { new_password: newPassword };
    return firstValueFrom(this.http.patch<User>(`/api/users/${userId}/password`, body));
  }
}
