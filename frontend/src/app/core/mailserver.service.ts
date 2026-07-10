import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import {
  DkimGenerateRequest,
  DkimKey,
  DomainDnsRecords,
  DovecotConfig,
  DovecotConfigUpdateRequest,
  DovecotMaster,
  DovecotMasterCreateRequest,
  LdapConfig,
  LdapConfigUpdateRequest,
  LdapScope,
  MailLog,
  MailserverEnvironment,
  MailStats,
  PostfixMasterOverride,
  PostfixMasterOverridesUpdateRequest,
  PostfixOverride,
  PostfixOverridesUpdateRequest,
  QueueActionResult,
  QueueSummary,
  RegexAlias,
  RegexAliasCreateRequest,
  RelayExclusion,
  RelayExclusionCreateRequest,
  RelayHost,
  RelayHostCreateRequest,
  Restriction,
  RestrictionCreateRequest,
  RestrictionKind,
  RspamdCommand,
  RspamdCommandsUpdateRequest,
  RspamdOverrides,
  ServiceStatus,
  SieveScope,
  SieveScript,
  SieveScriptUpdateRequest,
  SpamConfig,
  SpamConfigScope,
  SpamConfigUpdateRequest,
  SystemAlias,
  SystemAliasCreateRequest,
  TlsCertificate,
} from './mailserver.models';

/**
 * Access to the docker-mailserver global configuration API (admin only). Wraps
 * the calls managing SMTP relays, Postfix and Dovecot overrides, aliases, Sieve
 * scripts, DKIM records, the Rspamd overrides and the spam-filtering files stored
 * in the shared config volume, plus the read-only runtime views (queue, TLS, DNS,
 * environment, service health and mail statistics); callers own the resulting data.
 */
@Injectable({ providedIn: 'root' })
export class MailserverService {
  private readonly http = inject(HttpClient);

  // ── SMTP relays ─────────────────────────────────────────────────────────────

  /** List the configured SMTP relays (passwords never included). */
  async listRelays(): Promise<RelayHost[]> {
    return firstValueFrom(this.http.get<RelayHost[]>('/api/mailserver/relays'));
  }

  /** Add an SMTP relay for a sender domain. */
  async createRelay(body: RelayHostCreateRequest): Promise<RelayHost> {
    return firstValueFrom(this.http.post<RelayHost>('/api/mailserver/relays', body));
  }

  /** Remove an SMTP relay and its stored credentials. */
  async deleteRelay(sender: string): Promise<void> {
    await firstValueFrom(
      this.http.delete<void>(`/api/mailserver/relays/${encodeURIComponent(sender)}`),
    );
  }

  // ── Global relay exclusions ─────────────────────────────────────────────────

  /** List the sender domains opted out of the global relay host. */
  async listRelayExclusions(): Promise<RelayExclusion[]> {
    return firstValueFrom(this.http.get<RelayExclusion[]>('/api/mailserver/relay-exclusions'));
  }

  /** Opt a sender domain out of the global relay host. */
  async createRelayExclusion(sender: string): Promise<RelayExclusion> {
    const body: RelayExclusionCreateRequest = { sender };
    return firstValueFrom(this.http.post<RelayExclusion>('/api/mailserver/relay-exclusions', body));
  }

  /** Send a sender domain's mail through the global relay again. */
  async deleteRelayExclusion(sender: string): Promise<void> {
    await firstValueFrom(
      this.http.delete<void>(`/api/mailserver/relay-exclusions/${encodeURIComponent(sender)}`),
    );
  }

  // ── Postfix overrides ───────────────────────────────────────────────────────

  /** Return the Postfix main.cf overrides. */
  async getPostfixOverrides(): Promise<PostfixOverride[]> {
    return firstValueFrom(this.http.get<PostfixOverride[]>('/api/mailserver/postfix'));
  }

  /** Replace the full set of Postfix main.cf overrides. */
  async setPostfixOverrides(overrides: PostfixOverride[]): Promise<PostfixOverride[]> {
    const body: PostfixOverridesUpdateRequest = { overrides };
    return firstValueFrom(this.http.put<PostfixOverride[]>('/api/mailserver/postfix', body));
  }

  /** Return the Postfix master.cf service overrides. */
  async getPostfixMasterOverrides(): Promise<PostfixMasterOverride[]> {
    return firstValueFrom(this.http.get<PostfixMasterOverride[]>('/api/mailserver/postfix-master'));
  }

  /** Replace the full set of Postfix master.cf overrides. */
  async setPostfixMasterOverrides(
    overrides: PostfixMasterOverride[],
  ): Promise<PostfixMasterOverride[]> {
    const body: PostfixMasterOverridesUpdateRequest = { overrides };
    return firstValueFrom(
      this.http.put<PostfixMasterOverride[]>('/api/mailserver/postfix-master', body),
    );
  }

  // ── Dovecot configuration override ──────────────────────────────────────────

