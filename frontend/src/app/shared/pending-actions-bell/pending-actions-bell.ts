import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';

import { PendingActionsService } from '../../core/pending-actions.service';

/** How often the badge re-checks the backend for changes made elsewhere. */
const POLL_INTERVAL_MS = 30_000;

/** Turn a failed restart call into a message the dropdown can display as-is. */
function restartErrorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse && err.status === 502) {
    return 'The mailserver container could not be reached. Check the Docker socket mount.';
  }
  return 'Failed to restart the mailserver. Please try again.';
}

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
  protected readonly restarting = signal(false);
  protected readonly restartError = signal<string | null>(null);

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

  protected async onRestart(): Promise<void> {
    this.restarting.set(true);
    this.restartError.set(null);
    try {
      await this.pendingActions.restart();
    } catch (err) {
      this.restartError.set(restartErrorMessage(err));
    } finally {
      this.restarting.set(false);
    }
  }
}
