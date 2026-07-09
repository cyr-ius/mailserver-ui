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
  (admin only).
- **Mailbox management** — create, reset the password of, and delete
  docker-mailserver accounts. Mailboxes live in the shared `postfix-accounts.cf`
  file (see `MAILSERVER_CONFIG_DIR`), not in the application database.
- Group-based role mapping and optional group-restricted access for OIDC users.

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

## Configuration

All settings are provided through environment variables (see
[`backend/.env.example`](backend/.env.example) for the full list). The essentials:

| Variable                | Default                      | Description                                       |
| ----------------------- | ---------------------------- | ------------------------------------------------- |
| `SECRET_KEY`            | _(change me)_                | Signs session cookies — **must** be set in prod.  |
| `ADMIN_USERNAME`        | `admin`                      | Default admin account seeded on first boot.       |
| `DATA_DIR`              | `/var/lib/mailserver-ui`     | Persistent directory for the SQLite database.     |
| `MAILSERVER_CONFIG_DIR` | `/var/lib/mailserver-config` | docker-mailserver config dir (shared volume).     |
| `TRUSTED_PROXIES`       | _(empty)_                    | Trusted proxy IPs/CIDRs; enables `X-Forwarded-*`. |
| `LOG_LEVEL`             | `INFO`                       | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`         |

> The auth cookie `Secure` flag is detected automatically from the request
> scheme (HTTPS), honouring `X-Forwarded-Proto` when the request comes through a
> trusted proxy. No manual `COOKIE_SECURE` toggle is needed.

### OIDC / SSO

OIDC is managed from **Settings → OIDC / SSO** in the UI and stored in the
database. The `OIDC_*` environment variables are read **only on the first
startup** to seed the initial configuration (for backwards compatibility);
afterwards the database is authoritative and changing those variables has no
effect. Configure the issuer URL, client ID/secret, redirect URI, scopes and
group mappings directly in the interface.

## Development

### Backend (FastAPI)

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

Over plain HTTP the auth cookie is issued without the `Secure` flag
automatically, so local development works without any extra configuration.

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
