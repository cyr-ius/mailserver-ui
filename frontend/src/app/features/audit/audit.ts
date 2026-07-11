import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { AuditService } from '../../core/audit.service';
import { AUDIT_CATEGORIES, AuditEntry, categoryLabel } from '../../core/audit.models';

/** Entries per page. The backend caps a page at 200. */
const PAGE_SIZE = 50;

/** Read-only view of the audit trail, with filters and paging. */
@Component({
  selector: 'app-audit',
  imports: [DatePipe],
  templateUrl: './audit.html',
  styleUrl: './audit.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Audit {
  private readonly auditService = inject(AuditService);

  protected readonly entries = signal<AuditEntry[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(true);
  protected readonly loadError = signal<string | null>(null);

  // Filters. Each is applied server-side; an empty value means "no filter".
  protected readonly actor = signal('');
  protected readonly category = signal('');
  protected readonly status = signal('');
  protected readonly page = signal(0);

  protected readonly categories = AUDIT_CATEGORIES;
  protected readonly categoryLabel = categoryLabel;
  protected readonly pageSize = PAGE_SIZE;

  protected readonly pageCount = computed(() => Math.max(1, Math.ceil(this.total() / PAGE_SIZE)));
  protected readonly firstShown = computed(() =>
    this.total() === 0 ? 0 : this.page() * PAGE_SIZE + 1,
  );
  protected readonly lastShown = computed(() =>
    Math.min(this.total(), this.page() * PAGE_SIZE + this.entries().length),
  );

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      const result = await this.auditService.list({
        actor: this.actor().trim(),
        category: this.category(),
        status: this.status(),
        limit: PAGE_SIZE,
        offset: this.page() * PAGE_SIZE,
      });
      this.entries.set(result.items);
      this.total.set(result.total);
    } catch {
      this.loadError.set('Unable to load the audit trail.');
    } finally {
      this.loading.set(false);
    }
  }

  /** Apply the filters. Always returns to the first page: page 3 of the previous
   * result set means nothing once the filters changed. */
  protected async applyFilters(): Promise<void> {
    this.page.set(0);
    await this.load();
  }

  protected async resetFilters(): Promise<void> {
    this.actor.set('');
    this.category.set('');
    this.status.set('');
    await this.applyFilters();
  }

  protected async goToPage(page: number): Promise<void> {
    const target = Math.min(Math.max(page, 0), this.pageCount() - 1);
    if (target === this.page()) {
      return;
    }
    this.page.set(target);
    await this.load();
  }

  protected async refresh(): Promise<void> {
    await this.load();
  }

  protected statusBadge(status: string): string {
    return status === 'failure' ? 'text-bg-danger' : 'text-bg-success';
  }
}
