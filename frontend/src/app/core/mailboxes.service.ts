import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import {
  Alias,
  AliasCreateRequest,
  Mailbox,
  MailboxCreateRequest,
  MailboxPasswordUpdateRequest,
  QuotaUpdateRequest,
} from './mailbox.models';

/**
 * Access to the mailbox-management API (admin only). Wraps the CRUD calls
 * against docker-mailserver accounts, quotas and aliases; callers own the
 * resulting data.
 */
@Injectable({ providedIn: 'root' })
export class MailboxesService {
  private readonly http = inject(HttpClient);

  /** List all mail accounts. */
  async list(): Promise<Mailbox[]> {
    return firstValueFrom(this.http.get<Mailbox[]>('/api/mailboxes'));
  }

  /** Create a new mail account, optionally with a quota. */
  async create(email: string, password: string, quota?: string | null): Promise<Mailbox> {
    const body: MailboxCreateRequest = { email, password, quota: quota || null };
    return firstValueFrom(this.http.post<Mailbox>('/api/mailboxes', body));
  }

  /** Reset the password of an existing mail account. */
  async resetPassword(email: string, newPassword: string): Promise<Mailbox> {
    const body: MailboxPasswordUpdateRequest = { new_password: newPassword };
    return firstValueFrom(
      this.http.patch<Mailbox>(`/api/mailboxes/${encodeURIComponent(email)}/password`, body),
    );
  }

  /** Set (or clear, with null) the quota of a mail account. */
  async setQuota(email: string, quota: string | null): Promise<Mailbox> {
    const body: QuotaUpdateRequest = { quota: quota || null };
    return firstValueFrom(
      this.http.put<Mailbox>(`/api/mailboxes/${encodeURIComponent(email)}/quota`, body),
    );
  }

  /** Delete a mail account. */
  async delete(email: string): Promise<void> {
    await firstValueFrom(this.http.delete<void>(`/api/mailboxes/${encodeURIComponent(email)}`));
  }

  /** List the aliases forwarding to a mail account. */
  async listAliases(email: string): Promise<Alias[]> {
    return firstValueFrom(
      this.http.get<Alias[]>(`/api/mailboxes/${encodeURIComponent(email)}/aliases`),
    );
  }

  /** Add an alias forwarding to a mail account. */
  async addAlias(email: string, alias: string): Promise<Alias> {
    const body: AliasCreateRequest = { alias };
    return firstValueFrom(
      this.http.post<Alias>(`/api/mailboxes/${encodeURIComponent(email)}/aliases`, body),
    );
  }

  /** Remove an alias forwarding to a mail account. */
  async deleteAlias(email: string, alias: string): Promise<void> {
    await firstValueFrom(
      this.http.delete<void>(
        `/api/mailboxes/${encodeURIComponent(email)}/aliases/${encodeURIComponent(alias)}`,
      ),
    );
  }
}
