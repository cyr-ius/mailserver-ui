import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { MailserverService } from '../../../core/mailserver.service';
import { TableSort } from '../../../shared/table-sort';
import { mailserverErrorMessage } from '../mailserver.utils';

/** Sortable columns; the message column is free text and stays unsorted. */
type LogColumn = 'date' | 'product' | 'process' | 'pid';

/** A single mail log line split into its syslog fields. */
interface MailLogEntry {
  date: Date | null;
  timestamp: string;
  product: string;
  process: string;
  pid: string;
  message: string;
  raw: string;
}

/**
 * `<timestamp> <host> <product>[/<process>][[<pid>]]: <message>` — the host is
 * always the mailserver itself and is dropped. Postfix logs a `<product>/<process>`
 * pair (`postfix/master[857]`), Dovecot and Amavis only a product.
 */
const LOG_LINE = /^(\S+)\s+\S+\s+([^\s:[/]+)(?:\/([^\s:[]+))?(?:\[(\d+)\])?:\s*(.*)$/;

/** Compare two entries on a column, ascending. Dates and PIDs sort numerically. */
function compareOn(column: LogColumn, a: MailLogEntry, b: MailLogEntry): number {
  switch (column) {
    case 'date':
      return (a.date?.getTime() ?? 0) - (b.date?.getTime() ?? 0);
    case 'pid':
      // A missing PID reads as 0 and groups before the real ones.
      return Number(a.pid || 0) - Number(b.pid || 0);
    default:
      return a[column].localeCompare(b[column]);
  }
}

/** Split a raw mail log line; an unparsable line keeps its text in `message`. */
function parseLogLine(raw: string): MailLogEntry {
  const match = LOG_LINE.exec(raw);
  if (!match) {
    return { date: null, timestamp: '', product: '', process: '', pid: '', message: raw, raw };
  }
  const [, timestamp, product, process = '', pid = '', message] = match;
  const date = new Date(timestamp);
  return {
    date: Number.isNaN(date.getTime()) ? null : date,
    timestamp,
    product,
    process,
    pid,
    message,
    raw,
  };
}

/** Trailing lines of the mailserver mail log. */
@Component({
  selector: 'app-mailserver-logs',
  imports: [DatePipe],
  templateUrl: './logs.html',
  styleUrl: './logs.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Logs {
  private readonly mailserver = inject(MailserverService);

  protected readonly lines = signal<string[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly filter = signal('');
  protected readonly sort = new TableSort<LogColumn>();

  protected readonly entries = computed(() => this.lines().map(parseLogLine));

  protected readonly filtered = computed(() => {
    const needle = this.filter().trim().toLowerCase();
    const entries = this.entries();
    if (!needle) {
      return entries;
    }
    return entries.filter((entry) => entry.raw.toLowerCase().includes(needle));
  });

  protected readonly visible = computed(() => this.sort.apply(this.filtered(), compareOn));

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.lines.set((await this.mailserver.getMailLogs()).lines);
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  protected refresh(): void {
    void this.load();
  }

  protected onFilterInput(event: Event): void {
    this.filter.set((event.target as HTMLInputElement).value);
  }
}
