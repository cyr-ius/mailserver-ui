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
- **User management** — list local & OIDC accounts, reset local passwords
  (admin only), personal API keys issued from the profile page.
- **Mailbox management** — create, reset the password of, and delete
  docker-mailserver accounts, with per-mailbox quotas.
- **Mailserver administration** — aliases (system & regex), relay hosts and
  exclusions, DKIM keys, DNS records, Postfix/Dovecot overrides, Sieve scripts,
  access restrictions, Dovecot master accounts and mail queue actions.
- **Dashboard** — real mailbox disk usage (from Dovecot, not the configured
  quota), TLS certificate expiry, DKIM coverage per hosted domain, supervised
  service health, the mail queue backlog, banned IPs per jail and the delivery
  counters of the last 24 hours.
- **Fail2ban** — inspect jails, ban and unban IPs, read the fail2ban log.
- Group-based role mapping and optional group-restricted access for OIDC users.

## How it talks to docker-mailserver

Everything — mailboxes, aliases, relays, DKIM, mail log, queue, fail2ban — is
driven **through the Docker socket** with `docker exec` inside the mailserver
container. Config files are read and written there directly; **no config
directory is bind-mounted** into the UI container.

This means:

- `/var/run/docker.sock` **must** be mounted into the `mailserver-ui` container;
- `MAILSERVER_EXEC_ENABLED=true` and `MAILSERVER_CONTAINER` must be set;
- mounting the Docker socket grants the container root-equivalent control of the
  host — only enable it if you accept that risk. Mount it read-only (`:ro`).

The mailserver container itself must run with `ACCOUNT_PROVISIONER=FILE` (the UI
edits `postfix-accounts.cf` / `dovecot-quotas.cf`), `ENABLE_QUOTAS=1` and
`ENABLE_OPENDKIM=1` / `ENABLE_RSPAMD=0` (DKIM keys are read from
`opendkim/keys`).

## Quick start (Docker)

```bash
cp backend/.env.example .env   # then edit SECRET_KEY (at minimum)
docker compose up -d --build
```

The UI is available on <http://localhost:8000>. On first startup, check the
logs for the generated admin password:

```bash
docker compose logs mailserver-ui | grep "Generated password"
```

## Example `docker-compose.yml`

```yaml
---
services:
  mailserver:
    image: mailserver/docker-mailserver:latest
    container_name: mailserver # must match MAILSERVER_CONTAINER below
    hostname: mail.example.com
    environment:
      # The UI writes postfix-accounts.cf / dovecot-quotas.cf directly, which
      # only docker-mailserver's FILE provisioner reads. Quotas require it too.
      - ACCOUNT_PROVISIONER=FILE
      - ENABLE_QUOTAS=1
      # The UI reads DKIM records from opendkim/keys; Rspamd stores them
      # elsewhere, so the two toggles must stay as they are here.
      - ENABLE_OPENDKIM=1
      - ENABLE_RSPAMD=0
      # Required by the published 4190 port, otherwise nothing listens on it.
      - ENABLE_MANAGESIEVE=1
      - ENABLE_FAIL2BAN=1
      - POSTMASTER_ADDRESS=postmaster@example.com
      - SSL_TYPE=
    cap_add:
      - NET_ADMIN # required by fail2ban
    ports:
      - "25:25" # SMTP
      - "465:465" # SMTPS
      - "587:587" # Submission
      - "143:143" # IMAP
      - "993:993" # IMAPS
      - "4190:4190" # ManageSieve
    volumes:
      - mailserver-mail:/var/mail
      - mailserver-config:/tmp/docker-mailserver/
      # Postfix/Dovecot runtime state, including the fail2ban ban database the
      # UI manages: without it every ban is lost when the container is recreated.
      - mailserver-state:/var/mail-state
      # The UI tails /var/log/mail/mail.log.
      - mailserver-logs:/var/log/mail
    restart: unless-stopped

  mailserver-ui:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      - mailserver
    environment:
      - SECRET_KEY=${SECRET_KEY:?generate one with `openssl rand -hex 32`}
      - LOG_LEVEL=INFO
      - MAILSERVER_EXEC_ENABLED=true
      - MAILSERVER_CONTAINER=mailserver
      - FAIL2BAN_ENABLED=true
      # Behind a reverse proxy, list its IPs so rate limiting and the cookie
      # `Secure` flag see the real client request.
      # - TRUSTED_PROXIES=10.0.0.0/8
    ports:
      - "8000:8000"
    volumes:
      - mailserver-ui:/var/lib/mailserver-ui
      # Root-equivalent access to the host — required, see the section above.
      - /var/run/docker.sock:/var/run/docker.sock:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

volumes:
  mailserver-mail:
  mailserver-config:
  mailserver-state:
  mailserver-logs:
  mailserver-ui:
```

