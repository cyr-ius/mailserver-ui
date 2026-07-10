import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  WritableSignal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { Fail2banService } from '../../core/fail2ban.service';
import { Fail2banStatus } from '../../core/fail2ban.models';
import { GroupsService } from '../../core/groups.service';
import { Mailbox, MailboxUsageSummary } from '../../core/mailbox.models';
import { MailboxesService } from '../../core/mailboxes.service';
import { MailserverService } from '../../core/mailserver.service';
import {
  DkimKey,
  MailStats,
  MailserverEnvironment,
  QueueSummary,
  ServiceStatus,
  TlsCertificate,
} from '../../core/mailserver.models';
import { User } from '../../core/auth.models';
import { UsersService } from '../../core/users.service';
import { mailserverErrorMessage } from '../mailserver/mailserver.utils';
import { formatAge, formatBytes } from '../../shared/format';

/** How many mailboxes the storage breakdown lists. */
const TOP_MAILBOXES = 5;

/** Days before expiry at which the TLS certificate turns from warning to danger. */
const TLS_CRITICAL_DAYS = 15;
const TLS_WARNING_DAYS = 30;

/**
 * One dashboard tile. Every tile is backed by a different endpoint, several of
 * which shell into the mailserver container and can fail on their own, so each
 * carries its own state: a broken fail2ban must not blank out the mailbox count.
 */
interface Tile<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

