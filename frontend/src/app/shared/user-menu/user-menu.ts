import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { roleLabel } from '../../core/auth.models';
import { THEME_OPTIONS, ThemeMode, ThemeService } from '../../core/theme.service';

/** Header dropdown carrying the session identity, the colour scheme and sign-out. */
@Component({
  selector: 'app-user-menu',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './user-menu.html',
  styleUrl: './user-menu.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UserMenu {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly theme = inject(ThemeService);

  protected readonly user = this.auth.user;
  protected readonly themeOptions = THEME_OPTIONS;
  protected readonly mode = this.theme.themeMode;
  protected readonly roleLabel = roleLabel;

  protected selectTheme(mode: ThemeMode): void {
    this.theme.setThemeMode(mode);
  }

  protected async onLogout(): Promise<void> {
    await this.auth.logout();
    await this.router.navigate(['/login']);
  }
}
