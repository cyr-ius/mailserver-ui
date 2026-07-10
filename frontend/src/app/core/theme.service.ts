import { DOCUMENT, DestroyRef, Injectable, computed, effect, inject, signal } from '@angular/core';

/** The preference expressed by the user. */
export type ThemeMode = 'light' | 'dark' | 'auto';

/** The theme actually applied to the document, once `auto` is resolved. */
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'mailserver-ui-theme';
const DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)';
const TRANSITION_CLASS = 'theme-transition';
const TRANSITION_DURATION_MS = 250;

/** Mobile address bar color, kept in sync with `--app-canvas`. */
const THEME_COLOR: Record<ResolvedTheme, string> = {
  light: '#eef1f6',
  dark: '#0d1220',
};

const THEME_MODES: readonly ThemeMode[] = ['light', 'dark', 'auto'];

/** A mode, as presented in the theme selectors. */
export interface ThemeOption {
  readonly mode: ThemeMode;
  readonly label: string;
  readonly icon: string;
}

export const THEME_OPTIONS: readonly ThemeOption[] = [
  { mode: 'light', label: 'Light', icon: 'bi-sun-fill' },
  { mode: 'dark', label: 'Dark', icon: 'bi-moon-stars-fill' },
  { mode: 'auto', label: 'System', icon: 'bi-circle-half' },
];

function isThemeMode(value: string | null): value is ThemeMode {
  return value !== null && THEME_MODES.includes(value as ThemeMode);
}

/**
 * Light/dark theme management.
 *
 * The preference is persisted in `localStorage` and applied through the
 * `data-bs-theme` attribute on `<html>`, read by Bootstrap and the `--app-*` tokens.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly destroyRef = inject(DestroyRef);
  private readonly window = this.document.defaultView;

  // `matchMedia` is missing from some render-less environments (SSR, jsdom):
  // there the theme simply falls back to `light`.
  private readonly mediaQuery =
    typeof this.window?.matchMedia === 'function' ? this.window.matchMedia(DARK_MEDIA_QUERY) : null;
  private readonly systemPrefersDark = signal(this.mediaQuery?.matches ?? false);
  private readonly mode = signal<ThemeMode>(this.readStoredMode());

  private transitionTimer: ReturnType<typeof setTimeout> | undefined;

  /** The selected mode (`light`, `dark` or `auto`). */
  readonly themeMode = this.mode.asReadonly();

  /** The theme that is effectively applied. */
  readonly resolvedTheme = computed<ResolvedTheme>(() => {
    const mode = this.mode();
    if (mode === 'auto') {
      return this.systemPrefersDark() ? 'dark' : 'light';
    }
    return mode;
  });

  readonly isDarkMode = computed(() => this.resolvedTheme() === 'dark');

  constructor() {
    this.watchSystemPreference();

    // The first pass runs synchronously with the initial render: no animation
    // on the theme already set by the anti-FOUC script in `index.html`.
    let initial = true;
    effect(() => {
      const theme = this.resolvedTheme();
      this.applyTheme(theme, { animate: !initial });
      initial = false;
    });
  }

  /** Select a mode and persist it. */
  setThemeMode(mode: ThemeMode): void {
    this.mode.set(mode);
    this.persistMode(mode);
  }

  /** Switch between light and dark, starting from the currently visible theme. */
  toggle(): void {
    this.setThemeMode(this.isDarkMode() ? 'light' : 'dark');
  }

  /**
   * Track the system preference. The dedicated signal guarantees that `auto`
   * reacts to changes, which a `set('auto')` would not: writing the same value
   * back into a signal notifies no consumer.
   */
  private watchSystemPreference(): void {
    const mediaQuery = this.mediaQuery;
    if (!mediaQuery) {
      return;
    }

    const onChange = (event: MediaQueryListEvent): void => {
      this.systemPrefersDark.set(event.matches);
    };

    mediaQuery.addEventListener('change', onChange);
    this.destroyRef.onDestroy(() => {
      mediaQuery.removeEventListener('change', onChange);
      clearTimeout(this.transitionTimer);
    });
  }

  private applyTheme(theme: ResolvedTheme, options: { animate: boolean }): void {
    const root = this.document.documentElement;

    if (options.animate) {
      this.playTransition(root);
    }

    root.setAttribute('data-bs-theme', theme);
    this.syncThemeColor(theme);
  }

  /**
   * Fade the colors for the duration of the switch only: leaving the transition
   * permanently enabled would delay every color change in the application
   * (hovers, focus, navigation).
   */
  private playTransition(root: HTMLElement): void {
    root.classList.add(TRANSITION_CLASS);
    clearTimeout(this.transitionTimer);
    this.transitionTimer = setTimeout(() => {
      root.classList.remove(TRANSITION_CLASS);
    }, TRANSITION_DURATION_MS);
  }

  private syncThemeColor(theme: ResolvedTheme): void {
    const meta = this.document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    meta?.setAttribute('content', THEME_COLOR[theme]);
  }

  private readStoredMode(): ThemeMode {
    try {
      const stored = this.window?.localStorage.getItem(STORAGE_KEY) ?? null;
      return isThemeMode(stored) ? stored : 'auto';
    } catch {
      // localStorage unavailable (private browsing, blocked cookies).
      return 'auto';
    }
  }

  private persistMode(mode: ThemeMode): void {
    try {
      this.window?.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // The theme still applies for the current session.
    }
  }
}
