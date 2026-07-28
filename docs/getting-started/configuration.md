# Configuration

All settings are provided through environment variables (see
[`backend/.env.example`](https://github.com/cyr-ius/mailserver-ui/blob/master/backend/.env.example)
for the annotated list).

## Core

| Variable          | Default                   | Description                                                                                                                                                        |
| ----------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `SECRET_KEY`      | _(auto-generated)_        | Signs session cookies. If unset, a random key is generated and persisted to `DATA_DIR/secret_key` on first boot. Set it explicitly when running multiple replicas. |
| `ADMIN_USERNAME`  | `admin`                   | Default admin account seeded on first boot.                                                                                                                        |
| `DATA_DIR`        | `/var/lib/mailserver-ui`  | Persistent directory for the SQLite database.                                                                                                                      |
| `DATABASE_URL`    | _(file under `DATA_DIR`)_ | SQLite connection string.                                                                                                                                          |
| `DATABASE_ECHO`   | `false`                   | Echo SQL statements to the logs (debug only).                                                                                                                      |
| `LOG_LEVEL`       | `INFO`                    | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`                                                                                                                          |
| `SWAGGER_ENABLED` | `false`                   | Expose the Swagger UI at `/api/docs`.                                                                                                                              |

## Mailserver (`docker exec`)

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

## Fail2ban

The fail2ban views follow the mailserver's own `ENABLE_FAIL2BAN` toggle: when
the container starts with it off, no daemon runs and the UI says so instead of
offering actions that would do nothing. Nothing to enable on this side.

| Variable                   | Default | Description                                     |
| -------------------------- | ------- | ----------------------------------------------- |
| `FAIL2BAN_COMMAND_TIMEOUT` | `15`    | Timeout (s) of a single fail2ban command.       |
| `FAIL2BAN_LOG_LINES`       | `200`   | Trailing fail2ban log lines returned to the UI. |

## Authentication & personal access tokens

| Variable                      | Default    | Description                                                                                                                                                       |
| ----------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AUTH_COOKIE_NAME`            | `pc_token` | Name of the session cookie.                                                                                                                                       |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480`      | Session lifetime in minutes (8 h).                                                                                                                                |
| `PATS_ENABLED`                | `true`     | Let users issue personal access tokens from their profile. Set to `false` and the backend rejects every token, while the profile page hides the section entirely. |
| `PAT_MAX_PER_USER`            | `10`       | Upper bound on live tokens per account.                                                                                                                           |

**Note:** the auth cookie `Secure` flag is detected automatically from the
request scheme (HTTPS), honouring `X-Forwarded-Proto` when the request comes
through a trusted proxy. No manual `COOKIE_SECURE` toggle is needed.

A personal access token (PAT) is a single secret — `pat_` followed by 43 random
characters — shown once at creation and never again. It authenticates a REST
call as `Authorization: Bearer <token>`; the `pat_` prefix is what tells it
apart from a session JWT sent the same way. The scheme is declared in the
OpenAPI schema, so the Swagger UI's _Authorize_ dialog offers it when
`SWAGGER_ENABLED=true`.

```bash
curl -H "Authorization: Bearer pat_…" https://mail.example.com/api/mailboxes
```

**Note:** tokens replace the API keys of earlier versions. The `api_key` table
is dropped on the first startup that follows the upgrade — a token cannot be
derived from the digest of an existing key — so their owners reissue a token
from the profile page.

## Mail connector

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

## Audit trail

| Variable               | Default | Description                                                       |
| ---------------------- | ------- | ----------------------------------------------------------------- |
| `AUDIT_RETENTION_DAYS` | `0`     | Purge entries older than this on startup. `0` keeps them forever. |

## Reverse proxy & rate limiting

| Variable                          | Default           | Description                                       |
| --------------------------------- | ----------------- | ------------------------------------------------- |
| `TRUSTED_PROXIES`                 | _(empty)_         | Trusted proxy IPs/CIDRs; enables `X-Forwarded-*`. |
| `RATE_LIMIT_ENABLED`              | `true`            | Master switch for rate limiting.                  |
| `RATE_LIMIT_WINDOW_SECONDS`       | `60`              | Window applied to all `/api/*` routes.            |
| `RATE_LIMIT_MAX_REQUESTS`         | `100`             | Requests per IP per window.                       |
| `RATE_LIMIT_LOGIN_MAX_ATTEMPTS`   | `5`               | Login attempts before throttling.                 |
| `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `300`             | Window for those attempts.                        |
| `RATE_LIMIT_LOGIN_PATH`           | `/api/auth/login` | Path the stricter login budget applies to.        |

## OIDC / SSO

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
