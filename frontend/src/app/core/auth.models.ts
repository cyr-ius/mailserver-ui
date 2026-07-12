/** Application roles, ordered from least to most privileged. */
export const ROLES = ['guest', 'mailbox_manager', 'admin'] as const;
export type Role = (typeof ROLES)[number];
export type AuthProvider = 'local' | 'oidc';

const ROLE_LABELS: Record<Role, string> = {
  guest: 'Guest',
  mailbox_manager: 'Mailbox manager',
  admin: 'Administrator',
};

/** Human-readable name of a role, for badges and selects. */
export function roleLabel(role: Role): string {
  return ROLE_LABELS[role] ?? role;
}

/** True when `role` is at least as privileged as `required`. */
export function roleGrants(role: Role | undefined, required: Role): boolean {
  if (!role) {
    return false;
  }
  return ROLES.indexOf(role) >= ROLES.indexOf(required);
}

export interface SessionUser {
  username: string;
  display_name: string;
  role: Role;
  provider: AuthProvider;
}

export interface AuthConfig {
  local_enabled: boolean;
  oidc_enabled: boolean;
  /** When false the backend rejects tokens, so the profile page hides them. */
  pats_enabled: boolean;
}

export interface LoginRequest {
  username: string;
  password: string;
}

/** A managed application user (local or OIDC), as returned by /api/users. */
export interface User {
  id: number;
  username: string;
  display_name: string;
  /** Role assigned to the account itself (rewritten by OIDC on each sign-in). */
  role: Role;
  /** Role actually enforced, raised by the roles of the user's local groups. */
  effective_role: Role;
  provider: AuthProvider;
  /** A deactivated account keeps its data but can no longer authenticate. */
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface PasswordChangeRequest {
  new_password: string;
}

/** Payload activating or deactivating an account. */
export interface UserStatusUpdate {
  is_active: boolean;
}

/** Payload for a user rotating their own password; the current one is required. */
export interface SelfPasswordChangeRequest {
  current_password: string;
  new_password: string;
}

/** Payload creating a local account. The role comes from group membership only. */
export interface UserCreateRequest {
  username: string;
  display_name: string;
  password: string;
}
