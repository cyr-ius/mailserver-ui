import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { signal } from '@angular/core';

import { App } from './app';
import { AuthService } from './core/auth.service';
import { SessionUser } from './core/auth.models';

const ADMIN: SessionUser = {
  username: 'admin',
  display_name: 'Admin',
  role: 'admin',
  provider: 'local',
};

/** Stubs the session so the authenticated shell (sidebar + header) renders. */
class AuthServiceStub {
  readonly user = signal<SessionUser | null>(ADMIN);
  readonly isAdmin = signal(true);
  readonly canManageMailboxes = signal(true);
  async logout(): Promise<void> {}
}

describe('App', () => {
  let fixture: ComponentFixture<App>;

  const el = () => fixture.nativeElement as HTMLElement;
  const sidebar = () => el().querySelector('#app-sidebar') as HTMLElement;
  const collapseButton = () =>
    el().querySelector('[aria-controls="app-sidebar"]') as HTMLButtonElement;
  const sectionButtons = () => Array.from(el().querySelectorAll('.btn-toggle')) as HTMLElement[];
  const mailboxButton = () => sectionButtons()[0] as HTMLButtonElement;
  const mailserverButton = () => sectionButtons()[1] as HTMLButtonElement;

  beforeEach(async () => {
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: AuthService, useClass: AuthServiceStub },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(App);
    fixture.detectChanges();
  });

  it('starts expanded on a desktop viewport', () => {
    expect(sidebar().classList.contains('collapsed')).toBe(false);
  });

  it('collapses the sidebar and remembers it', () => {
    collapseButton().click();
    fixture.detectChanges();

    expect(sidebar().classList.contains('collapsed')).toBe(true);
    expect(localStorage.getItem('mailserver-ui-sidebar-collapsed')).toBe('true');
    expect(collapseButton().getAttribute('aria-expanded')).toBe('false');
  });

  it('keeps every section icon in the DOM once collapsed', () => {
    collapseButton().click();
    fixture.detectChanges();

    // Labels are hidden by CSS, so the icons must survive the collapse untouched.
    const icons = sectionButtons().map((button) => button.querySelector('i')?.className);
    expect(icons).toEqual(['bi bi-inbox', 'bi bi-hdd-network', 'bi bi-shield-lock', 'bi bi-gear']);
    expect(sectionButtons()[0].querySelector('.sidebar-label')?.textContent?.trim()).toBe('Mailbox');
  });

  it('names each section button, since the rail hides its label', () => {
    // `display: none` drops the label from the accessibility tree.
    const names = sectionButtons().map((button) => button.getAttribute('aria-label'));
    expect(names).toEqual(['Mailbox', 'Mailserver', 'Fail2ban', 'Settings']);
  });

  it('opens Mailbox only, so the rest of the rail stays quiet', () => {
    const expanded = sectionButtons().map((button) => button.getAttribute('aria-expanded'));
    expect(expanded).toEqual(['true', 'false', 'false', 'false']);
  });

  it('expands onto the picked section when a rail icon is clicked', () => {
    collapseButton().click();
    fixture.detectChanges();

    mailserverButton().click();
    fixture.detectChanges();

    expect(sidebar().classList.contains('collapsed')).toBe(false);
    expect(mailserverButton().getAttribute('aria-expanded')).toBe('true');
  });

  it('toggles the section in place when expanded', () => {
    expect(mailboxButton().getAttribute('aria-expanded')).toBe('true');

    mailboxButton().click();
    fixture.detectChanges();

    expect(mailboxButton().getAttribute('aria-expanded')).toBe('false');
    expect(sidebar().classList.contains('collapsed')).toBe(false);
  });

  it('restores the collapsed state from storage', () => {
    localStorage.setItem('mailserver-ui-sidebar-collapsed', 'true');

    const restored = TestBed.createComponent(App);
    restored.detectChanges();

    const aside = (restored.nativeElement as HTMLElement).querySelector('#app-sidebar');
    expect(aside?.classList.contains('collapsed')).toBe(true);
  });
});
