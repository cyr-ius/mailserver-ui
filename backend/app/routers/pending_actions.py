"""Pending operator actions endpoints (admin only).

Surfaces the mailserver settings changes still awaiting a container restart
(see :mod:`app.services.pending_action_service`). Entries are written by the
mailserver and fail2ban routers as their settings endpoints are called; there
is no endpoint to create one directly, only to list and dismiss them.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from ..auth import SessionUser
from ..depends import get_session, require_admin
from ..models.pending_action_models import PendingActionsSummary
from ..services import pending_action_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pending-actions", tags=["pending-actions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminDep = Annotated[SessionUser, Depends(require_admin)]


@router.get("", response_model=PendingActionsSummary)
async def list_pending_actions(
    session: SessionDep, _admin: AdminDep
) -> PendingActionsSummary:
    """Return every pending action, most recently changed first (admin only)."""
    return await pending_action_service.summary(session)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_pending_actions(session: SessionDep, _admin: AdminDep) -> None:
    """Dismiss every pending action, e.g. once the mailserver has restarted (admin only)."""
    await pending_action_service.clear_all(session)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_pending_action(key: str, session: SessionDep, _admin: AdminDep) -> None:
    """Dismiss a single pending action (admin only)."""
    await pending_action_service.clear(session, key)
