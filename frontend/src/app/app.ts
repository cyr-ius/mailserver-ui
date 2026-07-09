import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from './core/auth.service';
import { ThemeService } from './core/theme.service';

@Component({
  selector: 'app-root',
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './app.css',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly theme = inject(ThemeService);

  protected readonly user = this.auth.user;
  protected readonly isAuthenticated = computed(() => this.user() !== null);
  protected readonly isAdmin = this.auth.isAdmin;
  protected readonly canManageMailboxes = this.auth.canManageMailboxes;
  protected readonly sections = signal({
    mailserver: true,
    mailbox: true,
    fail2ban: true,
    settings: true,
  });
  protected readonly sidebarCollapsed = signal(false);

  constructor() {
    // Initialize theme service
  }

  protected toggleSection(section: 'mailserver' | 'mailbox' | 'fail2ban' | 'settings'): void {
    this.sections.update((state) => ({
      ...state,
      [section]: !state[section],
    }));
  }

  protected toggleSidebar(): void {
    this.sidebarCollapsed.update((state) => !state);
  }

  protected async onLogout(): Promise<void> {
    await this.auth.logout();
    await this.router.navigate(['/login']);
  }
}
