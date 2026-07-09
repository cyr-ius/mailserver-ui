import { Injectable, signal, computed, inject, effect } from '@angular/core';

export type ThemeMode = 'light' | 'dark' | 'auto';

/**
 * Service de gestion du thème (clair/sombre/auto)
 * Persiste la préférence dans localStorage
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly STORAGE_KEY = 'mailserver-ui-theme';

  private readonly _themeMode = signal<ThemeMode>(this.loadThemeFromStorage());
  private readonly _isDarkMode = computed(() => {
    const mode = this._themeMode();
    if (mode === 'auto') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return mode === 'dark';
  });

  /** Le mode de thème actuellement sélectionné (light/dark/auto) */
  readonly themeMode = computed(() => this._themeMode());

  /** True si le thème sombre doit être appliqué */
  readonly isDarkMode = this._isDarkMode;

  constructor() {
    // Appliquer le thème au démarrage
    this.applyTheme(this._isDarkMode());

    // Réappliquer le thème quand isDarkMode change
    effect(() => {
      this.applyTheme(this._isDarkMode());
    });

    // Écouter les changements de préférence système quand en mode auto
    if (this._themeMode() === 'auto') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', () => {
        // Forcer une mise à jour de isDarkMode en changeant le signal
        this._themeMode.set('auto');
      });
    }
  }

  /** Changer le mode de thème */
  setThemeMode(mode: ThemeMode): void {
    this._themeMode.set(mode);
    localStorage.setItem(this.STORAGE_KEY, mode);

    // Réenregistrer le listener si passé à auto
    if (mode === 'auto') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', () => {
        this._themeMode.set('auto');
      });
    }
  }

  /** Charger la préférence de thème depuis localStorage */
  private loadThemeFromStorage(): ThemeMode {
    const stored = localStorage.getItem(this.STORAGE_KEY) as ThemeMode | null;
    if (stored && ['light', 'dark', 'auto'].includes(stored)) {
      return stored;
    }
    return 'auto';
  }

  /** Appliquer le thème en modifiant l'attribut data-bs-theme */
  private applyTheme(isDark: boolean): void {
    const root = document.documentElement;
    if (isDark) {
      root.setAttribute('data-bs-theme', 'dark');
    } else {
      root.removeAttribute('data-bs-theme');
    }
  }
}
