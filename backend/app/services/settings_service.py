"""Settings service: persistence for runtime-editable configuration.

The OIDC configuration lives in a single database row. On first access it is
seeded from the ``OIDC_*`` environment variables so existing deployments keep
working without any change; afterwards the database is authoritative and the
UI edits it directly.
"""

import logging
from datetime import UTC, datetime

from sqlmodel import Session

from app.config import settings
from app.exceptions import BadRequestException
from app.services import oidc
from app.settings_models import OIDC_SETTINGS_ID, OidcSettings, OidcSettingsUpdate

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


# ── Internal helpers ─────────────────────────────────────────────────────────


def _validate(payload: OidcSettingsUpdate) -> None:
    """Reject configurations that cannot work once enabled."""
    if payload.enabled and not (payload.issuer and payload.client_id):
        raise BadRequestException("Issuer and Client ID are required when OIDC is enabled")


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
        user_group_claim=settings.oidc_user_group_claim,
        user_group=settings.oidc_user_group,
        restrict_to_groups=settings.oidc_restrict_to_groups,
    )
