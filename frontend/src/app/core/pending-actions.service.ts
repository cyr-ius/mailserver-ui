import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import { PendingAction, PendingActionsSummary } from './pending-action.models';

/**
 * Tracks the mailserver settings changes still awaiting a container restart
 * (admin only). State lives here rather than in the navbar bell component so
 * it survives navigation and stays a single source of truth for the badge.
 */
@Injectable({ providedIn: 'root' })
export class PendingActionsService {
  private readonly http = inject(HttpClient);

  private readonly _items = signal<PendingAction[]>([]);

  /** Every pending action, most recently changed first. */
  readonly items = this._items.asReadonly();

  /** Re-fetch the pending actions from the backend. */
  async refresh(): Promise<void> {
    const summary = await firstValueFrom(
      this.http.get<PendingActionsSummary>('/api/pending-actions'),
    );
    this._items.set(summary.items);
  }

  /** Dismiss a single pending action. */
  async dismiss(key: string): Promise<void> {
    await firstValueFrom(this.http.delete<void>(`/api/pending-actions/${encodeURIComponent(key)}`));
    this._items.update((items) => items.filter((item) => item.key !== key));
  }

  /** Dismiss every pending action, e.g. once the mailserver has been restarted. */
  async dismissAll(): Promise<void> {
    await firstValueFrom(this.http.delete<void>('/api/pending-actions'));
    this._items.set([]);
  }
}
