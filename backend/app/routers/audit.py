"""Audit trail endpoints (admin only).

The trail is append-only: it is read here, and written from the services that
perform the audited actions. There is no endpoint to create or edit an entry.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..auth import SessionUser
from ..depends import get_session, require_admin
from ..models.audit_models import AuditLog, AuditLogPublic, AuditPage
from ..services import audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[SessionUser, Depends(require_admin)]


def _to_public(entry: AuditLog) -> AuditLogPublic:
    return AuditLogPublic.model_validate(entry.model_dump())


@router.get("", response_model=AuditPage)
async def list_audit_entries(
    session: SessionDep,
    _admin: AdminDep,
    actor: Annotated[str, Query(max_length=255)] = "",
    action: Annotated[str, Query(max_length=64)] = "",
    category: Annotated[str, Query(max_length=32)] = "",
    status: Annotated[str, Query(max_length=16)] = "",
    limit: Annotated[int, Query(ge=1, le=audit_service.MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    """Return a page of audit entries, newest first (admin only)."""
    entries, total = audit_service.list_entries(
        session,
        actor=actor,
        action=action,
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )
    return AuditPage(items=[_to_public(entry) for entry in entries], total=total)