/** The application accounts, which two endpoints have to be joined to describe. */
interface AccountsOverview {
  users: User[];
  groupCount: number;
}

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Dashboard {
  private readonly auth = inject(AuthService);
  private readonly mailboxesService = inject(MailboxesService);
  private readonly fail2banService = inject(Fail2banService);
  private readonly mailserverService = inject(MailserverService);
  private readonly usersService = inject(UsersService);
  private readonly groupsService = inject(GroupsService);

  protected readonly user = this.auth.user;
  protected readonly isAdmin = this.auth.isAdmin;
  protected readonly canManageMailboxes = this.auth.canManageMailboxes;
  protected readonly refreshing = signal(false);

  protected readonly formatBytes = formatBytes;
  protected readonly formatAge = formatAge;

  // ── Tiles ───────────────────────────────────────────────────────────────────
  // Mailbox managers see the first two; everything else is admin-only.

  protected readonly mailboxes = this.tile<Mailbox[]>();
  protected readonly usage = this.tile<MailboxUsageSummary>();
  protected readonly queue = this.tile<QueueSummary>();
  protected readonly fail2ban = this.tile<Fail2banStatus>();
  protected readonly tls = this.tile<TlsCertificate>();
  protected readonly dkim = this.tile<DkimKey[]>();
  protected readonly services = this.tile<ServiceStatus[]>();
  protected readonly stats = this.tile<MailStats>();
  protected readonly environment = this.tile<MailserverEnvironment>();
  protected readonly accounts = this.tile<AccountsOverview>();

  // ── Derived views ───────────────────────────────────────────────────────────

  /** Every domain the mailboxes span; the mailserver hosts exactly these. */
  protected readonly domains = computed(() => {
    const mailboxes = this.mailboxes().data;
    return mailboxes ? [...new Set(mailboxes.map((m) => m.domain))].sort() : [];
  });

  /** The heaviest mailboxes, already ordered by the API. */
  protected readonly topMailboxes = computed(
    () => this.usage().data?.mailboxes.slice(0, TOP_MAILBOXES) ?? [],
  );

  /** Share of the aggregate quota consumed, or null when any account is unlimited. */
  protected readonly storagePercent = computed(() => {
    const summary = this.usage().data;
    if (!summary?.total_limit_bytes) {
      return null;
    }
    return Math.min(Math.round((summary.total_used_bytes / summary.total_limit_bytes) * 100), 100);
  });

  /**
   * Which hosted domains sign their outgoing mail. Needs both tiles, so it stays
   * null until each has loaded; a domain without a DKIM key silently loses
   * deliverability, which is exactly what this surfaces.
   */
  protected readonly dkimCoverage = computed(() => {
    const keys = this.dkim().data;
    const domains = this.domains();
    if (!keys || domains.length === 0) {
      return null;
    }
    const signed = new Set(keys.map((key) => key.domain));
    const missing = domains.filter((domain) => !signed.has(domain));
    return { signed: domains.length - missing.length, total: domains.length, missing };
  });

  /** Messages Postfix has postponed: the count that actually warrants attention. */
  protected readonly deferredCount = computed(() => this.queue().data?.counts['deferred'] ?? 0);

  /** Arrival time of the oldest queued message, the age of the backlog. */
  protected readonly oldestQueued = computed(() => {
    const messages = this.queue().data?.messages ?? [];
    const arrivals = messages.map((m) => m.arrival_time).filter((a): a is string => a !== null);
    return arrivals.length ? arrivals.reduce((a, b) => (a < b ? a : b)) : null;
  });

  protected readonly queueCountEntries = computed(() =>
    Object.entries(this.queue().data?.counts ?? {}),
  );

  protected readonly bannedIpsCount = computed(() =>
    (this.fail2ban().data?.jails ?? []).reduce((total, jail) => total + jail.currently_banned, 0),
  );

  /** Jails that currently hold at least one IP, most populated first. */
  protected readonly activeJails = computed(() =>
    (this.fail2ban().data?.jails ?? [])
      .filter((jail) => jail.currently_banned > 0)
      .sort((a, b) => b.currently_banned - a.currently_banned),
  );

  /** Bootstrap contextual class reflecting how close the certificate is to expiry. */
  protected readonly tlsClass = computed(() => {
    const days = this.tls().data?.days_remaining;
    if (days === null || days === undefined) {
      return 'text-body-secondary';
    }
    if (days < 0) {
      return 'text-danger';
    }
    if (days < TLS_CRITICAL_DAYS) {
      return 'text-danger';
    }
    return days < TLS_WARNING_DAYS ? 'text-warning' : 'text-success';
  });

  /** Processes supervisor gave up on. Excludes the many a disabled feature leaves STOPPED. */
  protected readonly servicesFailed = computed(() =>
    (this.services().data ?? []).filter((service) => service.failed),
  );

  protected readonly servicesRunning = computed(() =>
    (this.services().data ?? []).filter((service) => service.running),
  );

  /** Running first, then failed, then the merely disabled ones. */
  protected readonly sortedServices = computed(() =>
    [...(this.services().data ?? [])].sort((a, b) => {
      const rank = (service: ServiceStatus) => (service.running ? 0 : service.failed ? 1 : 2);
      return rank(a) - rank(b) || a.name.localeCompare(b.name);
    }),
  );

  /** Contradictions between the container's environment variables, worst first. */
  protected readonly environmentWarnings = computed(() => this.environment().data?.warnings ?? []);

  protected readonly hasDangerWarning = computed(() =>
    this.environmentWarnings().some((warning) => warning.level === 'danger'),
  );

  protected readonly oidcUserCount = computed(
    () => (this.accounts().data?.users ?? []).filter((u) => u.provider === 'oidc').length,
  );

  protected readonly adminCount = computed(
    () => (this.accounts().data?.users ?? []).filter((u) => u.effective_role === 'admin').length,
  );

  constructor() {
    void this.loadAll();
  }

  /** Reload every tile the current role is allowed to see. */
  protected async refresh(): Promise<void> {
    this.refreshing.set(true);
    try {
      await this.loadAll();
    } finally {
      this.refreshing.set(false);
    }
  }

  private tile<T>(): WritableSignal<Tile<T>> {
    return signal<Tile<T>>({ data: null, error: null, loading: true });
  }

  /**
   * Load one tile, trapping its failure inside it. Never rejects: a tile that
   * cannot load renders an inline message and leaves its neighbours alone.
   */
  private async load<T>(tile: WritableSignal<Tile<T>>, fetch: () => Promise<T>): Promise<void> {
    tile.set({ data: null, error: null, loading: true });
    try {
      tile.set({ data: await fetch(), error: null, loading: false });
    } catch (err) {
      console.error('Dashboard tile failed to load:', err);
      tile.set({ data: null, error: mailserverErrorMessage(err), loading: false });
    }
  }

  /**
   * Each tile is backed by an endpoint the viewer may not be allowed to call, so
   * a tile is only loaded — and only rendered — when the role permits it. A
   * guest therefore sees an empty dashboard rather than a wall of 403s.
   */
  private async loadAll(): Promise<void> {
    const pending: Promise<void>[] = [];

    if (this.canManageMailboxes()) {
      pending.push(
        this.load(this.mailboxes, () => this.mailboxesService.list()),
        this.load(this.usage, () => this.mailboxesService.usage()),
      );
    }

    if (this.isAdmin()) {
      pending.push(
        this.load(this.queue, () => this.mailserverService.getQueue()),
        this.load(this.fail2ban, () => this.fail2banService.getStatus()),
        this.load(this.tls, () => this.mailserverService.getTlsCertificate()),
        this.load(this.dkim, () => this.mailserverService.listDkimKeys()),
        this.load(this.services, () => this.mailserverService.listServices()),
        this.load(this.stats, () => this.mailserverService.getMailStats()),
        this.load(this.environment, () => this.mailserverService.getEnvironment()),
        this.load(this.accounts, async () => {
          const [users, groups] = await Promise.all([
            this.usersService.list(),
            this.groupsService.list(),
          ]);
          return { users, groupCount: groups.length };
        }),
      );
    }

    await Promise.all(pending);
  }
}
