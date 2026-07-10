import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { THEME_OPTIONS, ThemeMode, ThemeService } from '../../core/theme.service';

/** Dropdown to pick the colour scheme, used on the login page. */
@Component({
  selector: 'app-theme-toggle',
  templateUrl: './theme-toggle.html',
  styleUrl: './theme-toggle.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ThemeToggle {
  private readonly theme = inject(ThemeService);

  protected readonly options = THEME_OPTIONS;
  protected readonly mode = this.theme.themeMode;

  /** In `auto` the trigger mirrors the resolved theme, so it always shows what is on screen. */
  protected readonly triggerIcon = computed(() => {
    const mode = this.mode();
    if (mode === 'auto') {
      return this.theme.isDarkMode() ? 'bi-moon-stars-fill' : 'bi-sun-fill';
    }
    return mode === 'dark' ? 'bi-moon-stars-fill' : 'bi-sun-fill';
  });

  protected readonly triggerLabel = computed(() => {
    const active = this.options.find((option) => option.mode === this.mode());
    return `Theme: ${active?.label ?? 'System'}`;
  });

  protected select(mode: ThemeMode): void {
    this.theme.setThemeMode(mode);
  }
}
