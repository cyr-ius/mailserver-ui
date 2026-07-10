import { signal } from '@angular/core';

/** Direction a sortable column is ordered in. */
export type SortDirection = 'asc' | 'desc';

/** Compare two rows on a column, ascending. */
export type Comparator<C extends string, T> = (column: C, a: T, b: T) => number;

/**
 * Sort state for a table whose columns are named by `C`. A column cycles through
 * ascending, descending and back to unsorted, where unsorted keeps the rows in
 * the order the server returned them.
 */
export class TableSort<C extends string> {
  /** `null` while no column is sorted. */
  readonly column = signal<C | null>(null);
  readonly direction = signal<SortDirection>('asc');

  /** Cycle a column through ascending, descending and back to unsorted. */
  toggle(column: C): void {
    if (this.column() !== column) {
      this.column.set(column);
      this.direction.set('asc');
      return;
    }
    if (this.direction() === 'asc') {
      this.direction.set('desc');
      return;
    }
    this.column.set(null);
  }

  /** Sorting is stable, so rows sharing a value keep their original order. */
  apply<T>(rows: readonly T[], compare: Comparator<C, T>): T[] {
    const column = this.column();
    if (!column) {
      return rows.slice();
    }
    const direction = this.direction() === 'asc' ? 1 : -1;
    return rows.slice().sort((a, b) => direction * compare(column, a, b));
  }

  /** Bootstrap icon classes for a column header. */
  icon(column: C): string {
    if (this.column() !== column) {
      return 'bi bi-arrow-down-up opacity-50';
    }
    return this.direction() === 'asc' ? 'bi bi-sort-down-alt' : 'bi bi-sort-up-alt';
  }

  /** `aria-sort` value for a column header. */
  aria(column: C): 'ascending' | 'descending' | 'none' {
    if (this.column() !== column) {
      return 'none';
    }
    return this.direction() === 'asc' ? 'ascending' : 'descending';
  }
}
