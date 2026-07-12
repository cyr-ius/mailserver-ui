"""Settings service: persistence for runtime-editable configuration.

The OIDC configuration and the mail connector each live in a single database row.
On first access a row is seeded from the matching environment variables so
existing deployments keep working without any change; afterwards the database is
authoritative and the UI edits it directly.
"""

import logging
from datetime import UTC, datetime

from sqlmodel import Session

from ..config import settings
from ..exceptions import BadRequestException
from ..models.mail_models import MAIL_SETTINGS_ID, MailSettings, MailSettingsUpdate
from ..models.settings_models import OIDC_SETTINGS_ID, OidcSettings, OidcSettingsUpdate
from ..services import oidc

logger = logging.getLogger(__name__)


def get_oidc_settings(session: Session) -> OidcSettings:
    """Return the OIDC settings singleton, seeding it from env on first access."""
    config = session.get(OidcSettings, OIDC_SETTINGS_ID)
    if config is None:
        config = _seed_from_env()
        session.add(config)
        session.commit()
        session.refresh(config)
        logger.info("OIDC settings initialised from environment variables")
    return config


def update_oidc_settings(session: Session, payload: OidcSettingsUpdate) -> OidcSettings:
    """Apply an update to the OIDC settings and persist it.

    The client secret is preserved when the payload omits it (write-only field).
    Changing the issuer invalidates the cached discovery document.
    """
    config = get_oidc_settings(session)
    _validate(payload)

    previous_issuer = config.issuer
    data = payload.model_dump(exclude={"client_secret"})
    for key, value in data.items():
        setattr(config, key, value)

    if payload.client_secret:
        config.client_secret = payload.client_secret

    config.updated_at = datetime.now(UTC)
    session.add(config)
    session.commit()
    session.refresh(config)

    if config.issuer != previous_issuer:
        oidc.reset_discovery_cache()
    logger.info("OIDC settings updated (enabled=%s)", config.enabled)
    return config


# ── Mail connector ───────────────────────────────────────────────────────────


def get_mail_settings(session: Session) -> MailSettings:
    """Return the mail settings singleton, seeding it from env on first access."""
    config = session.get(MailSettings, MAIL_SETTINGS_ID)
    if config is None:
        config = _seed_mail_from_env()
        session.add(config)
        session.commit()
        session.refresh(config)
        logger.info("Mail settings initialised from environment variables")
    return config


def update_mail_settings(session: Session, payload: MailSettingsUpdate) -> MailSettings:
    """Apply an update to the mail connector and persist it.

    The password is preserved when the payload omits it (write-only field).
    """
    config = get_mail_settings(session)
    _validate_mail(payload)

    data = payload.model_dump(exclude={"password"})
    for key, value in data.items():
        setattr(config, key, value)

    if payload.password:
        config.password = payload.password

    config.updated_at = datetime.now(UTC)
    session.add(config)
    session.commit()
    session.refresh(config)
    logger.info(
        "Mail settings updated (enabled=%s host=%s)", config.enabled, config.host
    )
    return config


# ── Internal helpers ─────────────────────────────────────────────────────────


def _validate_mail(payload: MailSettingsUpdate) -> None:
    """Reject mail configurations that cannot work once enabled."""
    if not payload.enabled:
        return
    if not payload.host:
        raise BadRequestException(
            "An SMTP host is required when the mail connector is enabled"
        )
    if not payload.from_address:
        raise BadRequestException(
            "A sender address is required when the mail connector is enabled"
        )
    if not 1 <= payload.port <= 65535:
        raise BadRequestException("The SMTP port must be between 1 and 65535")
    if payload.use_ssl and payload.use_tls:
        raise BadRequestException(
            "Choose either implicit TLS (SSL) or STARTTLS, not both"
        )


def _seed_mail_from_env() -> MailSettings:
    """Build the initial mail settings row from environment-backed settings."""
    return MailSettings(
        id=MAIL_SETTINGS_ID,
        enabled=settings.smtp_enabled,
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        use_tls=settings.smtp_use_tls,
        use_ssl=settings.smtp_use_ssl,
        from_address=settings.smtp_from,
        recipients=settings.smtp_recipients,
        notify_auth_events=settings.smtp_notify_auth_events,
        notify_audit_events=settings.smtp_notify_audit_events,
    )


def _validate(payload: OidcSettingsUpdate) -> None:
    """Reject configurations that cannot work once enabled."""
    if payload.enabled and not (payload.issuer and payload.client_id):
        raise BadRequestException(
            "Issuer and Client ID are required when OIDC is enabled"
        )


def _seed_from_env() -> OidcSettings:
    """Build the initial OIDC settings row from environment-backed settings."""
    return OidcSettings(
        id=OIDC_SETTINGS_ID,
        enabled=settings.oidc_enabled,
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        redirect_uri=settings.oidc_redirect_uri,
        post_logout_redirect_uri=settings.oidc_post_logout_redirect_uri,
        response_type=settings.oidc_response_type,
        scope=settings.oidc_scope,
        oidc_only=settings.oidc_only,
        admin_group_claim=settings.oidc_admin_group_claim,
        admin_group=settings.oidc_admin_group,
        manager_group_claim=settings.oidc_manager_group_claim,
        manager_group=settings.oidc_manager_group,
        restrict_to_groups=settings.oidc_restrict_to_groups,
    )
