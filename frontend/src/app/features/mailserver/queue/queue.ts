import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { MailserverService } from '../../../core/mailserver.service';
import { QueueMessage } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** Messages Postfix has accepted but not yet delivered. */
@Component({
  selector: 'app-mailserver-queue',
  templateUrl: './queue.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Queue {
  private readonly mailserver = inject(MailserverService);

  protected readonly queue = signal<QueueMessage[]>([]);
  protected readonly counts = signal<Record<string, number>>({});
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);
  protected readonly flushing = signal(false);
  protected readonly deletingQueueId = signal<string | null>(null);

  protected readonly countEntries = computed(() => Object.entries(this.counts()));

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const summary = await this.mailserver.getQueue();
      this.queue.set(summary.messages);
      this.counts.set(summary.counts);
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  protected refresh(): void {
    this.success.set(null);
    void this.load();
  }

  protected async onFlush(): Promise<void> {
    this.error.set(null);
    this.success.set(null);
    this.flushing.set(true);
    try {
      await this.mailserver.flushQueue();
      this.success.set('Delivery attempted for every deferred message.');
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.flushing.set(false);
    }
  }

  protected async onDelete(message: QueueMessage): Promise<void> {
    if (!confirm(`Delete the queued message ${message.queue_id}? This cannot be undone.`)) {
      return;
    }
    this.error.set(null);
    this.success.set(null);
    this.deletingQueueId.set(message.queue_id);
    try {
      await this.mailserver.deleteQueuedMessage(message.queue_id);
      this.success.set(`Message ${message.queue_id} deleted.`);
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.deletingQueueId.set(null);
    }
  }

  protected async onDeleteAll(): Promise<void> {
    if (!confirm('Delete every message in the queue? This cannot be undone.')) {
      return;
    }
    this.error.set(null);
    this.success.set(null);
    this.flushing.set(true);
    try {
      await this.mailserver.deleteAllQueued();
      this.success.set('The queue was emptied.');
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.flushing.set(false);
    }
  }
}
