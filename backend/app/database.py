"""Database engine configuration.

A single SQLite database (path derived from ``DATA_DIR``) stores the local and
OIDC users. The engine is created once at import time; tables are created on
application startup via :func:`create_db_and_tables`. The request-scoped
session dependency lives in :mod:`app.depends`.
"""

import logging
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy import text as sql_text
from sqlmodel import SQLModel, create_engine

from .config import settings

logger = logging.getLogger(__name__)

# ``create_all`` only creates missing *tables*, never missing columns, and the
# project carries no migration tool yet — so schema changes are replayed here on
# every startup, guarded by an existence check. Drop this once Alembic lands.

# New columns, with the DDL fragment used to append them.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "group": {"role": "VARCHAR(32) NOT NULL DEFAULT 'guest'"},
    "oidcsettings": {
        "manager_group_claim": "VARCHAR NOT NULL DEFAULT ''",
        "manager_group": "VARCHAR NOT NULL DEFAULT ''",
    },
    # Accounts that predate deactivation are active, which is what they were.
    "user": {"is_active": "BOOLEAN NOT NULL DEFAULT 1"},
}

# Columns renamed as part of the three-role model, as ``(table, old, new)``. The
# value is carried over before the old column is dropped, so a deployment that
# had configured an OIDC user group keeps its mapping — now onto the mailbox
# manager role.
_RENAMED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("oidcsettings", "user_group_claim", "manager_group_claim"),
    ("oidcsettings", "user_group", "manager_group"),
)

# Tables left behind by a superseded feature. ``api_key`` gave way to ``pat``:
# a personal access token also carries a short secret, which cannot be derived
# from the digest of an existing key — so the old keys are dropped rather than
# migrated, and their owners reissue a token from the profile page.
_DROPPED_TABLES: tuple[str, ...] = ("api_key",)

# ``check_same_thread`` must be disabled so the connection can be shared across
# the threadpool FastAPI uses for synchronous dependencies. It is safe here
# because sessions are short-lived and never shared between threads.
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

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


def _migrate_schema() -> None:
    """Bring an existing database up to the current model definitions."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    columns = {
        table: {c["name"] for c in inspector.get_columns(table)} for table in tables
    }

    with engine.begin() as connection:
        for table, additions in _ADDED_COLUMNS.items():
            if table not in tables:
                continue
            for name, ddl in additions.items():
                if name in columns[table]:
                    continue
                connection.execute(
                    sql_text(f'ALTER TABLE "{table}" ADD COLUMN {name} {ddl}')
                )
                columns[table].add(name)
                logger.info("Added column %s.%s", table, name)

        for table, old, new in _RENAMED_COLUMNS:
            if table not in tables or old not in columns[table]:
                continue
            connection.execute(sql_text(f'UPDATE "{table}" SET {new} = {old}'))
            connection.execute(sql_text(f'ALTER TABLE "{table}" DROP COLUMN {old}'))
            columns[table].discard(old)
            logger.info("Migrated column %s.%s to %s", table, old, new)

        for table in _DROPPED_TABLES:
            if table not in tables:
                continue
            connection.execute(sql_text(f'DROP TABLE "{table}"'))
            logger.warning(
                "Dropped obsolete table %s: its credentials must be reissued as personal "
                "access tokens from the profile page",
                table,
            )


def create_db_and_tables() -> None:
    """Create all tables declared by ``table=True`` SQLModel models."""
    _ensure_sqlite_dir()
    # Import models so their tables are registered on SQLModel.metadata.
    from .models import (  # noqa: F401
        audit_models,
        mail_models,
        pat_models,
        user_models,
    )

    SQLModel.metadata.create_all(engine)
    _migrate_schema()
    logger.info("Database ready at %s", settings.database_url)
