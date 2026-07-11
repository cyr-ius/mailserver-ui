/** Families an audited action belongs to, as recorded by the backend. */
export const AUDIT_CATEGORIES = ['auth', 'user', 'settings', 'api_key', 'mailserver'] as const;
export type AuditCategory = (typeof AUDIT_CATEGORIES)[number];

export type AuditStatus = 'success' | 'failure';

const CATEGORY_LABELS: Record<AuditCategory, string> = {
  auth: 'Authentication',
  user: 'Users',
  settings: 'Settings',
  api_key: 'API keys',
  mailserver: 'Mailserver',
};

/** Human-readable name of an audit category, for filters and badges. */
export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category as AuditCategory] ?? category;
}

/** One entry of the audit trail, as returned by GET /api/audit. */
export interface AuditEntry {
  id: number;
  created_at: string;
  actor: string;
  category: string;
  action: string;
  target: string;
  status: AuditStatus;
  detail: string;
  ip: string;
}

/** A page of entries; `total` counts every row matching the active filters. */
export interface AuditPage {
  items: AuditEntry[];
  total: number;
}

/** Filters accepted by GET /api/audit. Empty strings mean "no filter". */
export interface AuditQuery {
  actor?: string;
  action?: string;
  category?: string;
  status?: string;
  limit?: number;
  offset?: number;
}
