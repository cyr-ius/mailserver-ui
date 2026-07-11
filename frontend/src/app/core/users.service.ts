import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import {
  PasswordChangeRequest,
  SelfPasswordChangeRequest,
  User,
  UserCreateRequest,
  UserStatusUpdate,
} from './auth.models';

/**
 * Access to the user API: the `me` calls are open to any signed-in user, the
 * rest is admin-only. Stateless: callers own the resulting data; the service
 * just wraps the HTTP calls.
 */
@Injectable({ providedIn: 'root' })
export class UsersService {
  private readonly http = inject(HttpClient);

  /** Full profile of the signed-in user, group-granted role included. */
  async me(): Promise<User> {
    return firstValueFrom(this.http.get<User>('/api/users/me'));
  }

  /** Change the signed-in user's own password. Local accounts only. */
  async changeOwnPassword(currentPassword: string, newPassword: string): Promise<User> {
    const body: SelfPasswordChangeRequest = {
      current_password: currentPassword,
      new_password: newPassword,
    };
    return firstValueFrom(this.http.patch<User>('/api/users/me/password', body));
  }

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

  /**
   * Activate or deactivate an account, local or OIDC. A deactivated account keeps
   * its data but can no longer sign in, and its sessions and API keys stop
   * working immediately.
   */
  async setActive(userId: number, isActive: boolean): Promise<User> {
    const body: UserStatusUpdate = { is_active: isActive };
    return firstValueFrom(this.http.patch<User>(`/api/users/${userId}/status`, body));
  }
}
