"""
Docker Mailserver UI - FastAPI Backend
Copyright (C) 2021-2024  Cyr-ius (github.com/cyr-ius)
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .config import settings
from .database import create_db_and_tables, engine
from .exceptions import BaseAPIException
from .routers import audit, auth, fail2ban, groups, mailboxes, mailserver, users
from .routers import settings as settings_router
from .security import RateLimitMiddleware, SecurityHeadersMiddleware
from .services import audit_service, user_service
from .utils import resolve_safe_path

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise the database, seed the default admin and trim the audit trail."""
    create_db_and_tables()
    with Session(engine) as session:
        user_service.ensure_default_admin(session)
        audit_service.purge(session, settings.audit_retention_days)
    yield


app = FastAPI(
    title="Mailserver UI",
    description="REST API for docker mailserver management",
    version=settings.app_version,
    openapi_url="/api/openapi.json" if settings.swagger_enabled else None,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


# ── Exception handlers ────────────────────────────────────────────────────────
@app.exception_handler(BaseAPIException)
async def api_exception_handler(request: Request, exc: BaseAPIException) -> JSONResponse:
    """Turn typed application exceptions into consistent JSON error responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


# ── Middleware ───────────────────────────────────────────────────────────────
app.add_middleware(SecurityHeadersMiddleware)
if settings.rate_limit_enabled:
    # Added last → outermost: throttled requests are rejected before any work.
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
        login_max_attempts=settings.rate_limit_login_max_attempts,
        login_window_seconds=settings.rate_limit_login_window_seconds,
        login_path=settings.rate_limit_login_path,
    )

# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(groups.router)
app.include_router(mailboxes.router)
app.include_router(mailserver.router)
app.include_router(fail2ban.router)
app.include_router(settings_router.router)
app.include_router(audit.router)

# ── Self-hosted static assets (Swagger UI, no Internet dependency) ─────────────
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/api/static", StaticFiles(directory=static_dir), name="static")


@app.get("/api/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    if not settings.swagger_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="Docker Mailserver API",
        swagger_js_url="/api/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/api/static/swagger/swagger-ui.css",
        swagger_favicon_url="/api/static/favicon.ico",
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "app": "Docker Mailserver UI",
        "version": settings.app_version,
    }


# ── Serve Angular SPA (must be last) ─────────────────────────────────────────
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str) -> FileResponse:
    """
    Serve Angular static files with path traversal protection.

    Requests for existing static assets (JS, CSS, images) are served directly.
    All other paths fall back to index.html to support client-side SPA routing.
    Unknown or unsafe paths also fall back to index.html rather than 404-ing,
    letting the Angular router handle the error page.
    """

    # Resolve once at module load — avoids repeated filesystem calls per request.
    project_root = Path(__file__).resolve().parents[2]
    frontend_dist = (project_root / "frontend").resolve()
    frontend_index = frontend_dist / "index.html"

    if not frontend_index.is_file():
        logger.error("SPA index.html not found at %s", frontend_index)
        raise HTTPException(status_code=503, detail="Frontend not available.")

    safe = resolve_safe_path(full_path, frontend_dist)
    if safe is not None:
        return FileResponse(safe)

    # SPA fallback: Angular router handles unknown client-side routes.
    return FileResponse(frontend_index)
