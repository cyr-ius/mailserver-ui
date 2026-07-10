import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

import {
  BannedIp,
  BanRequest,
  Fail2banActionResult,
  Fail2banConfig,
  Fail2banConfigUpdateRequest,
  Fail2banLog,
  Fail2banPolicy,
  Fail2banPolicyUpdateRequest,
  Fail2banStatus,
} from './fail2ban.models';

/**
 * Access to the fail2ban management API (admin only). Every call runs a
 * `docker exec` against the mailserver container on the backend, so responses
 * reflect the live state of fail2ban rather than a stored config.
 */
@Injectable({ providedIn: 'root' })
export class Fail2banService {
  private readonly http = inject(HttpClient);

  /** Return the status of every fail2ban jail, banned IPs included. */
  async getStatus(): Promise<Fail2banStatus> {
    return firstValueFrom(this.http.get<Fail2banStatus>('/api/fail2ban/status'));
  }

  /** List every currently banned IP with its jail. */
  async listBanned(): Promise<BannedIp[]> {
    return firstValueFrom(this.http.get<BannedIp[]>('/api/fail2ban/banned'));
  }

  /** Ban an IP address across the mailserver's active jails. */
  async banIp(ip: string): Promise<Fail2banActionResult> {
    const body: BanRequest = { ip };
    return firstValueFrom(this.http.post<Fail2banActionResult>('/api/fail2ban/ban', body));
  }

  /** Remove any ban for an IP address across all jails. */
  async unbanIp(ip: string): Promise<Fail2banActionResult> {
    return firstValueFrom(
      this.http.delete<Fail2banActionResult>(`/api/fail2ban/banned/${encodeURIComponent(ip)}`),
    );
  }

  /** Return the trailing lines of the fail2ban log file. */
  async getLog(): Promise<Fail2banLog> {
    return firstValueFrom(this.http.get<Fail2banLog>('/api/fail2ban/log'));
  }

  /** Return the ban policy: bantime, findtime and maxretry. */
  async getPolicy(): Promise<Fail2banPolicy> {
    return firstValueFrom(this.http.get<Fail2banPolicy>('/api/fail2ban/policy'));
  }

  /** Replace the ban policy; takes effect when the mailserver restarts. */
  async setPolicy(body: Fail2banPolicyUpdateRequest): Promise<Fail2banPolicy> {
    return firstValueFrom(this.http.put<Fail2banPolicy>('/api/fail2ban/policy', body));
  }

  /** Return the raw fail2ban-fail2ban.cf daemon configuration. */
  async getConfig(): Promise<Fail2banConfig> {
    return firstValueFrom(this.http.get<Fail2banConfig>('/api/fail2ban/config'));
  }

  /** Replace the daemon configuration; takes effect when the mailserver restarts. */
  async setConfig(content: string): Promise<Fail2banConfig> {
    const body: Fail2banConfigUpdateRequest = { content };
    return firstValueFrom(this.http.put<Fail2banConfig>('/api/fail2ban/config', body));
  }
}
