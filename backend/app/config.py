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

    # SQLite database storing local/OIDC users. Defaults to a file under
    # ``DATA_DIR``; override with the ``DATABASE_URL`` env variable if needed.
    database_url: str = f"sqlite:///{Path(DATA_DIR) / 'mailserver-ui.db'}"
    database_echo: bool = False

    # Username of the default admin account seeded on first startup. Its
    # password is generated randomly and printed once to the logs.
    admin_username: str = "admin"

    # Path of the docker-mailserver configuration directory *inside* the
    # mailserver container. The flat config files (``postfix-accounts.cf`` and
    # friends) are read and written there over the Docker socket via
    # ``docker exec`` — no host directory is bind-mounted. Rarely needs changing
    # from the docker-mailserver image default.
    mailserver_config_dir: str = "/tmp/docker-mailserver"

    # ── Fail2ban (docker-mailserver) ──────────────────────────────────────────
    # Fail2ban lives inside the mailserver container and cannot be driven through
    # the shared config files, so it is managed with ``docker exec``. This
    # requires the Docker socket to be mounted into this container. Disabled by
    # default; enable it explicitly once the socket and container name are set.
    fail2ban_enabled: bool = False
    # Name (or ID) of the docker-mailserver container to exec into.
    mailserver_container: str = "mailserver"
    # Path to the docker CLI used to exec into the container.
    docker_binary: str = "docker"
    # Timeout (seconds) for a single fail2ban command.
    fail2ban_command_timeout: int = 15
    # Number of trailing fail2ban log lines returned by the log endpoint.
    fail2ban_log_lines: int = 200

    # ── Mailserver docker exec (docker-mailserver) ────────────────────────────
    # All mailserver management (mailboxes, aliases, relays, DKIM, mail log, …)
    # runs inside the mailserver container via ``docker exec`` — reading and
    # writing its config files as well as runtime-only actions. This requires the
    # Docker socket to be mounted into this container. Disabled by default;
    # enable it once the socket is mounted and the container name is set.
    mailserver_exec_enabled: bool = False
    # Timeout (seconds) for a single mailserver ``docker exec`` command.
    mailserver_command_timeout: int = 30
    # Number of trailing mail log lines returned by the mail log endpoint.
    mailserver_log_lines: int = 200
    # Trailing time window the mail statistics endpoint reports on.
    mailserver_stats_hours: int = 24
    # Trailing mail log lines scanned to build those statistics. A busy server
    # can overflow this window; the endpoint reports how many lines it read.
    mailserver_stats_log_lines: int = 20000

    secret_key: str = "change-this-secret-key-in-production"
    auth_cookie_name: str = "pc_token"
    # Session lifetime for the local/OIDC JWT stored in the auth cookie.
    auth_token_ttl_seconds: int = 8 * 3600

    # ── Personal API keys ─────────────────────────────────────────────────────
    # Users issue keys from their profile to call the REST API without a browser
    # session. A key carries the effective role of the account that owns it.
    api_keys_enabled: bool = True
    # Header carrying the key. ``Authorization: Bearer <key>`` is accepted too.
    api_key_header: str = "X-API-Key"
    # Upper bound on the number of live keys a single account may own.
    api_key_max_per_user: int = 10
    # The auth cookie ``Secure`` flag is detected per request from the scheme
    # (honouring ``X-Forwarded-Proto`` behind trusted proxies), not configured.

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

    oidc_manager_group_claim: str = ""
    oidc_manager_group: str = ""

    oidc_restrict_to_groups: bool = False

    # Logging level (DEBUG, INFO, WARNING, ERROR)
    log_level: str = "INFO"

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
