"""Application settings endpoints (admin only).

Currently exposes the OIDC/SSO configuration. Values are stored in the database
and edited from the UI; the client secret is write-only and never returned.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth import SessionUser
from app.depends import get_session, require_admin
from app.services import settings_service
from app.settings_models import OidcSettings, OidcSettingsPublic, OidcSettingsUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[SessionUser, Depends(require_admin)]


def _to_public(config: OidcSettings) -> OidcSettingsPublic:
    """Serialise the stored config without leaking the client secret."""
    return OidcSettingsPublic.model_validate(
        {**config.model_dump(), "client_secret_set": bool(config.client_secret)}
    )


@router.get("/oidc", response_model=OidcSettingsPublic)
async def get_oidc(session: SessionDep, _admin: AdminDep) -> OidcSettingsPublic:
    """Return the current OIDC configuration (admin only)."""
    return _to_public(settings_service.get_oidc_settings(session))


@router.put("/oidc", response_model=OidcSettingsPublic)
async def update_oidc(
    payload: OidcSettingsUpdate,
    session: SessionDep,
    _admin: AdminDep,
) -> OidcSettingsPublic:
    """Update the OIDC configuration (admin only).

    Leave ``client_secret`` empty to keep the stored secret unchanged.
    """
    return _to_public(settings_service.update_oidc_settings(session, payload))
