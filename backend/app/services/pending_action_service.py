"""Tracks pending operator actions — currently, only "restart the mailserver".

Saving a docker-mailserver config file that is only read at container startup
leaves the running container out of sync with it until the next restart.
Rather than scattering that warning across every settings page, each such write
calls :func:`mark_restart_required`, which registers or refreshes one row per
area; the navbar bell reads the aggregate through :func:`list_all`.
"""

import logging
from datetime import UTC, datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models.pending_action_models import PendingAction

logger = logging.getLogger(__name__)


async def mark_restart_required(
    session: AsyncSession, *, key: str, title: str, detail: str = ""
) -> None:
    """Register a pending restart for ``key``, refreshing it if already pending.

    Failing to record this is logged and swallowed: the settings write it
    describes already succeeded, and must not be undone by a bookkeeping error.
    """
    try:
        result = await session.exec(
            select(PendingAction).where(col(PendingAction.key) == key)
        )
        existing = result.first()
        if existing:
            existing.title = title
            existing.detail = detail
            existing.updated_at = datetime.now(UTC)
            session.add(existing)
        else:
            session.add(PendingAction(key=key, title=title, detail=detail))
        await session.commit()
    except Exception as exc:  # noqa: BLE001 — the settings write already happened
        await session.rollback()
        logger.error("Failed to record pending action %s: %s", key, exc)


async def list_all(session: AsyncSession) -> list[PendingAction]:
    """Return every pending action, newest change first."""
    result = await session.exec(
        select(PendingAction).order_by(col(PendingAction.updated_at).desc())
    )
    return list(result.all())


async def clear(session: AsyncSession, key: str) -> None:
    """Dismiss a single pending action; a missing ``key`` is not an error."""
    result = await session.exec(
        select(PendingAction).where(col(PendingAction.key) == key)
    )
    existing = result.first()
    if existing:
        await session.delete(existing)
        await session.commit()


async def clear_all(session: AsyncSession) -> None:
    """Dismiss every pending action, e.g. once the mailserver has been restarted."""
    result = await session.exec(select(PendingAction))
    for item in result.all():
        await session.delete(item)
    await session.commit()
