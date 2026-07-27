/** One area of mailserver configuration awaiting a container restart. */
export interface PendingAction {
  id: number;
  key: string;
  title: string;
  detail: string;
  created_at: string;
  updated_at: string;
}

/** Every pending action, as returned by GET /api/pending-actions. */
export interface PendingActionsSummary {
  items: PendingAction[];
  count: number;
}
