import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { AuthService } from '../../core/auth.service';
import { UsersService } from '../../core/users.service';
import { GroupsService } from '../../core/groups.service';
import { ROLES, Role, User, roleLabel } from '../../core/auth.models';
import { GroupWithMembers } from '../../core/group.models';
import { UserMultiSelect } from '../../shared/user-multi-select/user-multi-select';

const MIN_PASSWORD_LENGTH = 8;

/** Bootstrap contextual colour per role, most privileged first in the UI. */
const ROLE_BADGE: Record<Role, string> = {
  admin: 'text-bg-danger',
  mailbox_manager: 'text-bg-primary',
  guest: 'text-bg-secondary',
};

@Component({
  selector: 'app-users',
  imports: [FormField, DatePipe, UserMultiSelect],
  templateUrl: './users.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Users {
  private readonly auth = inject(AuthService);
  private readonly usersService = inject(UsersService);
  private readonly groupsService = inject(GroupsService);
  private readonly router = inject(Router);

  protected readonly currentUser = this.auth.user;
  protected readonly users = signal<User[]>([]);
  protected readonly groups = signal<GroupWithMembers[]>([]);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);
  protected readonly loggingOut = signal(false);

  // Local account creation state
  protected readonly showUserForm = signal(false);
  protected readonly creatingUser = signal(false);
  protected readonly userCreationError = signal<string | null>(null);
  protected readonly deletingUserId = signal<number | null>(null);
  protected readonly userModel = signal({
    username: '',
    display_name: '',
    password: '',
    confirm: '',
  });
  protected readonly userForm = form(this.userModel, (path) => {
    required(path.username, { message: 'A username is required' });
    required(path.password, { message: 'A password is required' });
    required(path.confirm, { message: 'Please confirm the password' });
  });
  private readonly usernameInput = viewChild<ElementRef<HTMLInputElement>>('usernameInput');

  // Groups management state
  protected readonly activeTab = signal<'users' | 'groups'>('users');
  protected readonly savingGroup = signal(false);
  protected readonly groupFormError = signal<string | null>(null);
  protected readonly groupModel = signal({ name: '', description: '', role: 'guest' as Role });
  protected readonly groupForm = form(this.groupModel, (path) => {
    required(path.name, { message: 'Group name is required' });
  });
  private readonly groupNameInput = viewChild<ElementRef<HTMLInputElement>>('groupNameInput');
  protected readonly showGroupForm = signal(false);
  /** Id of the group the form edits, or null when it creates a new one. */
  protected readonly editedGroupId = signal<number | null>(null);

  /** Roles offered in the group form, most privileged first. */
  protected readonly roleOptions = [...ROLES].reverse();
  protected readonly roleLabel = roleLabel;

  protected roleBadge(role: Role): string {
    return ROLE_BADGE[role] ?? 'text-bg-secondary';
  }

  // Group members management
  protected readonly editingGroupId = signal<number | null>(null);
  protected readonly selectedUserIds = signal<number[]>([]);
  protected readonly addingMembers = signal(false);
  protected readonly groupMembers = signal<User[]>([]);
  protected readonly loadingMembers = signal(false);
  protected readonly membersError = signal<string | null>(null);
  protected readonly removingMemberId = signal<number | null>(null);

  /** Users that are not members of the group being edited yet. */
  protected readonly assignableUsers = computed(() => {
    const memberIds = new Set(this.groupMembers().map((m) => m.id));
    return this.users().filter((u) => !memberIds.has(u.id));
  });

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

  protected readonly editingGroup = computed(
    () => this.groups().find((g) => g.id === this.editingGroupId()) ?? null,
  );

  constructor() {
    void this.loadUsers();
    void this.loadGroups();

    effect(() => this.usernameInput()?.nativeElement.focus());
    effect(() => this.groupNameInput()?.nativeElement.focus());
  }

  /** Creates the group, or saves the one being edited when `editedGroupId` is set. */
  protected async submitGroup(): Promise<void> {
    this.groupFormError.set(null);
    submit(this.groupForm, async () => {
      const { name, description, role } = this.groupModel();
      if (!name.trim()) {
        this.groupFormError.set('Group name is required');
        return;
      }
      const groupId = this.editedGroupId();
      this.savingGroup.set(true);
      try {
        if (groupId === null) {
          await this.groupsService.create(name, description, role);
          this.successMessage.set(`Group "${name}" created successfully.`);
        } else {
          await this.groupsService.update(groupId, name, description, role);
          this.successMessage.set(`Group "${name}" updated successfully.`);
        }
        this.closeGroupForm();
        await this.loadGroups();
      } catch (err) {
        const fallback =
          groupId === null ? 'Unable to create the group.' : 'Unable to update the group.';
        this.groupFormError.set(this.apiErrorFor(err, fallback));
      } finally {
        this.savingGroup.set(false);
      }
    });
  }

  protected startCreateGroup(): void {
    this.editedGroupId.set(null);
    this.resetGroupModel();
    this.groupFormError.set(null);
    this.showGroupForm.set(true);
  }

  /** Opens the group form on an existing group, so its granted role can be changed. */
  protected startEditGroup(group: GroupWithMembers): void {
    this.editedGroupId.set(group.id);
    this.groupModel.set({
      name: group.name,
      description: group.description,
      role: group.role,
    });
    this.groupFormError.set(null);
    this.successMessage.set(null);
    this.showGroupForm.set(true);
  }

  protected closeGroupForm(): void {
    this.showGroupForm.set(false);
    this.editedGroupId.set(null);
    this.resetGroupModel();
    this.groupFormError.set(null);
  }

  private resetGroupModel(): void {
    this.groupModel.set({ name: '', description: '', role: 'guest' });
  }

  protected async startEditingGroup(groupId: number): Promise<void> {
    if (this.editingGroupId() === groupId) {
      this.cancelEditingGroup();
      return;
    }
    this.editingGroupId.set(groupId);
    this.selectedUserIds.set([]);
    this.membersError.set(null);
    this.successMessage.set(null);
    await this.loadGroupMembers(groupId);
  }

  protected cancelEditingGroup(): void {
    this.editingGroupId.set(null);
    this.selectedUserIds.set([]);
    this.groupMembers.set([]);
    this.membersError.set(null);
  }

  protected async addSelectedUsersToGroup(): Promise<void> {
    const groupId = this.editingGroupId();
    const userIds = this.selectedUserIds();
    if (groupId === null || userIds.length === 0) {
      return;
    }

    this.membersError.set(null);
    this.addingMembers.set(true);
    try {
      await this.groupsService.addMembers(groupId, userIds);
      this.successMessage.set(`Added ${userIds.length} user(s) to the group.`);
      this.selectedUserIds.set([]);
      await Promise.all([this.loadGroupMembers(groupId), this.loadGroups()]);
    } catch (err) {
      this.membersError.set(this.apiErrorFor(err, 'Unable to add the selected users.'));
    } finally {
      this.addingMembers.set(false);
    }
  }

  protected async removeMember(member: User): Promise<void> {
    const groupId = this.editingGroupId();
    if (groupId === null) {
      return;
    }

    this.membersError.set(null);
    this.removingMemberId.set(member.id);
    try {
      await this.groupsService.removeMember(groupId, member.id);
      this.successMessage.set(`Removed ${member.username} from the group.`);
      await Promise.all([this.loadGroupMembers(groupId), this.loadGroups()]);
    } catch (err) {
      this.membersError.set(this.apiErrorFor(err, `Unable to remove ${member.username}.`));
    } finally {
      this.removingMemberId.set(null);
    }
  }

  protected async deleteGroup(group: GroupWithMembers): Promise<void> {
    if (!confirm(`Are you sure you want to delete the group "${group.name}"?`)) {
      return;
    }
    this.saving.set(true);
    try {
      await this.groupsService.delete(group.id);
      this.successMessage.set(`Group "${group.name}" deleted.`);
      if (this.editingGroupId() === group.id) {
        this.cancelEditingGroup();
      }
      if (this.editedGroupId() === group.id) {
        this.closeGroupForm();
      }
      await this.loadGroups();
    } catch (err) {
      this.loadError.set(this.apiErrorFor(err, `Unable to delete "${group.name}".`));
    } finally {
      this.saving.set(false);
    }
  }

  private async loadGroupMembers(groupId: number): Promise<void> {
    this.loadingMembers.set(true);
    try {
      this.groupMembers.set(await this.groupsService.getMembers(groupId));
    } catch {
      this.groupMembers.set([]);
      this.membersError.set('Unable to load the group members.');
    } finally {
      this.loadingMembers.set(false);
    }
  }

  private async loadGroups(): Promise<void> {
    try {
      this.groups.set(await this.groupsService.list());
    } catch {
      this.loadError.set('Unable to load groups.');
    }
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

  protected async createUser(): Promise<void> {
    this.userCreationError.set(null);
    this.successMessage.set(null);
    submit(this.userForm, async () => {
      const { username, display_name, password, confirm } = this.userModel();
      if (password.length < MIN_PASSWORD_LENGTH) {
        this.userCreationError.set(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
        return;
      }
      if (password !== confirm) {
        this.userCreationError.set('Passwords do not match.');
        return;
      }
      this.creatingUser.set(true);
      try {
        await this.usersService.create(username, display_name, password);
        this.successMessage.set(`User "${username}" created. Add it to a group to grant a role.`);
        this.cancelCreateUser();
        await this.loadUsers();
      } catch (err) {
        this.userCreationError.set(this.apiErrorFor(err, 'Unable to create the user.'));
      } finally {
        this.creatingUser.set(false);
      }
    });
  }

  protected startCreateUser(): void {
    this.userCreationError.set(null);
    this.successMessage.set(null);
    this.showUserForm.set(true);
  }

  protected cancelCreateUser(): void {
    this.showUserForm.set(false);
    this.userCreationError.set(null);
    this.userModel.set({ username: '', display_name: '', password: '', confirm: '' });
  }

  protected async deleteUser(user: User): Promise<void> {
    if (!confirm(`Are you sure you want to delete the account "${user.username}"?`)) {
      return;
    }
    this.loadError.set(null);
    this.successMessage.set(null);
    this.deletingUserId.set(user.id);
    try {
      await this.usersService.delete(user.id);
      this.successMessage.set(`User "${user.username}" deleted.`);
      if (this.editingId() === user.id) {
        this.cancelEdit();
      }
      await Promise.all([this.loadUsers(), this.loadGroups()]);
    } catch (err) {
      this.loadError.set(this.apiErrorFor(err, `Unable to delete "${user.username}".`));
    } finally {
      this.deletingUserId.set(null);
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
