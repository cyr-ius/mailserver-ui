"""
Docker Mailserver UI - FastAPI Backend
Copyright (C) 2021-2024  Cyr-ius (github.com/cyr-ius)
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import auth
from .security import RateLimitMiddleware, SecurityHeadersMiddleware
from .utils import resolve_safe_path

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


app = FastAPI(
    title="PowerDNS UI",
    description="REST API for docker mailserver management",
    version=settings.app_version,
    openapi_url="/api/openapi.json" if settings.swagger_enabled else None,
    docs_url=None,
    redoc_url=None,
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

# ── Self-hosted static assets (Swagger UI, no Internet dependency) ─────────────
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/api/static", StaticFiles(directory=static_dir), name="static")


@app.get("/api/docs", include_in_schema=False)
async def swagger_ui():
    if not settings.swagger_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="Docker Mailserver API",
        swagger_js_url="/api/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/api/static/swagger/swagger-ui.css",
        swagger_favicon_url="/favicon.ico",
    )


@app.get("/api/health")
async def health() -> dict:
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
