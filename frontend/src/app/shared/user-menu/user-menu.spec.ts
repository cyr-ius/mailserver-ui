import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import { vi } from 'vitest';

import { AuthService } from '../../core/auth.service';
import { SessionUser } from '../../core/auth.models';
import { ThemeService } from '../../core/theme.service';
import { UserMenu } from './user-menu';

const ADMIN: SessionUser = {
  username: 'admin',
  display_name: 'Admin',
  role: 'admin',
  provider: 'local',
};

class AuthServiceStub {
  readonly user = signal<SessionUser | null>(ADMIN);
  readonly logout = vi.fn().mockResolvedValue(undefined);
}

describe('UserMenu', () => {
  let fixture: ComponentFixture<UserMenu>;
  let auth: AuthServiceStub;
  let theme: ThemeService;
  let router: Router;

  const el = () => fixture.nativeElement as HTMLElement;
  const trigger = () => el().querySelector('.user-menu-trigger') as HTMLButtonElement;
  const items = () => Array.from(el().querySelectorAll('.dropdown-item')) as HTMLButtonElement[];
  const themeItems = () => items().slice(0, 3);
  const logoutItem = () => items()[3];

  beforeEach(async () => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-bs-theme');

    await TestBed.configureTestingModule({
      imports: [UserMenu],
      providers: [provideRouter([]), { provide: AuthService, useClass: AuthServiceStub }],
    }).compileComponents();

    auth = TestBed.inject(AuthService) as unknown as AuthServiceStub;
    theme = TestBed.inject(ThemeService);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);

    fixture = TestBed.createComponent(UserMenu);
    fixture.detectChanges();
  });

  it('shows the display name on the trigger and the role in the menu', () => {
    expect(trigger().textContent?.trim()).toContain('Admin');
    expect(el().querySelector('.user-menu-identity')?.textContent).toContain('Administrator');
  });

  it('offers light, dark and system, marking the active one', () => {
    expect(themeItems().map((item) => item.textContent?.trim())).toEqual([
      'Light',
      'Dark',
      'System',
    ]);
    expect(themeItems()[2].classList.contains('active')).toBe(true);
  });

  it('applies the picked theme to the document', () => {
    themeItems()[1].click();
    fixture.detectChanges();

    expect(theme.themeMode()).toBe('dark');
    expect(document.documentElement.getAttribute('data-bs-theme')).toBe('dark');
    expect(themeItems()[1].classList.contains('active')).toBe(true);
  });

  it('signs out and returns to the login page', async () => {
    logoutItem().click();
    await fixture.whenStable();

    expect(auth.logout).toHaveBeenCalled();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('renders nothing without a session', () => {
    auth.user.set(null);
    fixture.detectChanges();

    expect(el().querySelector('.user-menu')).toBeNull();
  });
});
