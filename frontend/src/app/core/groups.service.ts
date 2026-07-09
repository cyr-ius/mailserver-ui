import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { Role, User } from './auth.models';
import { Group, GroupWithMembers } from './group.models';

/**
 * Access to the group-management API (admin only). Stateless: callers own the
 * resulting data; the service just wraps the HTTP calls.
 */
@Injectable({ providedIn: 'root' })
export class GroupsService {
  private readonly http = inject(HttpClient);

  /** List all groups with member count. */
  async list(): Promise<GroupWithMembers[]> {
    return firstValueFrom(this.http.get<GroupWithMembers[]>('/api/groups'));
  }

  /** Create a new group granting `role` to its members. */
  async create(name: string, description: string = '', role: Role = 'guest'): Promise<Group> {
    const body = { name, description, role };
    return firstValueFrom(this.http.post<Group>('/api/groups', body));
  }

  /** Update a group. */
  async update(groupId: number, name: string, description: string, role: Role): Promise<Group> {
    const body = { name, description, role };
    return firstValueFrom(this.http.patch<Group>(`/api/groups/${groupId}`, body));
  }

  /** Delete a group. */
  async delete(groupId: number): Promise<void> {
    return firstValueFrom(this.http.delete<void>(`/api/groups/${groupId}`));
  }

  /** Get all members of a group. */
  async getMembers(groupId: number): Promise<User[]> {
    return firstValueFrom(this.http.get<User[]>(`/api/groups/${groupId}/members`));
  }

  /** Add a user to a group. */
  async addMember(groupId: number, userId: number): Promise<void> {
    return firstValueFrom(this.http.post<void>(`/api/groups/${groupId}/members/${userId}`, {}));
  }

  /** Remove a user from a group. */
  async removeMember(groupId: number, userId: number): Promise<void> {
    return firstValueFrom(this.http.delete<void>(`/api/groups/${groupId}/members/${userId}`));
  }

  /** Add multiple users to a group. */
  async addMembers(groupId: number, userIds: number[]): Promise<void> {
    const body = { user_ids: userIds };
    return firstValueFrom(this.http.post<void>(`/api/groups/${groupId}/members/batch`, body));
  }
}
