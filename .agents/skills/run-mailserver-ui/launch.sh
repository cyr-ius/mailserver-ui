#!/usr/bin/env bash
# Launch (or stop) Mailserver UI for an agent to drive.
#
# Starts the FastAPI backend and the Angular dev server on ports that do not
# collide with a developer's own instance on :8000, seeds a throwaway SQLite
# database, and captures the admin password FastAPI prints exactly once.
#
#   launch.sh start [--degraded]   bring both up, write state to $MSUI_RUN_DIR
#   launch.sh stop                 kill only the PIDs we started
#   launch.sh status               report what is up
#
# --degraded points the backend at a container that does not exist, so every
# `docker exec` endpoint returns 502. That is how you exercise error paths
# without touching the real mailserver.
set -uo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
RUN_DIR="${MSUI_RUN_DIR:-/tmp/mailserver-ui-run}"
API_PORT="${MSUI_API_PORT:-8010}"
WEB_PORT="${MSUI_WEB_PORT:-4210}"
CONTAINER="${MSUI_CONTAINER:-mailserver}"

# Start a detached process and record a PID we can actually signal.
#
# `setsid cmd & echo $!` records the *wrapper's* PID, which is not the session
# leader setsid forks — `kill -- -$pid` then targets a process group that does
# not exist. Having the process write its own PID before exec'ing keeps the two
# in step: it is the session leader, so its PID is also its process-group ID.
spawn() {
  local pidfile="$1" logfile="$2"; shift 2
  setsid nohup bash -c 'echo $$ > "$1"; shift; exec "$@"' _ "$pidfile" "$@" \
    > "$logfile" 2>&1 < /dev/null &
  disown 2>/dev/null || true
}

# A port left busy by a previous run makes the readiness probe below succeed
# against the *old* server while the new one dies with EADDRINUSE. Fail loudly.
require_free_port() {
  local port="$1" name="$2"
  if curl -s -m 1 -o /dev/null "http://127.0.0.1:${port}/" 2>/dev/null; then
    echo "port ${port} (${name}) is already serving. Run 'launch.sh stop' first," >&2
    echo "or pick another with MSUI_${name}_PORT=... (a dev instance often owns :8000)." >&2
    return 1
  fi
}

wait_for_port_free() {
  local port="$1"
  for _ in $(seq 1 15); do
    curl -s -m 1 -o /dev/null "http://127.0.0.1:${port}/" 2>/dev/null || return 0
    sleep 1
  done
  return 1
}

start() {
  [ "${1:-}" = "--degraded" ] && CONTAINER="no-such-container-$$"

  require_free_port "$API_PORT" API || return 1
  require_free_port "$WEB_PORT" WEB || return 1

  mkdir -p "$RUN_DIR"
  # A fresh database is what makes the backend print a new admin password;
  # reusing one leaves us with a password we can never recover.
  rm -f "$RUN_DIR/app.db" "$RUN_DIR/password" "$RUN_DIR"/*.log

  cat > "$RUN_DIR/proxy.json" <<JSON
{ "/api": { "target": "http://127.0.0.1:${API_PORT}", "secure": false, "changeOrigin": true } }
JSON

  echo "→ backend on :${API_PORT} (container: ${CONTAINER})"
  ( cd "$REPO/backend" && \
    DATABASE_URL="sqlite:///$RUN_DIR/app.db" \
    SECRET_KEY="local-run-only-not-a-production-secret" \
    MAILSERVER_EXEC_ENABLED=true \
    FAIL2BAN_ENABLED=true \
    MAILSERVER_CONTAINER="$CONTAINER" \
    RATE_LIMIT_ENABLED=false \
    spawn "$RUN_DIR/backend.pid" "$RUN_DIR/backend.log" \
      .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" )

  for _ in $(seq 1 30); do
    curl -sf -m 2 -o /dev/null "http://127.0.0.1:${API_PORT}/api/health" && break
    sleep 1
  done
  if ! curl -sf -m 2 -o /dev/null "http://127.0.0.1:${API_PORT}/api/health"; then
    echo "backend failed to start:" >&2; tail -20 "$RUN_DIR/backend.log" >&2; return 1
  fi

  # FastAPI prints the seeded admin password exactly once, and only for a fresh
  # database — which is why start() deletes app.db above.
  for _ in $(seq 1 10); do
    grep -oE "Generated password: \S+" "$RUN_DIR/backend.log" \
      | tail -1 | sed 's/Generated password: //' > "$RUN_DIR/password"
    [ -s "$RUN_DIR/password" ] && break
    sleep 1
  done
  if [ ! -s "$RUN_DIR/password" ]; then
    echo "no admin password in the log:" >&2; tail -20 "$RUN_DIR/backend.log" >&2; return 1
  fi

  echo "→ frontend on :${WEB_PORT}"
  ( cd "$REPO/frontend" && \
    spawn "$RUN_DIR/frontend.pid" "$RUN_DIR/frontend.log" \
      npx ng serve --port "$WEB_PORT" --proxy-config "$RUN_DIR/proxy.json" )

  for _ in $(seq 1 60); do
    curl -sf -m 2 -o /dev/null "http://127.0.0.1:${WEB_PORT}/" && break
    sleep 1
  done
  if ! curl -sf -m 2 -o /dev/null "http://127.0.0.1:${WEB_PORT}/"; then
    echo "frontend failed to start:" >&2; tail -20 "$RUN_DIR/frontend.log" >&2; return 1
  fi

  cat > "$RUN_DIR/env" <<ENV
MSUI_BASE=http://127.0.0.1:${WEB_PORT}
MSUI_API=http://127.0.0.1:${API_PORT}
MSUI_CONTAINER=${CONTAINER}
ENV
  echo "ready: http://127.0.0.1:${WEB_PORT}  (admin / $(cat "$RUN_DIR/password"))"
}

stop() {
  # Kill by recorded PID. Never `pkill -f "port 8010"` or `pkill -f uvicorn`:
  # the pattern also matches the shell running it (its own argv contains the
  # string), so the shell kills itself and the command dies with exit 144.
  for role in frontend backend; do
    pidfile="$RUN_DIR/$role.pid"
    [ -f "$pidfile" ] || continue
    pid="$(cat "$pidfile")"
    # ng serve forks children; spawn() made the process a session leader, so its
    # PID is the process-group ID and a negative signal reaches the whole tree.
    kill -- "-${pid}" 2>/dev/null || kill "$pid" 2>/dev/null
    rm -f "$pidfile"
    echo "stopped $role (pgid $pid)"
  done
  # uvicorn and ng serve take a moment to release their sockets; starting again
  # before they do gives EADDRINUSE against a readiness probe that still passes.
  wait_for_port_free "$API_PORT" || echo "warning: :${API_PORT} still busy" >&2
  wait_for_port_free "$WEB_PORT" || echo "warning: :${WEB_PORT} still busy" >&2
}

status() {
  curl -s -m 2 -o /dev/null -w "backend  :${API_PORT} → %{http_code}\n" "http://127.0.0.1:${API_PORT}/api/health"
  curl -s -m 2 -o /dev/null -w "frontend :${WEB_PORT} → %{http_code}\n" "http://127.0.0.1:${WEB_PORT}/"
}

case "${1:-start}" in
  start) shift; start "${1:-}" ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: launch.sh [start [--degraded] | stop | status]" >&2; exit 2 ;;
esac
