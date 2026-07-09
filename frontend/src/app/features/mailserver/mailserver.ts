import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, NavigationEnd } from '@angular/router';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { AuthService } from '../../core/auth.service';
import { MailserverService } from '../../core/mailserver.service';
import {
  DkimKey,
  DomainDnsRecords,
  DovecotMaster,
  MailserverEnvironment,
  PostfixMasterOverride,
  PostfixOverride,
  QueueMessage,
  RegexAlias,
  RelayExclusion,
  RelayHost,
  Restriction,
  RestrictionKind,
  SieveScope,
  SystemAlias,
  TlsCertificate,
} from '../../core/mailserver.models';

/** Editable configuration tabs. */
type Tab =
  | 'relay'
  | 'postfix'
  | 'dovecot'
  | 'aliases'
  | 'sieve'
  | 'dkim'
  | 'dns'
  | 'restrictions'
  | 'queue'
  | 'tls'
  | 'environment'
  | 'logs';

@Component({
  selector: 'app-mailserver',
  imports: [FormField],
  templateUrl: './mailserver.html',
  styleUrl: './mailserver.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Mailserver {
  private readonly auth = inject(AuthService);
  private readonly mailserver = inject(MailserverService);
  private readonly router = inject(Router);

  protected readonly user = this.auth.user;
  protected readonly loggingOut = signal(false);

  protected readonly activeTab = signal<Tab>('relay');

  // ── SMTP relays ───────────────────────────────────────────────────────────────
  protected readonly relays = signal<RelayHost[]>([]);
  protected readonly relaysLoading = signal(true);
  protected readonly relaysError = signal<string | null>(null);
  protected readonly relaySuccess = signal<string | null>(null);
  protected readonly creatingRelay = signal(false);
  protected readonly createRelayError = signal<string | null>(null);
  protected readonly deletingSender = signal<string | null>(null);
  protected readonly relayModel = signal({
    sender: '',
    host: '',
    port: 587,
    username: '',
    password: '',
  });
  protected readonly relayForm = form(this.relayModel, (path) => {
    required(path.sender, { message: 'A sender domain is required' });
    required(path.host, { message: 'A relay host is required' });
  });

  // ── Global relay exclusions ─────────────────────────────────────────────────
  protected readonly exclusions = signal<RelayExclusion[]>([]);
  protected readonly addingExclusion = signal(false);
  protected readonly deletingExclusion = signal<string | null>(null);
  protected readonly exclusionModel = signal({ sender: '' });
  protected readonly exclusionForm = form(this.exclusionModel, (path) => {
    required(path.sender, { message: 'A sender domain is required' });
  });

  // ── Postfix overrides ─────────────────────────────────────────────────────────
  protected readonly overrides = signal<PostfixOverride[]>([]);
  protected readonly masterOverrides = signal<PostfixMasterOverride[]>([]);
  protected readonly postfixLoading = signal(false);
  protected readonly postfixLoaded = signal(false);
  protected readonly postfixError = signal<string | null>(null);
  protected readonly postfixSuccess = signal<string | null>(null);
  protected readonly savingPostfix = signal(false);
  protected readonly savingPostfixMaster = signal(false);

  // ── DKIM ──────────────────────────────────────────────────────────────────────
  protected readonly dkimKeys = signal<DkimKey[]>([]);
  protected readonly dkimLoading = signal(false);
  protected readonly dkimLoaded = signal(false);
  protected readonly dkimError = signal<string | null>(null);
  protected readonly dkimSuccess = signal<string | null>(null);
  protected readonly generatingDkim = signal(false);
  protected readonly dkimModel = signal({ domain: '', selector: 'mail', keySize: '2048' });
  protected readonly dkimForm = form(this.dkimModel, (path) => {
    required(path.selector, { message: 'A selector is required' });
  });

  // ── DNS records ───────────────────────────────────────────────────────────────
  protected readonly dnsRecords = signal<DomainDnsRecords[]>([]);
  protected readonly dnsLoading = signal(false);
  protected readonly dnsLoaded = signal(false);
  protected readonly dnsError = signal<string | null>(null);

  // ── Send/receive restrictions ─────────────────────────────────────────────────
  protected readonly restrictionKind = signal<RestrictionKind>('send');
  protected readonly restrictions = signal<Restriction[]>([]);
  protected readonly restrictionsLoading = signal(false);
  protected readonly restrictionsLoaded = signal(false);
  protected readonly restrictionsError = signal<string | null>(null);
  protected readonly restrictionsSuccess = signal<string | null>(null);
  protected readonly addingRestriction = signal(false);
  protected readonly deletingRestriction = signal<string | null>(null);
  protected readonly restrictionModel = signal({ address: '' });
  protected readonly restrictionForm = form(this.restrictionModel, (path) => {
    required(path.address, { message: 'An address is required' });
  });

  // ── Dovecot master accounts ─────────────────────────────────────────────────
  protected readonly masters = signal<DovecotMaster[]>([]);
  protected readonly mastersLoading = signal(false);
  protected readonly mastersLoaded = signal(false);
  protected readonly mastersError = signal<string | null>(null);
  protected readonly mastersSuccess = signal<string | null>(null);
  protected readonly creatingMaster = signal(false);
  protected readonly deletingMaster = signal<string | null>(null);
  protected readonly masterModel = signal({ name: '', password: '' });
  protected readonly masterForm = form(this.masterModel, (path) => {
    required(path.name, { message: 'A name is required' });
    required(path.password, { message: 'A password is required' });
  });

  // ── Dovecot configuration override ──────────────────────────────────────────
  protected readonly dovecotConfig = signal('');
  protected readonly savingDovecotConfig = signal(false);

  // ── System and regex aliases ────────────────────────────────────────────────
  protected readonly systemAliases = signal<SystemAlias[]>([]);
  protected readonly regexAliases = signal<RegexAlias[]>([]);
  protected readonly aliasesLoading = signal(false);
  protected readonly aliasesLoaded = signal(false);
  protected readonly aliasesError = signal<string | null>(null);
  protected readonly aliasesSuccess = signal<string | null>(null);
  protected readonly addingSystemAlias = signal(false);
  protected readonly addingRegexAlias = signal(false);
  protected readonly deletingAlias = signal<string | null>(null);
  protected readonly systemAliasModel = signal({ name: '', targets: '' });
  protected readonly systemAliasForm = form(this.systemAliasModel, (path) => {
    required(path.name, { message: 'An alias name is required' });
    required(path.targets, { message: 'At least one destination is required' });
  });
  protected readonly regexAliasModel = signal({ pattern: '', targets: '' });
  protected readonly regexAliasForm = form(this.regexAliasModel, (path) => {
    required(path.pattern, { message: 'A pattern is required' });
    required(path.targets, { message: 'At least one destination is required' });
  });

  // ── Global Sieve scripts ────────────────────────────────────────────────────
  protected readonly sieveScope = signal<SieveScope>('before');
  protected readonly sieveContent = signal('');
  protected readonly sieveLoading = signal(false);
  protected readonly sieveLoaded = signal(false);
  protected readonly sieveError = signal<string | null>(null);
  protected readonly sieveSuccess = signal<string | null>(null);
  protected readonly savingSieve = signal(false);

  // ── Postfix mail queue ──────────────────────────────────────────────────────
  protected readonly queue = signal<QueueMessage[]>([]);
  protected readonly queueCounts = signal<Record<string, number>>({});
  protected readonly queueLoading = signal(false);
  protected readonly queueLoaded = signal(false);
  protected readonly queueError = signal<string | null>(null);
  protected readonly queueSuccess = signal<string | null>(null);
  protected readonly flushingQueue = signal(false);
  protected readonly deletingQueueId = signal<string | null>(null);
  protected readonly queueCountEntries = computed(() => Object.entries(this.queueCounts()));

  // ── TLS certificate ─────────────────────────────────────────────────────────
  protected readonly tlsCertificate = signal<TlsCertificate | null>(null);
  protected readonly tlsLoading = signal(false);
  protected readonly tlsLoaded = signal(false);
  protected readonly tlsError = signal<string | null>(null);

  /** Bootstrap contextual class reflecting how close the certificate is to expiry. */
  protected readonly tlsExpiryClass = computed(() => {
    const days = this.tlsCertificate()?.days_remaining;
    if (days === null || days === undefined) {
      return 'text-bg-secondary';
    }
    if (days < 0) {
      return 'text-bg-danger';
    }
    return days < 15 ? 'text-bg-warning' : 'text-bg-success';
  });

  // ── Mailserver environment ──────────────────────────────────────────────────
  protected readonly environment = signal<MailserverEnvironment | null>(null);
  protected readonly environmentLoading = signal(false);
  protected readonly environmentLoaded = signal(false);
  protected readonly environmentError = signal<string | null>(null);
  protected readonly environmentEntries = computed(() =>
    Object.entries(this.environment()?.variables ?? {}),
  );

  // ── Mail log ────────────────────────────────────────────────────────────────
  protected readonly mailLog = signal<string[]>([]);
  protected readonly logLoading = signal(false);
  protected readonly logLoaded = signal(false);
  protected readonly logError = signal<string | null>(null);

  protected readonly hasOverrides = computed(() => this.overrides().length > 0);

  constructor() {
    void this.loadRelays();
    this.setTabFromUrl(this.router.url);
    this.router.events.subscribe((event) => {
      if (event instanceof NavigationEnd) {
        this.setTabFromUrl(event.urlAfterRedirects);
      }
    });
  }

  protected setTab(tab: Tab): void {
    this.activeTab.set(tab);
    if (tab === 'postfix' && !this.postfixLoaded()) {
      void this.loadPostfix();
    } else if (tab === 'dkim' && !this.dkimLoaded()) {
      void this.loadDkim();
    } else if (tab === 'dns' && !this.dnsLoaded()) {
      void this.loadDns();
    } else if (tab === 'restrictions' && !this.restrictionsLoaded()) {
      void this.loadRestrictions();
    } else if (tab === 'dovecot' && !this.mastersLoaded()) {
      void this.loadDovecot();
    } else if (tab === 'aliases' && !this.aliasesLoaded()) {
      void this.loadAliases();
    } else if (tab === 'sieve' && !this.sieveLoaded()) {
      void this.loadSieve();
    } else if (tab === 'queue' && !this.queueLoaded()) {
      void this.loadQueue();
    } else if (tab === 'tls' && !this.tlsLoaded()) {
      void this.loadTls();
    } else if (tab === 'environment' && !this.environmentLoaded()) {
      void this.loadEnvironment();
    } else if (tab === 'logs' && !this.logLoaded()) {
      void this.loadLog();
    }
  }

  private setTabFromUrl(url: string): void {
    const path = url.split('/').filter(Boolean)[1] || 'relay';
    switch (path) {
      case 'postfix':
      case 'dkim':
      case 'dns':
      case 'restrictions':
      case 'dovecot':
      case 'aliases':
      case 'sieve':
      case 'queue':
      case 'tls':
      case 'environment':
      case 'logs':
        this.setTab(path);
        break;
      default:
        this.setTab('relay');
    }
  }

  // ── SMTP relays ───────────────────────────────────────────────────────────────

  private async loadRelays(): Promise<void> {
    this.relaysLoading.set(true);
    this.relaysError.set(null);
    try {
      const [relays, exclusions] = await Promise.all([
        this.mailserver.listRelays(),
        this.mailserver.listRelayExclusions(),
      ]);
      this.relays.set(relays);
      this.exclusions.set(exclusions);
    } catch {
      this.relaysError.set('Unable to load the SMTP relays.');
    } finally {
      this.relaysLoading.set(false);
    }
  }

  protected onCreateRelay(): void {
    this.createRelayError.set(null);
    this.relaySuccess.set(null);
    submit(this.relayForm, async () => {
      const value = this.relayModel();
      const sender = value.sender.trim().toLowerCase();
      if (!sender.includes('@')) {
        this.createRelayError.set('The sender must be a domain (e.g. @example.com).');
        return;
      }
      const port = Number(value.port);
      if (!Number.isInteger(port) || port < 1 || port > 65535) {
        this.createRelayError.set('The port must be between 1 and 65535.');
        return;
      }
      this.creatingRelay.set(true);
      try {
        await this.mailserver.createRelay({
          sender,
          host: value.host.trim(),
          port,
          username: value.username.trim() || null,
          password: value.password || null,
        });
        this.relaySuccess.set(`Relay for ${sender} saved.`);
        this.relayModel.set({ sender: '', host: '', port: 587, username: '', password: '' });
        await this.loadRelays();
      } catch (err) {
        this.createRelayError.set(this.messageFor(err));
      } finally {
        this.creatingRelay.set(false);
      }
    });
  }

  protected async onDeleteRelay(relay: RelayHost): Promise<void> {
    if (!confirm(`Delete the SMTP relay for ${relay.sender}?`)) {
      return;
    }
    this.relaysError.set(null);
    this.relaySuccess.set(null);
    this.deletingSender.set(relay.sender);
    try {
      await this.mailserver.deleteRelay(relay.sender);
      this.relaySuccess.set(`Relay for ${relay.sender} deleted.`);
      await this.loadRelays();
    } catch (err) {
      this.relaysError.set(this.messageFor(err));
    } finally {
      this.deletingSender.set(null);
    }
  }

  // ── Global relay exclusions ─────────────────────────────────────────────────

  protected onAddExclusion(): void {
    this.relaysError.set(null);
    this.relaySuccess.set(null);
    submit(this.exclusionForm, async () => {
      const sender = this.exclusionModel().sender.trim().toLowerCase();
      if (!sender.includes('@')) {
        this.relaysError.set('The sender must be a domain (e.g. @example.com).');
        return;
      }
      this.addingExclusion.set(true);
      try {
        await this.mailserver.createRelayExclusion(sender);
        this.relaySuccess.set(`${sender} will no longer use the global relay.`);
        this.exclusionModel.set({ sender: '' });
        await this.loadRelays();
      } catch (err) {
        this.relaysError.set(this.messageFor(err));
      } finally {
        this.addingExclusion.set(false);
      }
    });
  }

  protected async onDeleteExclusion(exclusion: RelayExclusion): Promise<void> {
    if (!confirm(`Send mail from ${exclusion.sender} through the global relay again?`)) {
      return;
    }
    this.relaysError.set(null);
    this.relaySuccess.set(null);
    this.deletingExclusion.set(exclusion.sender);
    try {
      await this.mailserver.deleteRelayExclusion(exclusion.sender);
      this.relaySuccess.set(`Exclusion for ${exclusion.sender} removed.`);
      await this.loadRelays();
    } catch (err) {
      this.relaysError.set(this.messageFor(err));
    } finally {
      this.deletingExclusion.set(null);
    }
  }

  // ── Postfix overrides ─────────────────────────────────────────────────────────

  private async loadPostfix(): Promise<void> {
    this.postfixLoading.set(true);
    this.postfixError.set(null);
    try {
      const [main, master] = await Promise.all([
        this.mailserver.getPostfixOverrides(),
        this.mailserver.getPostfixMasterOverrides(),
      ]);
      this.overrides.set(main);
      this.masterOverrides.set(master);
      this.postfixLoaded.set(true);
    } catch {
      this.postfixError.set('Unable to load the Postfix overrides.');
    } finally {
      this.postfixLoading.set(false);
    }
  }

  protected addOverride(): void {
    this.overrides.update((list) => [...list, { key: '', value: '' }]);
  }

  protected removeOverride(index: number): void {
    this.overrides.update((list) => list.filter((_, i) => i !== index));
  }

  protected onOverrideKey(index: number, event: Event): void {
    const key = (event.target as HTMLInputElement).value;
    this.overrides.update((list) => list.map((o, i) => (i === index ? { ...o, key } : o)));
  }

  protected onOverrideValue(index: number, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.overrides.update((list) => list.map((o, i) => (i === index ? { ...o, value } : o)));
  }

  protected async onSavePostfix(): Promise<void> {
    this.postfixError.set(null);
    this.postfixSuccess.set(null);
    const cleaned = this.overrides()
      .map((o) => ({ key: o.key.trim(), value: o.value.trim() }))
      .filter((o) => o.key);
    const invalid = cleaned.find((o) => !/^[A-Za-z0-9_]+$/.test(o.key));
    if (invalid) {
      this.postfixError.set(`Invalid Postfix parameter name: "${invalid.key}".`);
      return;
    }
    this.savingPostfix.set(true);
    try {
      this.overrides.set(await this.mailserver.setPostfixOverrides(cleaned));
      this.postfixSuccess.set('Postfix overrides saved. Restart the mailserver to apply them.');
    } catch (err) {
      this.postfixError.set(this.messageFor(err));
    } finally {
      this.savingPostfix.set(false);
    }
  }

  protected addMasterOverride(): void {
    this.masterOverrides.update((list) => [...list, { key: '', value: '' }]);
  }

  protected removeMasterOverride(index: number): void {
    this.masterOverrides.update((list) => list.filter((_, i) => i !== index));
  }

  protected onMasterOverrideKey(index: number, event: Event): void {
    const key = (event.target as HTMLInputElement).value;
    this.masterOverrides.update((list) => list.map((o, i) => (i === index ? { ...o, key } : o)));
  }

  protected onMasterOverrideValue(index: number, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.masterOverrides.update((list) => list.map((o, i) => (i === index ? { ...o, value } : o)));
  }

  protected async onSavePostfixMaster(): Promise<void> {
    this.postfixError.set(null);
    this.postfixSuccess.set(null);
    const cleaned = this.masterOverrides()
      .map((o) => ({ key: o.key.trim(), value: o.value.trim() }))
      .filter((o) => o.key);
    const invalid = cleaned.find((o) => !/^[A-Za-z0-9_.-]+\/[a-z]+\/[A-Za-z0-9_]+$/.test(o.key));
    if (invalid) {
      this.postfixError.set(
        `Invalid master parameter: "${invalid.key}". Expected service/type/parameter.`,
      );
      return;
    }
    this.savingPostfixMaster.set(true);
    try {
      this.masterOverrides.set(await this.mailserver.setPostfixMasterOverrides(cleaned));
      this.postfixSuccess.set(
        'Postfix master overrides saved. Restart the mailserver to apply them.',
      );
    } catch (err) {
      this.postfixError.set(this.messageFor(err));
    } finally {
      this.savingPostfixMaster.set(false);
    }
  }

  // ── DKIM ──────────────────────────────────────────────────────────────────────

  private async loadDkim(): Promise<void> {
    this.dkimLoading.set(true);
    this.dkimError.set(null);
    try {
      this.dkimKeys.set(await this.mailserver.listDkimKeys());
      this.dkimLoaded.set(true);
    } catch {
      this.dkimError.set('Unable to load the DKIM records.');
    } finally {
      this.dkimLoading.set(false);
    }
  }

  protected onGenerateDkim(): void {
    this.dkimError.set(null);
    this.dkimSuccess.set(null);
    submit(this.dkimForm, async () => {
      const value = this.dkimModel();
      this.generatingDkim.set(true);
      try {
        this.dkimKeys.set(
          await this.mailserver.generateDkim({
            domain: value.domain.trim().toLowerCase() || null,
            selector: value.selector.trim() || 'mail',
            key_size: parseInt(value.keySize) as 1024 | 2048 | 4096,
          }),
        );
        this.dkimLoaded.set(true);
        this.dkimSuccess.set('DKIM keys generated.');
      } catch (err) {
        this.dkimError.set(this.messageFor(err));
      } finally {
        this.generatingDkim.set(false);
      }
    });
  }

  protected async copyToClipboard(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard access can be denied; ignore silently.
    }
  }

  // ── Send/receive restrictions ─────────────────────────────────────────────────

  private async loadRestrictions(): Promise<void> {
    this.restrictionsLoading.set(true);
    this.restrictionsError.set(null);
    try {
      this.restrictions.set(await this.mailserver.listRestrictions(this.restrictionKind()));
      this.restrictionsLoaded.set(true);
    } catch {
      this.restrictionsError.set('Unable to load the restrictions.');
    } finally {
      this.restrictionsLoading.set(false);
    }
  }

  protected setRestrictionKind(kind: RestrictionKind): void {
    if (this.restrictionKind() === kind) {
      return;
    }
    this.restrictionKind.set(kind);
    this.restrictionsSuccess.set(null);
    void this.loadRestrictions();
  }

  protected onAddRestriction(): void {
    this.restrictionsError.set(null);
    this.restrictionsSuccess.set(null);
    submit(this.restrictionForm, async () => {
      const address = this.restrictionModel().address.trim().toLowerCase();
      if (!address.includes('@')) {
        this.restrictionsError.set('The target must be an address or a domain (@example.com).');
        return;
      }
      this.addingRestriction.set(true);
      try {
        await this.mailserver.addRestriction(this.restrictionKind(), address);
        this.restrictionsSuccess.set(`${address} restricted.`);
        this.restrictionModel.set({ address: '' });
        await this.loadRestrictions();
      } catch (err) {
        this.restrictionsError.set(this.messageFor(err));
      } finally {
        this.addingRestriction.set(false);
      }
    });
  }

  protected async onDeleteRestriction(restriction: Restriction): Promise<void> {
    if (!confirm(`Remove the ${restriction.kind} restriction for ${restriction.address}?`)) {
      return;
    }
    this.restrictionsError.set(null);
    this.restrictionsSuccess.set(null);
    this.deletingRestriction.set(restriction.address);
    try {
      await this.mailserver.deleteRestriction(restriction.kind, restriction.address);
      this.restrictionsSuccess.set(`${restriction.address} removed.`);
      await this.loadRestrictions();
    } catch (err) {
      this.restrictionsError.set(this.messageFor(err));
    } finally {
      this.deletingRestriction.set(null);
    }
  }

  // ── DNS records ───────────────────────────────────────────────────────────────

  private async loadDns(): Promise<void> {
    this.dnsLoading.set(true);
    this.dnsError.set(null);
    try {
      this.dnsRecords.set(await this.mailserver.listDnsRecords());
      this.dnsLoaded.set(true);
    } catch {
      this.dnsError.set('Unable to load the DNS records.');
    } finally {
      this.dnsLoading.set(false);
    }
  }

  // ── Dovecot master accounts and configuration ───────────────────────────────

  private async loadDovecot(): Promise<void> {
    this.mastersLoading.set(true);
    this.mastersError.set(null);
    try {
      const [masters, config] = await Promise.all([
        this.mailserver.listDovecotMasters(),
        this.mailserver.getDovecotConfig(),
      ]);
      this.masters.set(masters);
      this.dovecotConfig.set(config.content);
      this.mastersLoaded.set(true);
    } catch {
      this.mastersError.set('Unable to load the Dovecot configuration.');
    } finally {
      this.mastersLoading.set(false);
    }
  }

  protected onDovecotConfig(event: Event): void {
    this.dovecotConfig.set((event.target as HTMLTextAreaElement).value);
  }

  protected async onSaveDovecotConfig(): Promise<void> {
    this.mastersError.set(null);
    this.mastersSuccess.set(null);
    this.savingDovecotConfig.set(true);
    try {
      const config = await this.mailserver.setDovecotConfig(this.dovecotConfig());
      this.dovecotConfig.set(config.content);
      this.mastersSuccess.set('Dovecot configuration saved. Restart the mailserver to apply it.');
    } catch (err) {
      this.mastersError.set(this.messageFor(err));
    } finally {
      this.savingDovecotConfig.set(false);
    }
  }

  protected onCreateMaster(): void {
    this.mastersError.set(null);
    this.mastersSuccess.set(null);
    submit(this.masterForm, async () => {
      const value = this.masterModel();
      const name = value.name.trim().toLowerCase();
      if (name.includes('@')) {
        this.mastersError.set("A master name must not contain '@'.");
        return;
      }
      this.creatingMaster.set(true);
      try {
        await this.mailserver.createDovecotMaster({ name, password: value.password });
        this.mastersSuccess.set(`Master account ${name} created.`);
        this.masterModel.set({ name: '', password: '' });
        await this.loadDovecot();
      } catch (err) {
        this.mastersError.set(this.messageFor(err));
      } finally {
        this.creatingMaster.set(false);
      }
    });
  }

  protected async onDeleteMaster(master: DovecotMaster): Promise<void> {
    if (!confirm(`Delete the Dovecot master account ${master.name}?`)) {
      return;
    }
    this.mastersError.set(null);
    this.mastersSuccess.set(null);
    this.deletingMaster.set(master.name);
    try {
      await this.mailserver.deleteDovecotMaster(master.name);
      this.mastersSuccess.set(`Master account ${master.name} deleted.`);
      await this.loadDovecot();
    } catch (err) {
      this.mastersError.set(this.messageFor(err));
    } finally {
      this.deletingMaster.set(null);
    }
  }

  // ── System and regex aliases ────────────────────────────────────────────────

  private async loadAliases(): Promise<void> {
    this.aliasesLoading.set(true);
    this.aliasesError.set(null);
    try {
      const [system, regex] = await Promise.all([
        this.mailserver.listSystemAliases(),
        this.mailserver.listRegexAliases(),
      ]);
      this.systemAliases.set(system);
      this.regexAliases.set(regex);
      this.aliasesLoaded.set(true);
    } catch {
      this.aliasesError.set('Unable to load the aliases.');
    } finally {
      this.aliasesLoading.set(false);
    }
  }

  /** Split a comma-separated destination list into clean addresses. */
  private parseTargets(raw: string): string[] {
    return raw
      .split(',')
      .map((target) => target.trim())
      .filter(Boolean);
  }

  protected onAddSystemAlias(): void {
    this.aliasesError.set(null);
    this.aliasesSuccess.set(null);
    submit(this.systemAliasForm, async () => {
      const value = this.systemAliasModel();
      const name = value.name.trim().toLowerCase();
      if (name.includes('@')) {
        this.aliasesError.set('A system alias is a local name, without a domain.');
        return;
      }
      const targets = this.parseTargets(value.targets);
      if (targets.length === 0) {
        this.aliasesError.set('At least one destination is required.');
        return;
      }
      this.addingSystemAlias.set(true);
      try {
        await this.mailserver.createSystemAlias(name, targets);
        this.aliasesSuccess.set(`System alias ${name} created.`);
        this.systemAliasModel.set({ name: '', targets: '' });
        await this.loadAliases();
      } catch (err) {
        this.aliasesError.set(this.messageFor(err));
      } finally {
        this.addingSystemAlias.set(false);
      }
    });
  }

  protected async onDeleteSystemAlias(alias: SystemAlias): Promise<void> {
    if (!confirm(`Delete the system alias ${alias.name}?`)) {
      return;
    }
    this.aliasesError.set(null);
    this.aliasesSuccess.set(null);
    this.deletingAlias.set(alias.name);
    try {
      await this.mailserver.deleteSystemAlias(alias.name);
      this.aliasesSuccess.set(`System alias ${alias.name} deleted.`);
      await this.loadAliases();
    } catch (err) {
      this.aliasesError.set(this.messageFor(err));
    } finally {
      this.deletingAlias.set(null);
    }
  }

  protected onAddRegexAlias(): void {
    this.aliasesError.set(null);
    this.aliasesSuccess.set(null);
    submit(this.regexAliasForm, async () => {
      const value = this.regexAliasModel();
      const pattern = value.pattern.trim();
      if (!/^\/.+\/[imxs]*$/.test(pattern)) {
        this.aliasesError.set('A regex alias must be delimited by slashes, e.g. /^info@.+$/.');
        return;
      }
      const targets = this.parseTargets(value.targets);
      if (targets.length === 0) {
        this.aliasesError.set('At least one destination is required.');
        return;
      }
      this.addingRegexAlias.set(true);
      try {
        await this.mailserver.createRegexAlias(pattern, targets);
        this.aliasesSuccess.set('Regex alias created.');
        this.regexAliasModel.set({ pattern: '', targets: '' });
        await this.loadAliases();
      } catch (err) {
        this.aliasesError.set(this.messageFor(err));
      } finally {
        this.addingRegexAlias.set(false);
      }
    });
  }

  protected async onDeleteRegexAlias(alias: RegexAlias): Promise<void> {
    if (!confirm(`Delete the regex alias ${alias.pattern}?`)) {
      return;
    }
    this.aliasesError.set(null);
    this.aliasesSuccess.set(null);
    this.deletingAlias.set(alias.pattern);
    try {
      await this.mailserver.deleteRegexAlias(alias.pattern);
      this.aliasesSuccess.set('Regex alias deleted.');
      await this.loadAliases();
    } catch (err) {
      this.aliasesError.set(this.messageFor(err));
    } finally {
      this.deletingAlias.set(null);
    }
  }

  // ── Global Sieve scripts ────────────────────────────────────────────────────

  private async loadSieve(): Promise<void> {
    this.sieveLoading.set(true);
    this.sieveError.set(null);
    try {
      this.sieveContent.set((await this.mailserver.getSieveScript(this.sieveScope())).content);
      this.sieveLoaded.set(true);
    } catch {
      this.sieveError.set('Unable to load the Sieve script.');
    } finally {
      this.sieveLoading.set(false);
    }
  }

  protected setSieveScope(scope: SieveScope): void {
    if (this.sieveScope() === scope) {
      return;
    }
    this.sieveScope.set(scope);
    this.sieveSuccess.set(null);
    void this.loadSieve();
  }

  protected onSieveContent(event: Event): void {
    this.sieveContent.set((event.target as HTMLTextAreaElement).value);
  }

  protected async onSaveSieve(): Promise<void> {
    this.sieveError.set(null);
    this.sieveSuccess.set(null);
    this.savingSieve.set(true);
    try {
      const script = await this.mailserver.setSieveScript(this.sieveScope(), this.sieveContent());
      this.sieveContent.set(script.content);
      this.sieveSuccess.set(
        `The "${script.scope}" script was saved. Restart the mailserver to compile it.`,
      );
    } catch (err) {
      this.sieveError.set(this.messageFor(err));
    } finally {
      this.savingSieve.set(false);
    }
  }

  // ── Postfix mail queue ──────────────────────────────────────────────────────

  private async loadQueue(): Promise<void> {
    this.queueLoading.set(true);
    this.queueError.set(null);
    try {
      const summary = await this.mailserver.getQueue();
      this.queue.set(summary.messages);
      this.queueCounts.set(summary.counts);
      this.queueLoaded.set(true);
    } catch (err) {
      this.queueError.set(this.messageFor(err));
    } finally {
      this.queueLoading.set(false);
    }
  }

  protected refreshQueue(): void {
    this.queueSuccess.set(null);
    void this.loadQueue();
  }

  protected async onFlushQueue(): Promise<void> {
    this.queueError.set(null);
    this.queueSuccess.set(null);
    this.flushingQueue.set(true);
    try {
      await this.mailserver.flushQueue();
      this.queueSuccess.set('Delivery attempted for every deferred message.');
      await this.loadQueue();
    } catch (err) {
      this.queueError.set(this.messageFor(err));
    } finally {
      this.flushingQueue.set(false);
    }
  }

  protected async onDeleteQueued(message: QueueMessage): Promise<void> {
    if (!confirm(`Delete the queued message ${message.queue_id}? This cannot be undone.`)) {
      return;
    }
    this.queueError.set(null);
    this.queueSuccess.set(null);
    this.deletingQueueId.set(message.queue_id);
    try {
      await this.mailserver.deleteQueuedMessage(message.queue_id);
      this.queueSuccess.set(`Message ${message.queue_id} deleted.`);
      await this.loadQueue();
    } catch (err) {
      this.queueError.set(this.messageFor(err));
    } finally {
      this.deletingQueueId.set(null);
    }
  }

  protected async onDeleteAllQueued(): Promise<void> {
    if (!confirm('Delete every message in the queue? This cannot be undone.')) {
      return;
    }
    this.queueError.set(null);
    this.queueSuccess.set(null);
    this.flushingQueue.set(true);
    try {
      await this.mailserver.deleteAllQueued();
      this.queueSuccess.set('The queue was emptied.');
      await this.loadQueue();
    } catch (err) {
      this.queueError.set(this.messageFor(err));
    } finally {
      this.flushingQueue.set(false);
    }
  }

  // ── TLS certificate ─────────────────────────────────────────────────────────

  private async loadTls(): Promise<void> {
    this.tlsLoading.set(true);
    this.tlsError.set(null);
    try {
      this.tlsCertificate.set(await this.mailserver.getTlsCertificate());
      this.tlsLoaded.set(true);
    } catch (err) {
      this.tlsError.set(this.messageFor(err));
    } finally {
      this.tlsLoading.set(false);
    }
  }

  protected refreshTls(): void {
    void this.loadTls();
  }

  // ── Mailserver environment ──────────────────────────────────────────────────

  private async loadEnvironment(): Promise<void> {
    this.environmentLoading.set(true);
    this.environmentError.set(null);
    try {
      this.environment.set(await this.mailserver.getEnvironment());
      this.environmentLoaded.set(true);
    } catch (err) {
      this.environmentError.set(this.messageFor(err));
    } finally {
      this.environmentLoading.set(false);
    }
  }

  // ── Mail log ────────────────────────────────────────────────────────────────

  private async loadLog(): Promise<void> {
    this.logLoading.set(true);
    this.logError.set(null);
    try {
      this.mailLog.set((await this.mailserver.getMailLogs()).lines);
      this.logLoaded.set(true);
    } catch (err) {
      this.logError.set(this.messageFor(err));
    } finally {
      this.logLoading.set(false);
    }
  }

  protected refreshLog(): void {
    void this.loadLog();
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
      if (err.status === 409) {
        return 'This entry already exists.';
      }
      if (err.status === 404) {
        return 'This entry no longer exists.';
      }
      if (err.status === 400) {
        return 'Invalid request. Check the values and the mailserver config volume.';
      }
      if (err.status === 422) {
        return 'Invalid input. Check the fields and try again.';
      }
      if (err.status === 502) {
        return 'The mailserver container could not be reached. Check the Docker socket mount.';
      }
    }
    return 'Something went wrong. Please try again.';
  }
}
