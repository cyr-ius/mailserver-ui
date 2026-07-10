import {
  ChangeDetectionStrategy,
  Component,
  DOCUMENT,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from './core/auth.service';
import { SessionExpiredModal } from './shared/session-expired-modal/session-expired-modal';
import { UserMenu } from './shared/user-menu/user-menu';

const SIDEBAR_STORAGE_KEY = 'mailserver-ui-sidebar-collapsed';

/** Matches the `md` breakpoint below which the sidebar becomes an overlay. */
const DESKTOP_MIN_WIDTH = 768;

@Component({
  selector: 'app-root',
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    SessionExpiredModal,
    UserMenu,
  ],
  templateUrl: './app.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './app.css',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly window = inject(DOCUMENT).defaultView;

  protected readonly isAuthenticated = computed(() => this.auth.user() !== null);
  protected readonly isAdmin = this.auth.isAdmin;
  protected readonly canManageMailboxes = this.auth.canManageMailboxes;
  protected readonly sections = signal({
    mailbox: true,
    mailserver: false,
    fail2ban: false,
    settings: false,
  });
  protected readonly sidebarCollapsed = signal(this.readCollapsed());

  protected toggleSection(section: 'mailbox' | 'mailserver' | 'fail2ban' | 'settings'): void {
    // On the rail the submenu is a hover flyout, so toggling it would look inert.
    // Clicking an icon expands the sidebar onto that section instead.
    if (this.sidebarCollapsed()) {
      this.toggleSidebar();
      this.sections.update((state) => ({ ...state, [section]: true }));
      return;
    }

    this.sections.update((state) => ({
      ...state,
      [section]: !state[section],
    }));
  }

  protected toggleSidebar(): void {
    const collapsed = !this.sidebarCollapsed();
    this.sidebarCollapsed.set(collapsed);
    this.persistCollapsed(collapsed);
  }

  /** On phones the sidebar overlays the page, so it starts closed whatever was stored. */
  private readCollapsed(): boolean {
    const width = this.window?.innerWidth ?? DESKTOP_MIN_WIDTH;
    if (width < DESKTOP_MIN_WIDTH) {
      return true;
    }
    try {
      return this.window?.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  }

  private persistCollapsed(collapsed: boolean): void {
    try {
      this.window?.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(collapsed));
    } catch {
      // The collapsed state still applies for the current session.
    }
  }
}
