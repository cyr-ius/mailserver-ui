"""Database engine configuration.

A single SQLite database (path derived from ``DATA_DIR``) stores the local and
OIDC users. The engine is created once at import time; tables are created on
application startup via :func:`create_db_and_tables`. The request-scoped
session dependency lives in :mod:`app.depends`.
"""

import logging
from pathlib import Path

from sqlmodel import SQLModel, create_engine

from app.config import settings

logger = logging.getLogger(__name__)

# ``check_same_thread`` must be disabled so the connection can be shared across
# the threadpool FastAPI uses for synchronous dependencies. It is safe here
# because sessions are short-lived and never shared between threads.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    connect_args=_connect_args,
)


def _ensure_sqlite_dir() -> None:
    """Create the parent directory of a SQLite database file if missing."""
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        return
    db_path = Path(settings.database_url[len(prefix) :])
    db_path.parent.mkdir(parents=True, exist_ok=True)


def create_db_and_tables() -> None:
    """Create all tables declared by ``table=True`` SQLModel models."""
    _ensure_sqlite_dir()
    # Import models so their tables are registered on SQLModel.metadata.
    from app import settings_models, user_models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    logger.info("Database ready at %s", settings.database_url)
