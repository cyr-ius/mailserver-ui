# Installation

## Quick start (Docker Compose)

A ready-to-use [`docker-compose.yml`](https://github.com/cyr-ius/mailserver-ui/blob/master/docker-compose.yml)
is provided at the root of the repository. It starts both docker-mailserver and
the UI with a sensible default configuration.

```bash
cp backend/.env.example .env   # sensible defaults; nothing is required
docker compose up -d --build
```

The UI is available on <http://localhost:8000>. On first startup, check the
logs for the generated admin password:

```bash
docker compose logs mailserver-ui | grep "Generated password"
```

## Docker run (one-liner)

If you already have a running `docker-mailserver` container (here named
`mailserver`), you can start the UI alone:

```bash
docker run -d \
  --name mailserver-ui \
  -p 8000:8000 \
  -e MAILSERVER_CONTAINER=mailserver \
  -v mailserver-ui:/var/lib/mailserver-ui \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  --restart unless-stopped \
  ghcr.io/cyr-ius/mailserver-ui:latest
```

- `-v /var/run/docker.sock:/var/run/docker.sock:ro` is **required** — the UI
  drives docker-mailserver through `docker exec` (see
  [Architecture](../architecture.md)).
- `-e MAILSERVER_CONTAINER=mailserver` must match the name (or ID) of your
  docker-mailserver container.
- `-v mailserver-ui:/var/lib/mailserver-ui` persists the SQLite database
  (users, settings, audit log) across restarts.

The UI is then available on <http://localhost:8000>; check the generated admin
password with:

```bash
docker logs mailserver-ui | grep "Generated password"
```
