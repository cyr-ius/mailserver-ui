"""Audit service: append-only trail of security-relevant actions.

Every write goes through :func:`record`, which persists the entry and hands it to
the mail connector for notification. The trail is never updated: the only way an
entry leaves the table is :func:`purge`, applied on startup when a retention
window is configured.

Recording must never break the action it describes. A failure to write the entry
(or to notify) is logged and swallowed — losing an audit line is bad, but failing
a mailbox deletion *after* it happened, because the trail could not be written,
is worse and leaves the client with a wrong answer.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func
from sqlmodel import Session, col, select

from ..client_ip import get_client_ip
from ..models.audit_models import AuditCategory, AuditLog, AuditStatus
from ..services import mail_service, settings_service

logger = logging.getLogger(__name__)

#: Cap on a page of entries, so a client cannot ask for the whole table at once.
MAX_PAGE_SIZE = 200


async def record(
    session: Session,
    *,
    category: AuditCategory,
    action: str,
    actor: str = "anonymous",
    target: str = "",
    status: AuditStatus = "success",
    detail: str = "",
    request: Request | None = None,
) -> None:
    """Append one entry to the audit trail and notify the mail connector.

    ``detail`` is free-form context (what changed, why it was rejected). It must
    never carry a secret: record the fact, not the value.
    """
    entry = AuditLog(
        actor=actor or "anonymous",
        category=category,
        action=action,
        target=target,
        status=status,
        detail=detail[:2000],
        ip=get_client_ip(request) or "" if request is not None else "",
    )
    try:
        session.add(entry)
        session.commit()
        session.refresh(entry)
    except Exception as exc:  # noqa: BLE001 — the audited action already happened
        session.rollback()
        logger.error("Failed to record audit entry %s: %s", action, exc)
        return

    try:
        # Detached snapshot: the notification is sent in the background, long
        # after this request's session is closed.
        config = settings_service.get_mail_settings(session)
        mail_service.notify(config.model_copy(), entry)
    except Exception as exc:  # noqa: BLE001 — notification is best-effort
        logger.error("Failed to dispatch audit notification for %s: %s", action, exc)


# ── Queries ──────────────────────────────────────────────────────────────────


def list_entries(
    session: Session,
    *,
    actor: str = "",
    action: str = "",
    category: str = "",
    status: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    """Return a page of entries, newest first, plus the total matching the filters."""
    filters = []
    if actor:
        filters.append(col(AuditLog.actor) == actor)
    if action:
        filters.append(col(AuditLog.action) == action)
    if category:
        filters.append(col(AuditLog.category) == category)
    if status:
        filters.append(col(AuditLog.status) == status)

    total_statement = select(func.count()).select_from(AuditLog)
    page_statement = select(AuditLog)
    for condition in filters:
        total_statement = total_statement.where(condition)
        page_statement = page_statement.where(condition)

    total = session.exec(total_statement).one()
    entries = session.exec(
        page_statement.order_by(
            col(AuditLog.created_at).desc(), col(AuditLog.id).desc()
        )
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), MAX_PAGE_SIZE))
    ).all()
    return list(entries), int(total)


def purge(session: Session, retention_days: int) -> int:
    """Delete entries older than ``retention_days``. ``0`` keeps them forever."""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    stale = session.exec(
        select(AuditLog).where(col(AuditLog.created_at) < cutoff)
    ).all()
    for entry in stale:
        session.delete(entry)
    session.commit()
    if stale:
        logger.info(
            "Purged %d audit entries older than %d days", len(stale), retention_days
        )
    return len(stale)
