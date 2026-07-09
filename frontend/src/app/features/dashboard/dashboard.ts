import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';

import { AuthService } from '../../core/auth.service';
import { MailboxesService } from '../../core/mailboxes.service';
import { Fail2banService } from '../../core/fail2ban.service';

@Component({
  selector: 'app-dashboard',
  imports: [CommonModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Dashboard {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly mailboxesService = inject(MailboxesService);
  private readonly fail2banService = inject(Fail2banService);

  protected readonly user = this.auth.user;
  protected readonly isAdmin = this.auth.isAdmin;
  protected readonly canManageMailboxes = this.auth.canManageMailboxes;
  protected readonly loggingOut = signal(false);

  // Statistics signals
  protected readonly mailboxCount = signal<number | null>(null);
  protected readonly largestMailbox = signal<{ email: string; quota: string | null } | null>(null);
  protected readonly largestQuota = signal<{ email: string; quota: string | null } | null>(null);
  protected readonly bannedIpsCount = signal<number | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);

  constructor() {
    this.loadStatistics();
  }

  /**
   * Each tile is backed by an endpoint the viewer may not be allowed to call, so
   * a tile is only loaded — and only rendered — when the role permits it. A
   * guest therefore sees an empty dashboard rather than a wall of 403s.
   */
  private async loadStatistics(): Promise<void> {
    try {
      this.loading.set(true);
      this.error.set(null);

      if (this.canManageMailboxes()) {
        await this.loadMailboxStatistics();
      }
      if (this.isAdmin()) {
        const bannedIps = await this.fail2banService.listBanned();
        this.bannedIpsCount.set(bannedIps.length);
      }
    } catch (err) {
      console.error('Error loading dashboard statistics:', err);
      this.error.set(err instanceof Error ? err.message : 'Failed to load statistics');
    } finally {
      this.loading.set(false);
    }
  }

  private async loadMailboxStatistics(): Promise<void> {
    const mailboxes = await this.mailboxesService.list();
    this.mailboxCount.set(mailboxes.length);

    if (mailboxes.length === 0) {
      return;
    }

    const mailboxesWithQuota = mailboxes.filter((m) => m.quota !== null);
    if (mailboxesWithQuota.length === 0) {
      // Get the first mailbox if none have quotas
      this.largestMailbox.set({ email: mailboxes[0].email, quota: null });
      return;
    }

    const sorted = mailboxesWithQuota.sort(
      (a, b) => this.parseQuotaBytes(b.quota!) - this.parseQuotaBytes(a.quota!),
    );
    this.largestMailbox.set({ email: sorted[0].email, quota: sorted[0].quota || null });
    this.largestQuota.set({ email: sorted[0].email, quota: sorted[0].quota || null });
  }

  private parseQuotaBytes(quota: string): number {
    const units: { [key: string]: number } = {
      B: 1,
      K: 1024,
      M: 1024 ** 2,
      G: 1024 ** 3,
      T: 1024 ** 4,
    };

    const match = quota.match(/^(\d+)\s*([KMGT]?)B?$/i);
    if (!match) return 0;

    const [, num, unit] = match;
    const multiplier = units[(unit || 'B').toUpperCase()] || 1;
    return parseInt(num) * multiplier;
  }

  protected async onLogout(): Promise<void> {
    this.loggingOut.set(true);
    try {
      await this.auth.logout();
      await this.router.navigate(['/login']);
    } finally {
      this.loggingOut.set(false);
    }
  }
}
