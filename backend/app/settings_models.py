"""SQLModel models for runtime-editable application settings.

Settings that used to be read only from environment variables now live in the
database so administrators can change them from the UI. Each settings group is a
singleton row (``id == 1``). The first time a group is read it is seeded from the
matching environment variables (see :mod:`app.services.settings_service`), after
which the database is the source of truth.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

# Fixed primary key of the OIDC settings singleton row.
OIDC_SETTINGS_ID = 1


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Base (shared fields, data model only) ─────────────────────────────────────


class OidcSettingsBase(SQLModel):
    """OIDC fields shared by the table model and the API schemas."""

    enabled: bool = False
    issuer: str = ""
    client_id: str = ""
    redirect_uri: str = ""
    post_logout_redirect_uri: str = ""
    response_type: str = "code"
    scope: str = "openid profile email groups"

    # Disable local username/password login and force SSO.
    oidc_only: bool = False

    admin_group_claim: str = ""
    admin_group: str = ""
    user_group_claim: str = ""
    user_group: str = ""
    restrict_to_groups: bool = False


# ── Table model ───────────────────────────────────────────────────────────────


class OidcSettings(OidcSettingsBase, table=True):
    """OIDC configuration — stored as a single row (``id == 1``)."""

    id: int | None = Field(default=None, primary_key=True)
    # Stored in clear, exactly as it previously lived in an env variable. Never
    # returned to the client (see ``OidcSettingsPublic``).
    client_secret: str = Field(default="")
    updated_at: datetime = Field(default_factory=_utcnow)


# ── API schemas (not stored) ──────────────────────────────────────────────────


class OidcSettingsPublic(OidcSettingsBase):
    """Response schema — exposes whether a secret is set, never its value."""

    client_secret_set: bool


class OidcSettingsUpdate(OidcSettingsBase):
    """Request schema for updating the OIDC configuration.

    ``client_secret`` is write-only: send a new value to replace it, or leave it
    ``None``/empty to keep the stored secret unchanged.
    """

    client_secret: str | None = None
