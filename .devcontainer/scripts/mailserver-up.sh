#!/usr/bin/env bash
# ─── Start the dev docker-mailserver instance ───────────────────────────────
# Brings up (idempotently) the docker-mailserver container that the backend
# talks to. The backend edits the mailserver config via `docker exec`, so no
# config directory is shared on the host. Safe to run on every container start.
set -euo pipefail

WORKSPACE="${1:-/workspaces/mailserver-ui}"
COMPOSE_FILE="${WORKSPACE}/.devcontainer/docker-compose.mailserver.yml"

# Test domain/account seeded so the UI has something to show on first boot.
TEST_EMAIL="admin@example.com"
TEST_PASSWORD="password"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📮  Starting dev docker-mailserver"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 0. Docker availability ──────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  echo "  ⏭️   docker not available — rebuild the devcontainer to enable the"
  echo "       docker-in-docker feature, then re-run this script." >&2
  exit 0
fi

echo "  ⏳  Waiting for the Docker daemon..."
for _ in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! docker info >/dev/null 2>&1; then
  echo "  ❌  Docker daemon not reachable — aborting." >&2
  exit 1
fi

# ── 1. Bring the container up ───────────────────────────────────────────────
echo "  🚀  docker compose up -d (image pull may take a while on first run)..."
docker compose -f "${COMPOSE_FILE}" up -d

# ── 2. Wait until the container reports healthy/running ─────────────────────
echo "  ⏳  Waiting for the mailserver to become ready..."
for _ in $(seq 1 60); do
  status=$(docker inspect -f '{{.State.Status}}' mailserver 2>/dev/null || echo "missing")
  if [ "${status}" = "running" ]; then
    break
  fi
  sleep 2
done

# ── 3. Seed a test account (idempotent) ─────────────────────────────────────
# The UI can create accounts itself, but seeding one lets you log in an IMAP
# client immediately. `setup email add` is a no-op if the account exists.
if docker exec mailserver setup email list 2>/dev/null | grep -q "${TEST_EMAIL}"; then
  echo "  ✅  Test account already present: ${TEST_EMAIL}"
else
  echo "  👤  Creating test account ${TEST_EMAIL} (password: ${TEST_PASSWORD})"
  docker exec mailserver setup email add "${TEST_EMAIL}" "${TEST_PASSWORD}" || \
    echo "  ⚠️   Could not seed test account (mailserver may still be starting)."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Mailserver ready"
echo "     Container   : mailserver (hostname mail.example.com)"
echo "     SMTP/IMAP   : localhost:25 / :143 (plain, dev only)"
echo "     Test account: ${TEST_EMAIL} / ${TEST_PASSWORD}"
echo "     Config      : inside container (docker exec), volume mailserver-config"
echo "     Logs        : docker logs -f mailserver"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
