import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterRenderEffect,
  computed,
  inject,
  input,
  model,
  signal,
  viewChild,
  viewChildren,
} from '@angular/core';

import { User } from '../../core/auth.models';

/** Distinguishes the ARIA ids of several selects living on the same page. */
let nextUid = 0;

/**
 * Searchable dropdown to pick several users at once.
 *
 * Selected ids are exposed as a two-way `model()`, so the parent owns the
 * selection and this component stays free of any API knowledge.
 */
@Component({
  selector: 'app-user-multi-select',
  templateUrl: './user-multi-select.html',
  styleUrl: './user-multi-select.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'd-block position-relative',
    '(document:click)': 'onDocumentClick($event)',
    '(keydown.escape)': 'close()',
  },
})
export class UserMultiSelect {
  private readonly host = inject(ElementRef<HTMLElement>);

  /** Users offered in the dropdown. */
  readonly users = input.required<User[]>();
  /** Ids of the currently selected users (two-way bound). */
  readonly selectedIds = model<number[]>([]);
  readonly disabled = input(false);
  readonly placeholder = input('Search users…');
  readonly emptyLabel = input('No user available');
  /** Accessible name of the search field — no visible `<label>` can target it. */
  readonly ariaLabel = input('Search and select users');

  protected readonly uid = nextUid++;
  protected readonly listboxId = `user-multi-select-list-${this.uid}`;

  protected readonly open = signal(false);
  protected readonly query = signal('');
  /** Index of the option highlighted by the keyboard, -1 when none. */
  protected readonly activeIndex = signal(-1);

  private readonly optionRefs = viewChildren<ElementRef<HTMLElement>>('optionEl');
  private readonly searchInput = viewChild<ElementRef<HTMLInputElement>>('searchInput');

  constructor() {
    // Keep the keyboard-highlighted option inside the scrollable list.
    afterRenderEffect(() => {
      const index = this.activeIndex();
      if (index >= 0) {
        this.optionRefs()[index]?.nativeElement.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  protected readonly selectedUsers = computed(() => {
    const ids = new Set(this.selectedIds());
    return this.users().filter((u) => ids.has(u.id));
  });

  protected readonly filtered = computed(() => {
    const needle = this.query().trim().toLowerCase();
    if (!needle) {
      return this.users();
    }
    return this.users().filter(
      (u) =>
        u.username.toLowerCase().includes(needle) || u.display_name.toLowerCase().includes(needle),
    );
  });

  protected isSelected(userId: number): boolean {
    return this.selectedIds().includes(userId);
  }

  protected toggle(userId: number): void {
    const current = this.selectedIds();
    this.selectedIds.set(
      current.includes(userId) ? current.filter((id) => id !== userId) : [...current, userId],
    );
  }

  protected remove(userId: number): void {
    this.selectedIds.set(this.selectedIds().filter((id) => id !== userId));
  }

  protected clear(): void {
    this.selectedIds.set([]);
  }

  protected openDropdown(): void {
    if (!this.disabled()) {
      this.open.set(true);
    }
  }

  /** Clicking anywhere on the control behaves like clicking the search field. */
  protected focusSearch(): void {
    if (!this.disabled()) {
      this.searchInput()?.nativeElement.focus();
      this.openDropdown();
    }
  }

  protected close(): void {
    this.open.set(false);
    this.activeIndex.set(-1);
  }

  protected onQueryInput(value: string): void {
    this.query.set(value);
    this.activeIndex.set(-1);
    this.openDropdown();
  }

  /** Arrow keys move the highlight, Enter toggles it, Backspace pops the last chip. */
  protected onKeydown(event: KeyboardEvent): void {
    const options = this.filtered();

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.openDropdown();
        this.moveActive(1, options.length);
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.moveActive(-1, options.length);
        break;
      case 'Enter': {
        const active = options[this.activeIndex()];
        if (active) {
          event.preventDefault();
          this.toggle(active.id);
        }
        break;
      }
      case 'Backspace': {
        if (this.query()) {
          return;
        }
        const selected = this.selectedIds();
        if (selected.length > 0) {
          this.remove(selected[selected.length - 1]);
        }
        break;
      }
    }
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.host.nativeElement.contains(event.target)) {
      this.close();
    }
  }

  protected optionId(index: number): string {
    return `user-multi-select-${this.uid}-option-${index}`;
  }

  protected activeOptionId(): string | null {
    const index = this.activeIndex();
    return index >= 0 ? this.optionId(index) : null;
  }

  private moveActive(delta: number, count: number): void {
    if (count === 0) {
      this.activeIndex.set(-1);
      return;
    }
    const current = this.activeIndex();
    if (current < 0) {
      this.activeIndex.set(delta > 0 ? 0 : count - 1);
      return;
    }
    this.activeIndex.set((current + delta + count) % count);
  }
}
