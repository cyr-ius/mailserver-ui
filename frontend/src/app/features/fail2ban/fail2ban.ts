import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { AuthService } from '../../core/auth.service';
import { Fail2banService } from '../../core/fail2ban.service';
import { BannedIp, Fail2banJail } from '../../core/fail2ban.models';

/** Displayed sections. */
type Tab = 'overview' | 'policy' | 'log';

@Component({
  selector: 'app-fail2ban',
  imports: [FormField],
  templateUrl: './fail2ban.html',
  styleUrl: './fail2ban.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Fail2ban {
  private readonly auth = inject(AuthService);
  private readonly fail2ban = inject(Fail2banService);
  private readonly router = inject(Router);

  protected readonly user = this.auth.user;
  protected readonly loggingOut = signal(false);

  protected readonly activeTab = signal<Tab>('overview');

  // ── Status / banned IPs ─────────────────────────────────────────────────────
  protected readonly jails = signal<Fail2banJail[]>([]);
  protected readonly statusLoading = signal(true);
  protected readonly statusError = signal<string | null>(null);
  protected readonly actionSuccess = signal<string | null>(null);
  protected readonly actionError = signal<string | null>(null);
  protected readonly banning = signal(false);
  protected readonly unbanningIp = signal<string | null>(null);

  /** Flat list of banned IPs across all jails. */
  protected readonly bannedIps = computed<BannedIp[]>(() =>
    this.jails().flatMap((jail) => jail.banned_ips.map((ip) => ({ ip, jail: jail.name }))),
  );
  protected readonly totalBanned = computed(() => this.bannedIps().length);

  protected readonly banModel = signal({ ip: '' });
  protected readonly banForm = form(this.banModel, (path) => {
    required(path.ip, { message: 'An IP address is required' });
  });

  // ── Ban policy ──────────────────────────────────────────────────────────────
  protected readonly policyLoading = signal(false);
  protected readonly policyLoaded = signal(false);
  protected readonly policyError = signal<string | null>(null);
  protected readonly policySuccess = signal<string | null>(null);
  protected readonly savingPolicy = signal(false);
  /** False while no fail2ban-jail.cf exists: the form shows the shipped defaults. */
  protected readonly policyConfigured = signal(false);
  protected readonly policyModel = signal({ bantime: 604800, findtime: 604800, maxretry: 6 });
  protected readonly policyForm = form(this.policyModel, (path) => {
    required(path.bantime, { message: 'A ban duration is required' });
    required(path.findtime, { message: 'A detection window is required' });
    required(path.maxretry, { message: 'A retry count is required' });
  });

  // ── Log ─────────────────────────────────────────────────────────────────────
  protected readonly logLines = signal<string[]>([]);
  protected readonly logLoading = signal(false);
  protected readonly logLoaded = signal(false);
  protected readonly logError = signal<string | null>(null);

  constructor() {
    void this.loadStatus();
  }

  protected setTab(tab: Tab): void {
    this.activeTab.set(tab);
    if (tab === 'log' && !this.logLoaded()) {
      void this.loadLog();
    } else if (tab === 'policy' && !this.policyLoaded()) {
      void this.loadPolicy();
    }
  }

  /** Reload whatever the active tab shows. */
  protected refresh(): void {
    switch (this.activeTab()) {
      case 'log':
        void this.loadLog();
        break;
      case 'policy':
        void this.loadPolicy();
        break;
      default:
        void this.loadStatus();
    }
  }

  // ── Status / banned IPs ─────────────────────────────────────────────────────

  protected async loadStatus(): Promise<void> {
    this.statusLoading.set(true);
    this.statusError.set(null);
    try {
      const status = await this.fail2ban.getStatus();
      this.jails.set(status.jails);
    } catch (err) {
      this.statusError.set(this.messageFor(err));
    } finally {
      this.statusLoading.set(false);
    }
  }

  protected onBan(): void {
    this.actionError.set(null);
    this.actionSuccess.set(null);
    submit(this.banForm, async () => {
      const ip = this.banModel().ip.trim();
      this.banning.set(true);
      try {
        await this.fail2ban.banIp(ip);
        this.actionSuccess.set(`IP ${ip} banned.`);
        this.banModel.set({ ip: '' });
        await this.loadStatus();
      } catch (err) {
        this.actionError.set(this.messageFor(err));
      } finally {
        this.banning.set(false);
      }
    });
  }

  protected async onUnban(ip: string): Promise<void> {
    if (!confirm(`Unban ${ip}?`)) {
      return;
    }
    this.actionError.set(null);
    this.actionSuccess.set(null);
    this.unbanningIp.set(ip);
    try {
      await this.fail2ban.unbanIp(ip);
      this.actionSuccess.set(`IP ${ip} unbanned.`);
      await this.loadStatus();
    } catch (err) {
      this.actionError.set(this.messageFor(err));
    } finally {
      this.unbanningIp.set(null);
    }
  }

  // ── Ban policy ──────────────────────────────────────────────────────────────

  protected async loadPolicy(): Promise<void> {
    this.policyLoading.set(true);
    this.policyError.set(null);
    try {
      const policy = await this.fail2ban.getPolicy();
      this.policyModel.set({
        bantime: policy.bantime,
        findtime: policy.findtime,
        maxretry: policy.maxretry,
      });
      this.policyConfigured.set(policy.configured);
      this.policyLoaded.set(true);
    } catch (err) {
      this.policyError.set(this.messageFor(err));
    } finally {
      this.policyLoading.set(false);
    }
  }

  protected onSavePolicy(): void {
    this.policyError.set(null);
    this.policySuccess.set(null);
    submit(this.policyForm, async () => {
      const value = this.policyModel();
      const bantime = Number(value.bantime);
      const findtime = Number(value.findtime);
      const maxretry = Number(value.maxretry);
      if (![bantime, findtime].every((seconds) => Number.isInteger(seconds) && seconds >= 60)) {
        this.policyError.set('The ban duration and detection window must be at least 60 seconds.');
        return;
      }
      if (!Number.isInteger(maxretry) || maxretry < 1 || maxretry > 100) {
        this.policyError.set('The retry count must be between 1 and 100.');
        return;
      }
      this.savingPolicy.set(true);
      try {
        const policy = await this.fail2ban.setPolicy({ bantime, findtime, maxretry });
        this.policyConfigured.set(policy.configured);
        this.policySuccess.set('Policy saved. Restart the mailserver to apply it.');
      } catch (err) {
        this.policyError.set(this.messageFor(err));
      } finally {
        this.savingPolicy.set(false);
      }
    });
  }

  // ── Log ─────────────────────────────────────────────────────────────────────

  protected async loadLog(): Promise<void> {
    this.logLoading.set(true);
    this.logError.set(null);
    try {
      const log = await this.fail2ban.getLog();
      this.logLines.set(log.lines);
      this.logLoaded.set(true);
    } catch (err) {
      this.logError.set(this.messageFor(err));
    } finally {
      this.logLoading.set(false);
    }
  }

  // ── Misc ────────────────────────────────────────────────────────────────────

  protected async onLogout(): Promise<void> {
    this.loggingOut.set(true);
    try {
      await this.auth.logout();
      await this.router.navigate(['/login']);
    } finally {
      this.loggingOut.set(false);
    }
  }

  private messageFor(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 400) {
        return 'Invalid request. Fail2ban may be disabled — check FAIL2BAN_ENABLED and the IP.';
      }
      if (err.status === 502) {
        return 'The mailserver container could not be reached. Check the Docker socket mount.';
      }
      if (err.status === 422) {
        return 'Invalid input. Check the IP address and try again.';
      }
    }
    return 'Something went wrong. Please try again.';
  }
}
