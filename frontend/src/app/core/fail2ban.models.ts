/** A fail2ban jail with its counters and currently banned IPs. */
export interface Fail2banJail {
  name: string;
  currently_failed: number;
  total_failed: number;
  currently_banned: number;
  total_banned: number;
  /** IPs currently banned in this jail. */
  banned_ips: string[];
  /** Log files watched by the jail's filter. */
  file_list: string[];
}

/** Aggregated fail2ban status returned by GET /api/fail2ban/status. */
export interface Fail2banStatus {
  jails: Fail2banJail[];
  /** False when ENABLE_FAIL2BAN=0: no daemon runs, so no jail exists. */
  fail2ban_enabled: boolean;
}

/** A single banned IP and the jail it is banned in. */
export interface BannedIp {
  ip: string;
  jail: string;
}

export interface BanRequest {
  ip: string;
}

/** Raw command output returned after a ban/unban action. */
export interface Fail2banActionResult {
  output: string;
}

/** Trailing lines of the fail2ban log file. */
export interface Fail2banLog {
  lines: string[];
}

/** The ban policy stored in fail2ban-jail.cf under [DEFAULT]. */
export interface Fail2banPolicy {
  /** Seconds a banned IP stays banned. */
  bantime: number;
  /** Seconds over which failures are counted towards maxretry. */
  findtime: number;
  /** Failures within findtime before an IP is banned. */
  maxretry: number;
  /** False when no policy file exists yet: the values are docker-mailserver's defaults. */
  configured: boolean;
  /** The mailserver only reads the policy when it starts. */
  restart_required: boolean;
}

export interface Fail2banPolicyUpdateRequest {
  bantime: number;
  findtime: number;
  maxretry: number;
}

/**
 * The raw contents of fail2ban-fail2ban.cf: the daemon's own options — log level,
 * database retention — rather than any jail.
 */
export interface Fail2banConfig {
  content: string;
  /** Copied to /etc/fail2ban/fail2ban.local at startup: an edit needs a restart. */
  restart_required: boolean;
}

export interface Fail2banConfigUpdateRequest {
  content: string;
}
