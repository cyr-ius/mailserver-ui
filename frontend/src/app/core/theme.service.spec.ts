import { TestBed } from '@angular/core/testing';

import { ThemeService } from './theme.service';

/** Minimal MediaQueryList double whose `matches` can be flipped at will. */
class FakeMediaQueryList {
  matches = false;
  private readonly listeners = new Set<(event: MediaQueryListEvent) => void>();

  addEventListener(_type: 'change', listener: (event: MediaQueryListEvent) => void): void {
    this.listeners.add(listener);
  }

  removeEventListener(_type: 'change', listener: (event: MediaQueryListEvent) => void): void {
    this.listeners.delete(listener);
  }

  emit(matches: boolean): void {
    this.matches = matches;
    for (const listener of this.listeners) {
      listener({ matches } as MediaQueryListEvent);
    }
  }
}

describe('ThemeService', () => {
  let media: FakeMediaQueryList;
  let originalMatchMedia: typeof window.matchMedia;

  function createService(): ThemeService {
    TestBed.configureTestingModule({});
    const service = TestBed.inject(ThemeService);
    TestBed.tick();
    return service;
  }

  const appliedTheme = () => document.documentElement.getAttribute('data-bs-theme');

  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-bs-theme');

    media = new FakeMediaQueryList();
    originalMatchMedia = window.matchMedia;
    window.matchMedia = (() => media) as unknown as typeof window.matchMedia;
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it('defaults to auto and resolves against the system preference', () => {
    media.matches = true;
    const service = createService();

    expect(service.themeMode()).toBe('auto');
    expect(service.isDarkMode()).toBe(true);
    expect(appliedTheme()).toBe('dark');
  });

  it('follows the system preference while in auto mode', () => {
    const service = createService();
    expect(service.resolvedTheme()).toBe('light');

    media.emit(true);
    TestBed.tick();

    expect(service.resolvedTheme()).toBe('dark');
    expect(appliedTheme()).toBe('dark');
  });

  it('ignores the system preference once a mode is pinned', () => {
    const service = createService();
    service.setThemeMode('light');
    TestBed.tick();

    media.emit(true);
    TestBed.tick();

    expect(service.resolvedTheme()).toBe('light');
    expect(appliedTheme()).toBe('light');
  });

  it('toggles from the theme currently on screen', () => {
    media.matches = true;
    const service = createService();

    service.toggle();
    TestBed.tick();

    expect(service.themeMode()).toBe('light');
    expect(appliedTheme()).toBe('light');
  });

  it('restores a persisted mode', () => {
    localStorage.setItem('mailserver-ui-theme', 'dark');
    const service = createService();

    expect(service.themeMode()).toBe('dark');
    expect(appliedTheme()).toBe('dark');
  });

  it('falls back to auto when the stored value is not a mode', () => {
    localStorage.setItem('mailserver-ui-theme', 'sepia');

    expect(createService().themeMode()).toBe('auto');
  });
});
