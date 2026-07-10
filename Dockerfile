# ─── Stage 1: Build Angular Frontend ──────────────────────────────────────
FROM node:26-alpine AS frontend-builder

WORKDIR /build/frontend

# Install dependencies
COPY frontend/package.json ./
RUN npm install

# Copy source and build
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: Final container ─────────────────────────────────────────────
FROM python:3.14-alpine

LABEL maintainer="cyr-ius <https://github.com/cyr-ius>"
LABEL org.opencontainers.image.title="Docker Mailserver UI"
LABEL org.opencontainers.image.description="Webinterface for Docker Mailserver "
LABEL org.opencontainers.image.source="https://github.com/cyr-ius/docker-mailserver-ui"
LABEL org.opencontainers.image.url="https://github.com/cyr-ius/docker-mailserver-ui"
LABEL org.opencontainers.image.licenses="MIT"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_NO_CACHE=true
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PYTHONUNBUFFERED=1
ENV PATH="$UV_PROJECT_ENVIRONMENT/bin:$PATH"

RUN apk add --no-cache docker && \
    update-ca-certificates && \
    rm -rf /var/cache/apk/*

WORKDIR /app

# Install Python dependencies from requirements
RUN --mount=type=bind,source=backend/pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/uv.lock,target=uv.lock \
    uv sync --frozen --no-dev

# Copy built frontend
COPY --from=frontend-builder /build/frontend/dist/mailserver-ui/browser ./frontend

# Copy Python backend
COPY backend/ ./backend

# Pass application version from build ARG to runtime ENV for about endpoint
ARG VERSION
ENV APP_VERSION=${VERSION}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# For staging pipeline (if needed)
EXPOSE 8000

# Volumes for registry data and config (if you want to persist or customize config)
VOLUME [ "/var/lib/mailserver-ui" ]

# Start application
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
