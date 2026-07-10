---
name: run-mailserver-ui
description: Build, launch, drive and screenshot the Mailserver UI app (Angular SPA + FastAPI) against a real docker-mailserver container. Use when asked to run, start, serve, screenshot, smoke-test or manually verify the app, or to reproduce a UI or API change end to end.
---

# Run Mailserver UI

Angular 22 SPA + FastAPI backend, deployed as one container. The backend drives a
**separate `docker-mailserver` container** over the Docker socket (`docker exec`),
so most of the UI is empty — or 502s — unless such a container is running.

Two committed pieces do the work. Paths are relative to the repo root.

| Piece                                         | What it does                                                                                                            |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `.claude/skills/run-mailserver-ui/launch.sh`  | Starts backend + Angular dev server on non-colliding ports, seeds a throwaway DB, captures the one-time admin password. |
| `.claude/skills/run-mailserver-ui/driver.mjs` | Playwright: signs in, navigates, clicks, screenshots, reports card/placeholder/error counts.                            |

## Prerequisites

A `docker-mailserver` container must be reachable, and the Docker socket must be
usable from this container:

```bash
docker ps --format '{{.Names}} {{.Status}}' | grep mailserver
```

If nothing matches, the app still starts — every mailserver tile just shows
"The mailserver container could not be reached". That is the `--degraded` mode below.

Dependencies (all verified in this container):

```bash
# Python deps into backend/.venv
(cd backend && uv sync)

# Node deps (already vendored in this repo; only needed on a clean clone)
(cd frontend && npm ci)

# Chromium for the driver. The browser download and the node package are
# SEPARATE steps — `playwright install` fetches the browser but not the module.
sudo -E env "PATH=$PATH" npx playwright install-deps chromium   # libglib-2.0 &co
npx playwright install chromium
mkdir -p /tmp/mailserver-ui-run && (cd /tmp/mailserver-ui-run && npm install playwright)
```

## Run (agent path)

```bash
# Start. Backend :8010, frontend :4210 — chosen to avoid a dev instance on :8000.
.claude/skills/run-mailserver-ui/launch.sh start
# → ready: http://127.0.0.1:4210  (admin / <generated password>)

# Drive it. Signs in automatically; state lives in /tmp/mailserver-ui-run.
node .claude/skills/run-mailserver-ui/driver.mjs \
  --route /dashboard \
  --screenshot /tmp/mailserver-ui-run/dashboard.png \
  --click 'button:has-text("Refresh")' \
  --dump --assert-loaded

.claude/skills/run-mailserver-ui/launch.sh stop
```

`launch.sh status` reports both ports. **Always `stop` when done** — a leftover
server makes the next `start` fail.

### driver.mjs flags

| Flag                         | Effect                                                         |
| ---------------------------- | -------------------------------------------------------------- |
| `--route /path`              | Page to land on after login (default `/dashboard`).            |
| `--screenshot FILE`          | Full-page PNG. **Open it** — a blank frame is a failed launch. |
| `--click 'SELECTOR'`         | Playwright selector, repeatable, clicked in order.             |
| `--dump`                     | Print the page's visible text.                                 |
| `--theme dark\|light`        | Flip `data-bs-theme` before screenshotting.                    |
| `--assert-loaded`            | Exit 1 if any loading skeleton is still on screen.             |
| `--assert-no-console-errors` | Exit 1 on any console/page error.                              |
| `--settle MS`                | Wait after load/click (default 2000).                          |

Routes worth driving: `/dashboard`, `/mailboxes`, `/mailserver/tls`,
`/mailserver/queue`, `/fail2ban`, `/users`.

### Exercising error paths

`--degraded` points the backend at a container name that does not exist, so every
`docker exec` endpoint returns 502 — **without touching the real mailserver**.
This is how to check that a failing tile degrades instead of blanking the page:

```bash
.claude/skills/run-mailserver-ui/launch.sh stop
.claude/skills/run-mailserver-ui/launch.sh start --degraded
node .claude/skills/run-mailserver-ui/driver.mjs --route /dashboard \
  --screenshot /tmp/mailserver-ui-run/degraded.png --assert-loaded
# 11 cards, 0 placeholders, each mailserver tile red. Non-container tiles still fill.
```

### Backend only

The API is faster to poke directly. `launch.sh start` writes the password to
`/tmp/mailserver-ui-run/password`:

```bash
PW=$(cat /tmp/mailserver-ui-run/password)
curl -s -c /tmp/c.jar -X POST http://127.0.0.1:8010/api/auth/login \
  -H 'Content-Type: application/json' -d "{\"username\":\"admin\",\"password\":\"$PW\"}"
curl -s -b /tmp/c.jar http://127.0.0.1:8010/api/mailserver/services | head -c 300
```

Set `SWAGGER_ENABLED=true` for `/api/docs`. Routes are not flattened into
`app.routes` on FastAPI 0.139 (they are `_IncludedRouter` objects) — enumerate
them with `app.openapi()['paths']` instead.

## Run (human path)

