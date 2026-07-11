# Docker Mailserver UI

A web interface for [docker-mailserver](https://github.com/docker-mailserver/docker-mailserver).
Single container serving an Angular SPA and a FastAPI backend, with local and
OIDC/SSO authentication.

| Layer    | Tech                                       |
| -------- | ------------------------------------------ |
| Frontend | Angular 22 (signals, zoneless, standalone) |
| Backend  | FastAPI 0.139 (async, Pydantic v2)         |
| Database | SQLite via SQLModel                        |
| UI       | Bootstrap 5.3 / Bootstrap Icons            |
| Runtimes | Python 3.14 / Node.js 18+                  |

## Features

- **Local authentication** — a default admin is seeded on first startup
  (random password printed once to the logs).
- **OIDC / SSO** — Keycloak, Authentik, etc. **Configured entirely from the web
  UI** (Settings → OIDC / SSO) and stored in the database. No redeploy needed to
  change the SSO configuration.
- **User management** — list local & OIDC accounts, create and delete local ones,
  deactivate any of them (a deactivated account keeps its data but can no longer
  sign in, and its sessions and API keys stop working at once), reset local
  passwords (admin only), personal API keys issued from the profile page. The
  last active administrator can neither be deleted nor deactivated, and an OIDC
  identity can never take over a local account of the same name.
- **Audit log** — every sign-in, sign-out, account change, settings change and
  API-key operation is appended to an immutable trail, browsable under
  Settings → Audit log with filters on the actor, the category and the outcome.
- **Mail connector** — an SMTP server configured from the web UI (Settings → Mail
  connector), notifying on sign-in/sign-out alone or on every audit event, with a
  test button to check the configuration.
- **Mailbox management** — create, reset the password of, and delete
  docker-mailserver accounts, with per-mailbox quotas.
- **Mailserver administration** — aliases (system & regex), relay hosts and
  exclusions, DKIM keys, DNS records, Postfix/Dovecot overrides, Sieve scripts,
  custom SpamAssassin rules and Postgrey whitelists, Rspamd overrides, Postfix
  LDAP maps, TLS certificates, access restrictions, Dovecot master accounts and
  mail queue actions.
- **Dashboard** — real mailbox disk usage (from Dovecot, not the configured
  quota), TLS certificate expiry, DKIM coverage per hosted domain, supervised
  service health, the mail queue backlog, banned IPs per jail, the spam/virus and
  delivery counters of the last 24 hours, and any contradiction between the
  mailserver's environment variables.
- **Fail2ban** — inspect jails, ban and unban IPs, read the fail2ban log.
- **Disabled features are called out** — docker-mailserver only reads a config
  file when the matching `ENABLE_*` toggle is on. Pages guarded by a toggle that
  is off (quotas, fail2ban, SpamAssassin, Postgrey, Amavis) say so, instead of
  silently saving a file nothing will ever read.
- Group-based role mapping and optional group-restricted access for OIDC users.

## How it talks to docker-mailserver

Everything — mailboxes, aliases, relays, DKIM, mail log, queue, fail2ban — is
driven **through the Docker socket** with `docker exec` inside the mailserver
container. Config files are read and written there directly; **no config
directory is bind-mounted** into the UI container.

This means:

- `/var/run/docker.sock` **must** be mounted into the `mailserver-ui` container;
- `MAILSERVER_CONTAINER` must name the docker-mailserver container;
- mounting the Docker socket grants the container root-equivalent control of the
  host — only enable it if you accept that risk. Mount it read-only (`:ro`).

Mailbox management requires the mailserver to run with
`ACCOUNT_PROVISIONER=FILE`, because the UI edits `postfix-accounts.cf` and
`dovecot-quotas.cf`, which only the FILE provisioner reads.

The rest adapts to whatever the container was started with: DKIM keys are read
from `opendkim/keys` or from Rspamd's own directory depending on
`ENABLE_RSPAMD`, and any page whose feature is off (`ENABLE_QUOTAS`,
`ENABLE_FAIL2BAN`, `ENABLE_SPAMASSASSIN`, `ENABLE_POSTGREY`, `ENABLE_AMAVIS`)
warns that its file is stored but never read.

## Quick start (Docker)

A ready-to-use [`docker-compose.yml`](docker-compose.yml) is provided at the
root of the repository. It starts both docker-mailserver and the UI with a
sensible default configuration.

```bash
cp backend/.env.example .env   # sensible defaults; nothing is required
docker compose up -d --build
```

The UI is available on <http://localhost:8000>. On first startup, check the
logs for the generated admin password:

```bash
docker compose logs mailserver-ui | grep "Generated password"
```

## Configuration

All settings are provided through environment variables (see
[`backend/.env.example`](backend/.env.example) for the annotated list).

### Core

| Variable          | Default                   | Description                                                                                                                                                        |
| ----------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `SECRET_KEY`      | _(auto-generated)_        | Signs session cookies. If unset, a random key is generated and persisted to `DATA_DIR/secret_key` on first boot. Set it explicitly when running multiple replicas. |
| `ADMIN_USERNAME`  | `admin`                   | Default admin account seeded on first boot.                                                                                                                        |
| `DATA_DIR`        | `/var/lib/mailserver-ui`  | Persistent directory for the SQLite database.                                                                                                                      |
| `DATABASE_URL`    | _(file under `DATA_DIR`)_ | SQLite connection string.                                                                                                                                          |
| `DATABASE_ECHO`   | `false`                   | Echo SQL statements to the logs (debug only).                                                                                                                      |
| `LOG_LEVEL`       | `INFO`                    | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`                                                                                                                          |
| `SWAGGER_ENABLED` | `false`                   | Expose the Swagger UI at `/api/docs`.                                                                                                                              |

### Mailserver (`docker exec`)

Mailserver management is always on: all it needs is a reachable Docker socket.

| Variable                     | Default      | Description                                       |
| ---------------------------- | ------------ | ------------------------------------------------- |
| `MAILSERVER_CONTAINER`       | `mailserver` | Name (or ID) of the docker-mailserver container.  |
| `MAILSERVER_COMMAND_TIMEOUT` | `30`         | Timeout (s) of a single `docker exec` command.    |
| `MAILSERVER_LOG_LINES`       | `200`        | Trailing mail log lines returned by the log view. |
| `MAILSERVER_STATS_HOURS`     | `24`         | Time window covered by the dashboard statistics.  |
| `MAILSERVER_STATS_LOG_LINES` | `20000`      | Log lines scanned to build those statistics.      |

The docker CLI (`docker`) and the config directory inside the mailserver
container (`/tmp/docker-mailserver`) are constants, not settings.

### Fail2ban

The fail2ban views follow the mailserver's own `ENABLE_FAIL2BAN` toggle: when the
container starts with it off, no daemon runs and the UI says so instead of
offering actions that would do nothing. Nothing to enable on this side.

| Variable                   | Default | Description                                     |
| -------------------------- | ------- | ----------------------------------------------- |
| `FAIL2BAN_COMMAND_TIMEOUT` | `15`    | Timeout (s) of a single fail2ban command.       |
| `FAIL2BAN_LOG_LINES`       | `200`   | Trailing fail2ban log lines returned to the UI. |

### Authentication & API keys

| Variable                 | Default     | Description                                                                                                                                                  |
| ------------------------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `AUTH_COOKIE_NAME`       | `pc_token`  | Name of the session cookie.                                                                                                                                  |
| `AUTH_TOKEN_TTL_SECONDS` | `28800`     | Session lifetime (8 h).                                                                                                                                      |
| `API_KEYS_ENABLED`       | `true`      | Let users issue personal API keys from their profile. Set to `false` and the backend rejects every key, while the profile page hides the section altogether. |
| `API_KEY_HEADER`         | `X-API-Key` | Header carrying the key (`Authorization: Bearer` too).                                                                                                       |
| `API_KEY_MAX_PER_USER`   | `10`        | Upper bound on live keys per account.                                                                                                                        |

> The auth cookie `Secure` flag is detected automatically from the request
> scheme (HTTPS), honouring `X-Forwarded-Proto` when the request comes through a
> trusted proxy. No manual `COOKIE_SECURE` toggle is needed.

A personal API key authenticates a REST call either as `X-API-Key: <key>` or as
`Authorization: Bearer <key>`. Both are declared in the OpenAPI schema, so the
Swagger UI's _Authorize_ dialog offers them when `SWAGGER_ENABLED=true`.

### Mail connector

Seeded on first boot, then edited from the UI (Settings → Mail connector).

| Variable                   | Default   | Description                                                   |
| -------------------------- | --------- | ------------------------------------------------------------- |
| `SMTP_ENABLED`             | `false`   | Master switch for the connector.                              |
| `SMTP_HOST`                | _(empty)_ | SMTP server.                                                  |
| `SMTP_PORT`                | `587`     | 587 (STARTTLS), 465 (implicit TLS) or 25 (plaintext).         |
| `SMTP_USERNAME`            | _(empty)_ | Leave empty for a server that needs no authentication.        |
| `SMTP_PASSWORD`            | _(empty)_ | Stored in the database; never returned by the API.            |
| `SMTP_USE_TLS`             | `true`    | STARTTLS on a plaintext connection. Exclusive with `USE_SSL`. |
| `SMTP_USE_SSL`             | `false`   | Implicit TLS. Exclusive with `USE_TLS`.                       |
| `SMTP_FROM`                | _(empty)_ | Sender address.                                               |
| `SMTP_RECIPIENTS`          | _(empty)_ | Comma-separated notification recipients.                      |
| `SMTP_NOTIFY_AUTH_EVENTS`  | `false`   | Notify on sign-in and sign-out only.                          |
| `SMTP_NOTIFY_AUDIT_EVENTS` | `false`   | Notify on every audit event (sign-in and sign-out included).  |

### Audit trail

| Variable               | Default | Description                                                       |
| ---------------------- | ------- | ----------------------------------------------------------------- |
| `AUDIT_RETENTION_DAYS` | `0`     | Purge entries older than this on startup. `0` keeps them forever. |

### Reverse proxy & rate limiting

| Variable                          | Default           | Description                                       |
| --------------------------------- | ----------------- | ------------------------------------------------- |
| `TRUSTED_PROXIES`                 | _(empty)_         | Trusted proxy IPs/CIDRs; enables `X-Forwarded-*`. |
| `RATE_LIMIT_ENABLED`              | `true`            | Master switch for rate limiting.                  |
| `RATE_LIMIT_WINDOW_SECONDS`       | `60`              | Window applied to all `/api/*` routes.            |
| `RATE_LIMIT_MAX_REQUESTS`         | `100`             | Requests per IP per window.                       |
| `RATE_LIMIT_AUTH_MAX_REQUESTS`    | `5`               | Same, restricted to the auth routes.              |
| `RATE_LIMIT_LOGIN_MAX_ATTEMPTS`   | `5`               | Login attempts before throttling.                 |
| `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `300`             | Window for those attempts.                        |
| `RATE_LIMIT_LOGIN_PATH`           | `/api/auth/login` | Path the stricter login budget applies to.        |

### OIDC / SSO

OIDC is managed from **Settings → OIDC / SSO** in the UI and stored in the
database. The `OIDC_*` environment variables are read **only on the first
startup** to seed the initial configuration (for backwards compatibility);
afterwards the database is authoritative and changing those variables has no
effect. Configure the issuer URL, client ID/secret, redirect URI, scopes and
group mappings directly in the interface.

| Variable                        | Default                       |
| ------------------------------- | ----------------------------- |
| `OIDC_ENABLED`                  | `false`                       |
| `OIDC_ISSUER`                   | _(empty)_                     |
| `OIDC_CLIENT_ID`                | _(empty)_                     |
| `OIDC_CLIENT_SECRET`            | _(empty)_                     |
| `OIDC_REDIRECT_URI`             | _(empty)_                     |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | _(empty)_                     |
| `OIDC_RESPONSE_TYPE`            | `code`                        |
| `OIDC_SCOPE`                    | `openid profile email groups` |
| `OIDC_ONLY`                     | `false`                       |
| `OIDC_ADMIN_GROUP_CLAIM`        | _(empty)_                     |
| `OIDC_ADMIN_GROUP`              | _(empty)_                     |
| `OIDC_MANAGER_GROUP_CLAIM`      | _(empty)_                     |
| `OIDC_MANAGER_GROUP`            | _(empty)_                     |
| `OIDC_RESTRICT_TO_GROUPS`       | `false`                       |

Members of `OIDC_ADMIN_GROUP` sign in as administrators, members of
`OIDC_MANAGER_GROUP` as mailbox managers. Anyone in neither group signs in as a
guest (dashboard only), unless `OIDC_RESTRICT_TO_GROUPS` denies them access
altogether.

## Development

### Backend (FastAPI)

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

Over plain HTTP the auth cookie is issued without the `Secure` flag
automatically, so local development works without any extra configuration.

A throwaway docker-mailserver instance for end-to-end testing is available with
`scripts/mailserver-up.sh` (see
[`.devcontainer/docker-compose.mailserver.yml`](.devcontainer/docker-compose.mailserver.yml)).

### Frontend (Angular)

```bash
cd frontend
npm install
npm start                               # http://localhost:4200 (proxied to :8000)
```

### Linting

```bash
# Backend
cd backend && uv run ruff check app/ && uv run ruff format --check app/
# Frontend
cd frontend && npx prettier --check "src/app/**/*.{ts,html,css}"
```

## License

MIT — see the container labels and repository for details.
