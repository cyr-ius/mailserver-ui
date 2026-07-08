export type Role = 'admin' | 'user';
export type AuthProvider = 'local' | 'oidc';

export interface SessionUser {
  username: string;
  display_name: string;
  role: Role;
  provider: AuthProvider;
}

export interface AuthConfig {
  local_enabled: boolean;
  oidc_enabled: boolean;
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
  role: Role;
  provider: AuthProvider;
  created_at: string;
  last_login_at: string | null;
}

export interface PasswordChangeRequest {
  new_password: string;
}
