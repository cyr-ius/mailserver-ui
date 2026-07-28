# Architecture

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

## Components

| Layer    | Tech                                       |
| -------- | ------------------------------------------ |
| Frontend | Angular 22 (signals, zoneless, standalone) |
| Backend  | FastAPI 0.139 (async, Pydantic v2)         |
| Database | SQLite via SQLModel                        |
| UI       | Bootstrap 5.3 / Bootstrap Icons            |
| Runtimes | Python 3.14 / Node.js 18+                  |

The backend and the built frontend are served from a **single container**:
FastAPI serves the compiled Angular SPA as static files alongside the `/api/*`
REST endpoints.

## Backend layout

```
backend/app/
├── routers/    # FastAPI routers (one per resource: users, mailboxes, mailserver, ...)
├── services/   # Business logic, docker exec orchestration, database access
├── models/     # SQLModel / Pydantic models
├── auth.py     # Session & token authentication
├── security.py # Password hashing, JWT
├── config.py   # Settings (environment variables)
└── main.py     # FastAPI app factory
```

## Frontend layout

```
frontend/src/app/
├── core/       # Services, guards, interceptors — one service per API resource
├── features/   # Route-level feature components (dashboard, mailboxes, users, mailserver/*, settings/*, ...)
└── shared/     # Reusable components (theme toggle, pending-actions bell, ...)
```

## Authentication

Two schemes are supported side by side:

- **Session cookie** — issued on local or OIDC sign-in, used by the SPA.
- **Personal access token (PAT)** — `pat_` followed by 43 random characters,
  shown once at creation, sent as `Authorization: Bearer <token>` for
  programmatic REST access. Declared in the OpenAPI schema so the Swagger UI's
  _Authorize_ dialog offers it when `SWAGGER_ENABLED=true`.

```bash
curl -H "Authorization: Bearer pat_…" https://mail.example.com/api/mailboxes
```
