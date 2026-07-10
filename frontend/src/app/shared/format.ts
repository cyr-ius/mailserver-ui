/**
 * Format a byte count for display, e.g. 1610612736 → "1.5 GB".
 *
 * Units step by 1024, matching how Dovecot reports usage and how quotas are
 * written throughout this UI ("5G" means 5 GiB), so a usage figure and the
 * quota it is compared against always use the same scale.
 */
export function formatBytes(bytes: number): string {
  if (bytes <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  // Whole bytes never need a decimal; above that one is enough to be useful.
  const decimals = exponent === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(decimals)} ${units[exponent]}`;
}

/**
 * Format how long ago `iso` was, e.g. "3h ago". Returns "—" when absent, and
 * "just now" under a minute — the dashboard only needs an order of magnitude.
 */
export function formatAge(iso: string | null): string {
  if (!iso) {
    return '—';
  }
  const elapsedMs = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(elapsedMs)) {
    return '—';
  }
  const minutes = Math.floor(elapsedMs / 60_000);
  if (minutes < 1) {
    return 'just now';
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  return `${Math.floor(hours / 24)}d ago`;
}