  /** Return the raw dovecot.cf override. */
  async getDovecotConfig(): Promise<DovecotConfig> {
    return firstValueFrom(this.http.get<DovecotConfig>('/api/mailserver/dovecot-config'));
  }

  /** Replace the dovecot.cf override; takes effect when the mailserver restarts. */
  async setDovecotConfig(content: string): Promise<DovecotConfig> {
    const body: DovecotConfigUpdateRequest = { content };
    return firstValueFrom(this.http.put<DovecotConfig>('/api/mailserver/dovecot-config', body));
  }

  // ── System and regex aliases ────────────────────────────────────────────────

  /** List the local aliases appended to /etc/aliases. */
  async listSystemAliases(): Promise<SystemAlias[]> {
    return firstValueFrom(this.http.get<SystemAlias[]>('/api/mailserver/system-aliases'));
  }

  /** Add a local system alias such as "root" or "abuse". */
  async createSystemAlias(name: string, targets: string[]): Promise<SystemAlias> {
    const body: SystemAliasCreateRequest = { name, targets };
    return firstValueFrom(this.http.post<SystemAlias>('/api/mailserver/system-aliases', body));
  }

  /** Remove a local system alias. */
  async deleteSystemAlias(name: string): Promise<void> {
    await firstValueFrom(
      this.http.delete<void>(`/api/mailserver/system-aliases/${encodeURIComponent(name)}`),
    );
  }

  /** List the PCRE aliases of postfix-regexp.cf. */
  async listRegexAliases(): Promise<RegexAlias[]> {
    return firstValueFrom(this.http.get<RegexAlias[]>('/api/mailserver/regex-aliases'));
  }

  /** Add a PCRE alias matching addresses by regular expression. */
  async createRegexAlias(pattern: string, targets: string[]): Promise<RegexAlias> {
    const body: RegexAliasCreateRequest = { pattern, targets };
    return firstValueFrom(this.http.post<RegexAlias>('/api/mailserver/regex-aliases', body));
  }

  /** Remove a PCRE alias. The pattern contains slashes, so it travels as a query param. */
  async deleteRegexAlias(pattern: string): Promise<void> {
    await firstValueFrom(
      this.http.delete<void>('/api/mailserver/regex-aliases', { params: { pattern } }),
    );
  }

  // ── DKIM ────────────────────────────────────────────────────────────────────

  /** Return the generated DKIM public records to publish in DNS. */
  async listDkimKeys(): Promise<DkimKey[]> {
    return firstValueFrom(this.http.get<DkimKey[]>('/api/mailserver/dkim'));
  }

  /** Generate DKIM keys inside the mailserver container; returns the refreshed list. */
  async generateDkim(body: DkimGenerateRequest): Promise<DkimKey[]> {
    return firstValueFrom(this.http.post<DkimKey[]>('/api/mailserver/dkim', body));
  }

  // ── Send/receive restrictions ─────────────────────────────────────────────────

  /** List the send or receive restrictions. */
  async listRestrictions(kind: RestrictionKind): Promise<Restriction[]> {
    return firstValueFrom(this.http.get<Restriction[]>(`/api/mailserver/restrictions/${kind}`));
  }

  /** Restrict an address from sending or receiving. */
  async addRestriction(kind: RestrictionKind, address: string): Promise<Restriction> {
    const body: RestrictionCreateRequest = { address };
    return firstValueFrom(
      this.http.post<Restriction>(`/api/mailserver/restrictions/${kind}`, body),
    );
  }

  /** Remove a send or receive restriction. */
  async deleteRestriction(kind: RestrictionKind, address: string): Promise<void> {
    await firstValueFrom(
      this.http.delete<void>(`/api/mailserver/restrictions/${kind}/${encodeURIComponent(address)}`),
    );
  }

  // ── Mail log (read-only) ──────────────────────────────────────────────────────

  /** Return the trailing lines of the mailserver mail log. */
  async getMailLogs(): Promise<MailLog> {
    return firstValueFrom(this.http.get<MailLog>('/api/mailserver/logs'));
  }

  // ── Dovecot master accounts ───────────────────────────────────────────────────

  /** List the Dovecot master accounts (passwords never included). */
  async listDovecotMasters(): Promise<DovecotMaster[]> {
    return firstValueFrom(this.http.get<DovecotMaster[]>('/api/mailserver/dovecot-masters'));
  }

  /** Add a Dovecot master account. */
  async createDovecotMaster(body: DovecotMasterCreateRequest): Promise<DovecotMaster> {
    return firstValueFrom(this.http.post<DovecotMaster>('/api/mailserver/dovecot-masters', body));
  }

  /** Remove a Dovecot master account. */
  async deleteDovecotMaster(name: string): Promise<void> {
    await firstValueFrom(
      this.http.delete<void>(`/api/mailserver/dovecot-masters/${encodeURIComponent(name)}`),
    );
  }

  // ── Global Sieve scripts ────────────────────────────────────────────────────

