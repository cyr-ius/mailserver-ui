"""Application settings endpoints (admin only).

Exposes the OIDC/SSO configuration and the outgoing mail connector. Values are
stored in the database and edited from the UI; secrets (the OIDC client secret,
the SMTP password) are write-only and never returned.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from ..auth import SessionUser
from ..depends import get_session, require_admin
from ..models.mail_models import (
    MailSettings,
    MailSettingsPublic,
    MailSettingsUpdate,
    MailTestRequest,
    MailTestResult,
)
from ..models.settings_models import (
    OidcSettings,
    OidcSettingsPublic,
    OidcSettingsUpdate,
)
from ..services import audit_service, mail_service, settings_service

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
    request: Request,
    session: SessionDep,
    admin: AdminDep,
) -> OidcSettingsPublic:
    """Update the OIDC configuration (admin only).

    Leave ``client_secret`` empty to keep the stored secret unchanged.
    """
    config = settings_service.update_oidc_settings(session, payload)
    await audit_service.record(
        session,
        request=request,
        category="settings",
        action="settings.oidc.update",
        actor=admin.username,
        target="oidc",
        detail=f"enabled={config.enabled} oidc_only={config.oidc_only} issuer={config.issuer}",
    )
    return _to_public(config)


# ── Mail connector ───────────────────────────────────────────────────────────


def _mail_to_public(config: MailSettings) -> MailSettingsPublic:
    """Serialise the stored connector without leaking the SMTP password."""
    return MailSettingsPublic.model_validate(
        {**config.model_dump(), "password_set": bool(config.password)}
    )


@router.get("/mail", response_model=MailSettingsPublic)
async def get_mail(session: SessionDep, _admin: AdminDep) -> MailSettingsPublic:
    """Return the current mail connector configuration (admin only)."""
    return _mail_to_public(settings_service.get_mail_settings(session))


@router.put("/mail", response_model=MailSettingsPublic)
async def update_mail(
    payload: MailSettingsUpdate,
    request: Request,
    session: SessionDep,
    admin: AdminDep,
) -> MailSettingsPublic:
    """Update the mail connector (admin only).

    Leave ``password`` empty to keep the stored one unchanged.
    """
    config = settings_service.update_mail_settings(session, payload)
    await audit_service.record(
        session,
        request=request,
        category="settings",
        action="settings.mail.update",
        actor=admin.username,
        target="mail",
        detail=(
            f"enabled={config.enabled} host={config.host}:{config.port} "
            f"auth_events={config.notify_auth_events} audit_events={config.notify_audit_events}"
        ),
    )
    return _mail_to_public(config)


@router.post("/mail/test", response_model=MailTestResult)
async def test_mail(
    payload: MailTestRequest,
    request: Request,
    session: SessionDep,
    admin: AdminDep,
) -> MailTestResult:
    """Send a test message with the stored configuration (admin only).

    Unlike a notification, the outcome is reported to the caller: diagnosing the
    configuration is the whole point of this endpoint. The failure text comes from
    the SMTP conversation (host, status code) — never a backtrace.
    """
    config = settings_service.get_mail_settings(session)
    recipients = (
        mail_service.parse_recipients(payload.recipient)
        if payload.recipient
        else mail_service.parse_recipients(config.recipients)
    )

    try:
        await mail_service.send(
            config,
            recipients,
            "[Mailserver UI] Test message",
            "This is a test message from Mailserver UI. "
            "Your mail connector is configured correctly.",
        )
    except mail_service.MailError as exc:
        await audit_service.record(
            session,
            request=request,
            category="settings",
            action="settings.mail.test",
            actor=admin.username,
            target=", ".join(recipients),
            status="failure",
            detail=str(exc),
        )
        return MailTestResult(sent=False, detail=str(exc))

    await audit_service.record(
        session,
        request=request,
        category="settings",
        action="settings.mail.test",
        actor=admin.username,
        target=", ".join(recipients),
        detail="Test message sent",
    )
    return MailTestResult(
        sent=True, detail=f"Test message sent to {', '.join(recipients)}"
    )
