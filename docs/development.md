# Development

## Backend (FastAPI)

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

Over plain HTTP the auth cookie is issued without the `Secure` flag
automatically, so local development works without any extra configuration.

A throwaway docker-mailserver instance for end-to-end testing is available with
`scripts/mailserver-up.sh` (see
[`.devcontainer/docker-compose.mailserver.yml`](https://github.com/cyr-ius/mailserver-ui/blob/master/.devcontainer/docker-compose.mailserver.yml)).

## Frontend (Angular)

```bash
cd frontend
npm install
npm start                               # http://localhost:4200 (proxied to :8000)
```

## Building the Docker image locally

The repository's `docker-compose.yml` targets the published image
(`ghcr.io/cyr-ius/mailserver-ui:latest`), so it never rebuilds on its own. To
test packaging changes (Dockerfile, dependency bumps) before they land on
GHCR, build and run the image directly:

```bash
docker build -t mailserver-ui:dev .
docker run -d \
  --name mailserver-ui-dev \
  -p 8000:8000 \
  -e MAILSERVER_CONTAINER=mailserver \
  -v mailserver-ui-dev:/var/lib/mailserver-ui \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  mailserver-ui:dev
```

## Linting

```bash
# Backend
cd backend && uv run ruff check app/ && uv run ruff format --check app/
# Frontend
cd frontend && npx prettier --check "src/app/**/*.{ts,html,css}"
```

## Building this documentation site

This site is built with [MkDocs](https://www.mkdocs.org/) and the
[Material theme](https://squidfunk.github.io/mkdocs-material/).

```bash
pip install -r docs/requirements.txt
mkdocs serve   # http://localhost:8000
```

It is automatically built and published to GitHub Pages on every push to
`master` that touches `docs/**` or `mkdocs.yml`.
