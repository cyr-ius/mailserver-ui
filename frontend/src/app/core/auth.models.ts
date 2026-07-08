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