`frontend/proxy.conf.json` hardwires the dev proxy to `http://localhost:8000`, so
the human loop is a backend on `:8000` (`uv run uvicorn app.main:app --port 8000`)
plus `npm start` in `frontend/`. **Not exercised here** — `:8000` was already
owned by a developer's own instance, which is why `launch.sh` uses `:8010`/`:4210`
and writes its own proxy config. Useless headless anyway: you get a URL, no window.

## Test

```bash
(cd frontend && npx ng test --watch=false)   # vitest
(cd backend && .venv/bin/ruff check app && .venv/bin/ruff format --check app)
```

`ng test --browsers=ChromeHeadless` does **not** work — this project runs vitest,
which rejects that flag. **3 tests in `src/app/shared/user-menu/user-menu.spec.ts`
fail on a clean checkout** (as of 2026-07-10); that is pre-existing, not your change.

There are no backend tests. Exercise services by patching `container.run_in_container`.

## Gotchas

- **`pkill -f uvicorn` / `pkill -f "port 8010"` kills your own shell.** The
  pattern matches the `bash -c` process running it, whose argv contains the
  string. The command dies with **exit 144** and takes the backend with it. Use
  `launch.sh stop` (PID files), or filter on `/proc/$pid/comm` and skip `bash`.
- **Piping `node driver.mjs` into `head` truncates the run.** `head` closes the
  pipe, node dies of SIGPIPE _before_ writing the screenshot, and you end up
  reading a PNG from a previous run. Redirect to a file, then `grep` it.
- **Ports must be free before `start`.** A stale server answers the readiness
  probe while the new process dies with `EADDRINUSE`; you then test the old code.
  `launch.sh` refuses to start on a busy port for exactly this reason.
- **The admin password is printed once, to the log, only for a fresh database.**
  `launch.sh` deletes `app.db` on every `start` so a new one is always generated.
- **`setsid cmd & echo $!` records the wrong PID** — the wrapper's, not the
  session leader's, so `kill -- -$pid` signals a group that does not exist.
  `launch.sh`'s `spawn()` has the process write its own `$$` before `exec`.
- **Two `<main>` elements.** The app shell renders `main.app-main` and each routed
  page opens its own `<main>` (`.container-fluid` on the dashboard, `.container`
  elsewhere). A bare `locator('main')` is a strict-mode violation; the driver uses
  `main.app-main main`.
- **Navigating right after login aborts the dashboard's in-flight requests**, and
  each aborted tile logs `Dashboard tile failed to load` — errors that look real
  but are the driver's fault. `driver.mjs` waits for networkidle, then clears the
  console buffer after navigating.
- **A 401 in the console on every run is normal**: the app probes `/api/auth/me`
  before the session cookie exists.
- **`supervisorctl status` exits 3** whenever any process is not RUNNING — which
  is always, since docker-mailserver supervises the features it left disabled.
  A healthy container reports ~10 `STOPPED "Not started"` processes.
- **Dovecot answers for addresses that are not mailboxes** (an alias with its own
  maildir). `postfix-accounts.cf` is the source of truth.
- **`MAILSERVER_EXEC_ENABLED=true` and `FAIL2BAN_ENABLED=true` are mandatory**, or
  every mailserver/fail2ban endpoint returns 400 with "set MAILSERVER_EXEC_ENABLED".
  `launch.sh` sets both.

## Troubleshooting

| Symptom                                                                         | Fix                                                                                                                                                |
| ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `chrome-headless-shell: error while loading shared libraries: libglib-2.0.so.0` | `sudo -E env "PATH=$PATH" npx playwright install-deps chromium`. Plain `sudo npx …` fails with `npx: No such file or directory` — sudo drops PATH. |
| `Cannot find package 'playwright'`                                              | `npx playwright install chromium` fetches only the browser. Also `(cd /tmp/mailserver-ui-run && npm install playwright)`.                          |
| `TypeError: Cannot read properties of undefined (reading 'launch')`             | Playwright is CommonJS; imported by absolute path its exports land on `.default`. `driver.mjs` handles this.                                       |
| `strict mode violation: locator('main') resolved to 2 elements`                 | Use `main.app-main main`.                                                                                                                          |
| Command exits 144, backend gone                                                 | You ran `pkill -f` with a pattern matching your own shell. See Gotchas.                                                                            |
| `address already in use` in `backend.log`                                       | Previous run still up: `launch.sh stop`, or `MSUI_API_PORT=8011 launch.sh start`.                                                                  |
| Every tile red: "container could not be reached"                                | Either no `mailserver` container (`docker ps`), or you started `--degraded`.                                                                       |
| `no admin password in the log`                                                  | The backend died at startup. Read `/tmp/mailserver-ui-run/backend.log`.                                                                            |

## Environment overrides

`MSUI_RUN_DIR` (default `/tmp/mailserver-ui-run`), `MSUI_API_PORT` (8010),
`MSUI_WEB_PORT` (4210), `MSUI_CONTAINER` (`mailserver`).
