import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { PasswordChangeRequest, User, UserCreateRequest } from './auth.models';

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

  /** Create a local user. The account starts as a guest until added to a group. */
  async create(username: string, displayName: string, password: string): Promise<User> {
    const body: UserCreateRequest = {
      username,
      display_name: displayName,
      password,
    };
    return firstValueFrom(this.http.post<User>('/api/users', body));
  }

  /** Delete a user and all of its group memberships. */
  async delete(userId: number): Promise<void> {
    return firstValueFrom(this.http.delete<void>(`/api/users/${userId}`));
  }

  /** Change the password of a local user. */
  async changePassword(userId: number, newPassword: string): Promise<User> {
    const body: PasswordChangeRequest = { new_password: newPassword };
    return firstValueFrom(this.http.patch<User>(`/api/users/${userId}/password`, body));
  }
}
