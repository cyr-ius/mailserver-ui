import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { User } from '../../core/auth.models';
import { UserMultiSelect } from './user-multi-select';

function user(id: number, username: string, displayName = ''): User {
  return {
    id,
    username,
    display_name: displayName,
    role: 'guest',
    effective_role: 'guest',
    provider: 'local',
    created_at: '2026-01-01T00:00:00Z',
    last_login_at: null,
  };
}

@Component({
  imports: [UserMultiSelect],
  template: `<app-user-multi-select [users]="users()" [(selectedIds)]="selected" />`,
})
class Host {
  readonly users = signal<User[]>([
    user(1, 'alice', 'Alice Martin'),
    user(2, 'bob', 'Bob Dupont'),
    user(3, 'carol', 'Carol Bernard'),
  ]);
  readonly selected = signal<number[]>([]);
}

describe('UserMultiSelect', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;

  const el = () => fixture.nativeElement as HTMLElement;
  const search = () => el().querySelector('input[role="combobox"]') as HTMLInputElement;
  const options = () => Array.from(el().querySelectorAll('[role="option"]')) as HTMLElement[];
  const optionNames = () =>
    options().map((o) => o.querySelector('span')?.textContent?.trim() ?? '');

  const type = (value: string) => {
    search().value = value;
    search().dispatchEvent(new Event('input'));
    fixture.detectChanges();
  };

  const press = (key: string) => {
    search().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    fixture.detectChanges();
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [Host] }).compileComponents();
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('keeps the list closed until the field is focused', () => {
    expect(options()).toHaveLength(0);

    search().dispatchEvent(new Event('focus'));
    fixture.detectChanges();

    expect(options()).toHaveLength(3);
  });

  it('filters options on username and display name', () => {
    type('bo');
    expect(optionNames()).toEqual(['bob']);

    type('bernard');
    expect(optionNames()).toEqual(['carol']);

    type('zzz');
    expect(options()).toHaveLength(0);
    expect(el().textContent).toContain('No user matches');
  });

  it('accumulates several users in the selection', () => {
    type('');
    options()[0].click();
    options()[2].click();
    fixture.detectChanges();

    expect(host.selected()).toEqual([1, 3]);
  });

  it('deselects an already selected user', () => {
    host.selected.set([2]);
    type('');

    expect(options()[1].getAttribute('aria-selected')).toBe('true');
    options()[1].click();
    fixture.detectChanges();

    expect(host.selected()).toEqual([]);
  });

  it('picks the highlighted option with the keyboard', () => {
    type('');
    press('ArrowDown');
    press('ArrowDown');
    press('Enter');

    expect(host.selected()).toEqual([2]);
  });

  it('removes the last chip on Backspace when the query is empty', () => {
    host.selected.set([1, 2]);
    fixture.detectChanges();

    press('Backspace');

    expect(host.selected()).toEqual([1]);
  });

  it('removes a user through its chip close button', () => {
    host.selected.set([1, 3]);
    fixture.detectChanges();

    const chipClose = el().querySelector('[aria-label="Remove carol"]') as HTMLButtonElement;
    chipClose.click();
    fixture.detectChanges();

    expect(host.selected()).toEqual([1]);
  });

  it('closes the list when clicking outside', () => {
    type('');
    expect(options()).toHaveLength(3);

    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    fixture.detectChanges();

    expect(options()).toHaveLength(0);
  });
});
