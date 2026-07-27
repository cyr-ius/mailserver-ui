import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject } from '@angular/core';
import { DatePipe } from '@angular/common';

import { PendingActionsService } from '../../core/pending-actions.service';

/** How often the badge re-checks the backend for changes made elsewhere. */
const POLL_INTERVAL_MS = 30_000;

/** Header bell surfacing mailserver settings changes still awaiting a restart. */
@Component({
  selector: 'app-pending-actions-bell',
  imports: [DatePipe],
  templateUrl: './pending-actions-bell.html',
  styleUrl: './pending-actions-bell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PendingActionsBell {
  private readonly pendingActions = inject(PendingActionsService);

  protected readonly items = this.pendingActions.items;
  protected readonly count = computed(() => this.items().length);

  constructor() {
    void this.pendingActions.refresh();

    const timer = setInterval(() => void this.pendingActions.refresh(), POLL_INTERVAL_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  protected onOpen(): void {
    void this.pendingActions.refresh();
  }

  protected async onDismiss(key: string): Promise<void> {
    await this.pendingActions.dismiss(key);
  }

  protected async onDismissAll(): Promise<void> {
    await this.pendingActions.dismissAll();
  }
}