  /** Return the global Sieve script running before or after the user's scripts. */
  async getSieveScript(scope: SieveScope): Promise<SieveScript> {
    return firstValueFrom(this.http.get<SieveScript>(`/api/mailserver/sieve/${scope}`));
  }

  /** Replace a global Sieve script; takes effect when the mailserver restarts. */
  async setSieveScript(scope: SieveScope, content: string): Promise<SieveScript> {
    const body: SieveScriptUpdateRequest = { content };
    return firstValueFrom(this.http.put<SieveScript>(`/api/mailserver/sieve/${scope}`, body));
  }

  // ── Spam filter configuration files ─────────────────────────────────────────

  /** Return the SpamAssassin rules or a Postgrey whitelist. */
  async getSpamConfig(scope: SpamConfigScope): Promise<SpamConfig> {
    return firstValueFrom(this.http.get<SpamConfig>(`/api/mailserver/spam/${scope}`));
  }

  /** Replace a spam-filtering file; takes effect when the mailserver restarts. */
  async setSpamConfig(scope: SpamConfigScope, content: string): Promise<SpamConfig> {
    const body: SpamConfigUpdateRequest = { content };
    return firstValueFrom(this.http.put<SpamConfig>(`/api/mailserver/spam/${scope}`, body));
  }

  // ── Rspamd overrides ────────────────────────────────────────────────────────

  /** Return the directives of rspamd/custom-commands.conf, in file order. */
  async getRspamdOverrides(): Promise<RspamdOverrides> {
    return firstValueFrom(this.http.get<RspamdOverrides>('/api/mailserver/rspamd'));
  }

  /** Replace the Rspamd custom commands; takes effect when the mailserver restarts. */
  async setRspamdOverrides(commands: RspamdCommand[]): Promise<RspamdOverrides> {
    const body: RspamdCommandsUpdateRequest = { commands };
    return firstValueFrom(this.http.put<RspamdOverrides>('/api/mailserver/rspamd', body));
  }

  // ── LDAP provisioner maps ───────────────────────────────────────────────────

  /** Return one Postfix LDAP map, with the keys the environment overrides. */
  async getLdapConfig(scope: LdapScope): Promise<LdapConfig> {
    return firstValueFrom(this.http.get<LdapConfig>(`/api/mailserver/ldap/${scope}`));
  }

  /** Replace one Postfix LDAP map; takes effect when the mailserver restarts. */
  async setLdapConfig(scope: LdapScope, content: string): Promise<LdapConfig> {
    const body: LdapConfigUpdateRequest = { content };
    return firstValueFrom(this.http.put<LdapConfig>(`/api/mailserver/ldap/${scope}`, body));
  }

  // ── Postfix mail queue ──────────────────────────────────────────────────────

  /** Return every message sitting in the Postfix queue. */
  async getQueue(): Promise<QueueSummary> {
    return firstValueFrom(this.http.get<QueueSummary>('/api/mailserver/queue'));
  }

  /** Attempt delivery of every deferred message now. */
  async flushQueue(): Promise<QueueActionResult> {
    return firstValueFrom(this.http.post<QueueActionResult>('/api/mailserver/queue/flush', {}));
  }

  /** Delete a single message from the Postfix queue. */
  async deleteQueuedMessage(queueId: string): Promise<QueueActionResult> {
    return firstValueFrom(
      this.http.delete<QueueActionResult>(`/api/mailserver/queue/${encodeURIComponent(queueId)}`),
    );
  }

  /** Delete every message currently in the Postfix queue. */
  async deleteAllQueued(): Promise<QueueActionResult> {
    return firstValueFrom(this.http.delete<QueueActionResult>('/api/mailserver/queue'));
  }

  // ── TLS, DNS and environment (read-only) ────────────────────────────────────

  /** Return the TLS certificate Postfix serves, with its expiry. */
  async getTlsCertificate(): Promise<TlsCertificate> {
    return firstValueFrom(this.http.get<TlsCertificate>('/api/mailserver/tls'));
  }

  /** Return the MX, SPF, DMARC and DKIM records to publish, per hosted domain. */
  async listDnsRecords(): Promise<DomainDnsRecords[]> {
    return firstValueFrom(this.http.get<DomainDnsRecords[]>('/api/mailserver/dns'));
  }

  /** Return the mailserver's effective environment, set when the container started. */
  async getEnvironment(): Promise<MailserverEnvironment> {
    return firstValueFrom(this.http.get<MailserverEnvironment>('/api/mailserver/environment'));
  }

  // ── Runtime health (read-only) ──────────────────────────────────────────────

  /** Report the state of every supervised process in the mailserver container. */
  async listServices(): Promise<ServiceStatus[]> {
    return firstValueFrom(this.http.get<ServiceStatus[]>('/api/mailserver/services'));
  }

  /** Count deliveries, rejections and bounces over the trailing stats window. */
  async getMailStats(): Promise<MailStats> {
    return firstValueFrom(this.http.get<MailStats>('/api/mailserver/stats'));
  }
}