## Configuration

All settings are provided through environment variables (see
[`backend/.env.example`](backend/.env.example) for the annotated list).

### Core

| Variable          | Default                   | Description                                      |
| ----------------- | ------------------------- | ------------------------------------------------ |
| `SECRET_KEY`      | _(change me)_             | Signs session cookies — **must** be set in prod. |
| `ADMIN_USERNAME`  | `admin`                   | Default admin account seeded on first boot.      |
| `DATA_DIR`        | `/var/lib/mailserver-ui`  | Persistent directory for the SQLite database.    |
| `DATABASE_URL`    | _(file under `DATA_DIR`)_ | SQLite connection string.                        |
| `DATABASE_ECHO`   | `false`                   | Echo SQL statements to the logs (debug only).    |
| `LOG_LEVEL`       | `INFO`                    | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`        |
| `SWAGGER_ENABLED` | `false`                   | Expose the Swagger UI at `/api/docs`.            |

### Mailserver (`docker exec`)

| Variable                     | Default                  | Description                                          |
| ---------------------------- | ------------------------ | ---------------------------------------------------- |
| `MAILSERVER_EXEC_ENABLED`    | `false`                  | Enables all mailserver management. Needs the socket. |
| `MAILSERVER_CONTAINER`       | `mailserver`             | Name (or ID) of the docker-mailserver container.     |
| `DOCKER_BINARY`              | `docker`                 | Path to the docker CLI inside this container.        |
| `MAILSERVER_CONFIG_DIR`      | `/tmp/docker-mailserver` | Config dir **inside** the mailserver container.      |
| `MAILSERVER_COMMAND_TIMEOUT` | `30`                     | Timeout (s) of a single `docker exec` command.       |
| `MAILSERVER_LOG_LINES`       | `200`                    | Trailing mail log lines returned by the log view.    |
| `MAILSERVER_STATS_HOURS`     | `24`                     | Time window covered by the dashboard statistics.     |
| `MAILSERVER_STATS_LOG_LINES` | `20000`                  | Log lines scanned to build those statistics.         |

### Fail2ban

| Variable                   | Default | Description                                     |
| -------------------------- | ------- | ----------------------------------------------- |
| `FAIL2BAN_ENABLED`         | `false` | Enables the fail2ban views. Needs the socket.   |
| `FAIL2BAN_COMMAND_TIMEOUT` | `15`    | Timeout (s) of a single fail2ban command.       |
| `FAIL2BAN_LOG_LINES`       | `200`   | Trailing fail2ban log lines returned to the UI. |

### Authentication & API keys

| Variable                 | Default     | Description                                            |
| ------------------------ | ----------- | ------------------------------------------------------ |
| `AUTH_COOKIE_NAME`       | `pc_token`  | Name of the session cookie.                            |
| `AUTH_TOKEN_TTL_SECONDS` | `28800`     | Session lifetime (8 h).                                |
| `API_KEYS_ENABLED`       | `true`      | Let users issue personal API keys from their profile.  |
| `API_KEY_HEADER`         | `X-API-Key` | Header carrying the key (`Authorization: Bearer` too). |
| `API_KEY_MAX_PER_USER`   | `10`        | Upper bound on live keys per account.                  |

> The auth cookie `Secure` flag is detected automatically from the request
> scheme (HTTPS), honouring `X-Forwarded-Proto` when the request comes through a
> trusted proxy. No manual `COOKIE_SECURE` toggle is needed.

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
