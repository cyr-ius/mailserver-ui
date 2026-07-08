"""
Portalcrane - Application Configuration
All settings loaded from environment variables
"""

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Default data directory (can be overridden by DATA_DIR env variable for debugging)
DATA_DIR = os.getenv("DATA_DIR", "/var/lib/mailserver-ui")

# Default directory for ui
FRONTEND_DIR = Path("/app/ui").resolve()
INDEX_HTML = FRONTEND_DIR / "index.html"


# HTTP client timeout for GitHub API calls (in seconds)
DEFAULT_TIMEOUT: float = 10.0


# ── Settings ─────────────────────────────────────────────────────────────────


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_version: str = "0.1.0"

    admin_username: str = "admin"
    # Local admin password. Provide either a plaintext value (hashed at compare
    # time) or a precomputed bcrypt hash via ``admin_password_hash``.
    admin_password: str = "admin"
    admin_password_hash: str = ""

    secret_key: str = "change-this-secret-key-in-production"
    auth_cookie_name: str = "pc_token"
    # Session lifetime for the local/OIDC JWT stored in the auth cookie.
    auth_token_ttl_seconds: int = 8 * 3600
    # Mark the auth cookie Secure. Disable only for local HTTP development.
    cookie_secure: bool = True

    # OIDC configuration
    oidc_enabled: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_post_logout_redirect_uri: str = ""
    oidc_response_type: str = "code"
    oidc_scope: str = "openid profile email groups"

    oidc_only: bool = False
    oidc_admin_group_claim: str = ""
    oidc_admin_group: str = ""

    oidc_user_group_claim: str = ""
    oidc_user_group: str = ""

    oidc_restrict_to_groups: bool = False

    syslog_enabled: bool = False
    syslog_host: str = ""
    syslog_port: int = 514
    syslog_protocol: str = "udp"  # 'udp' | 'tcp' | 'tcp+tls'
    syslog_rfc: str = "rfc5424"  # 'rfc3164' | 'rfc5424'
    syslog_forward_audit: bool = True
    syslog_forward_uvicorn: bool = False
    syslog_tls_verify: bool = True
    syslog_tls_ca_cert: str = ""
    syslog_auth_enabled: bool = False
    syslog_auth_username: str = ""
    syslog_auth_password: str = ""

    email_enabled: bool = False
    email_host: str = ""
    email_port: int = 587
    email_security: str = "starttls"  # 'none' | 'starttls' | 'ssl'
    email_username: str = ""
    email_password: str = ""
    email_from_address: str = ""
    email_to_addresses: str = ""  # comma-separated recipients
    email_subject: str = "Portalcrane audit log"

    # Logging level (DEBUG, INFO, WARNING, ERROR)
    log_level: str = "INFO"

    # Audit retention
    audit_max_events: int = 100

    # Swagger UI
    swagger_enabled: bool = False

    trusted_proxies: str = ""

    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 100  # per IP per window, all /api/* routes
    rate_limit_auth_max_requests: int = 5  # per IP per window, login/token only

    # Stricter budget for the login endpoint to slow credential brute-forcing.
    rate_limit_login_max_attempts: int = 5
    rate_limit_login_window_seconds: int = 300
    rate_limit_login_path: str = "/api/auth/login"

    # ── Internal helpers ─────────────────────────────────────────────────────────

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


app_settings = get_settings()
# ``settings`` is the canonical name imported across the app.
settings = app_settings
