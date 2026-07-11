"""SQLModel models for the outgoing mail (SMTP) connector.

Like the OIDC configuration, the connector is a singleton row (``id == 1``)
seeded from the ``SMTP_*`` environment variables on first access, after which the
database is the source of truth and the UI edits it directly.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

# Fixed primary key of the mail settings singleton row.
MAIL_SETTINGS_ID = 1


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Base (shared fields, data model only) ─────────────────────────────────────


class MailSettingsBase(SQLModel):
    """Mail connector fields shared by the table model and the API schemas."""

    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    # STARTTLS on a plaintext connection (usually port 587). Mutually exclusive
    # with ``use_ssl``, which opens an implicit TLS connection (usually port 465).
    use_tls: bool = True
    use_ssl: bool = False
    from_address: str = ""
    # Comma-separated recipients of the notifications.
    recipients: str = ""

    # What the connector notifies on. Both are off by default: enabling the
    # connector alone only unlocks the test button.
    notify_auth_events: bool = False
    notify_audit_events: bool = False


# ── Table model ───────────────────────────────────────────────────────────────


class MailSettings(MailSettingsBase, table=True):
    """Mail connector configuration — stored as a single row (``id == 1``)."""

    id: int | None = Field(default=None, primary_key=True)
    # Stored in clear, exactly as it previously lived in an env variable. Never
    # returned to the client (see ``MailSettingsPublic``).
    password: str = Field(default="")
    updated_at: datetime = Field(default_factory=_utcnow)


# ── API schemas (not stored) ──────────────────────────────────────────────────


class MailSettingsPublic(MailSettingsBase):
    """Response schema — exposes whether a password is set, never its value."""

    password_set: bool


class MailSettingsUpdate(MailSettingsBase):
    """Request schema for updating the mail connector.

    ``password`` is write-only: send a new value to replace it, or leave it
    ``None``/empty to keep the stored one unchanged.
    """

    password: str | None = None


class MailTestRequest(SQLModel):
    """Request schema for the "send a test message" button.

    ``recipient`` overrides the configured recipients for this one message, so an
    administrator can check the connector against their own mailbox first.
    """

    recipient: str = Field(default="", max_length=255)


class MailTestResult(SQLModel):
    """Outcome of a test send — the error is a message, never a backtrace."""

    sent: bool
    detail: str
