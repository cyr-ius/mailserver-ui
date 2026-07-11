"""SQLModel models for the audit trail.

Every security-relevant action (sign-in, sign-out, account and settings changes,
API-key lifecycle) appends one immutable row here. The table is append-only: the
API exposes reads and a retention-based purge, never an update.
"""

from datetime import UTC, datetime
from typing import Literal

from sqlmodel import Field, SQLModel

#: Outcome of an audited action.
AuditStatus = Literal["success", "failure"]

#: Broad family an action belongs to. ``auth`` covers sign-in/sign-out — the mail
#: connector can be told to notify on those alone, without the rest of the trail.
AuditCategory = Literal["auth", "user", "settings", "api_key", "mailserver"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Base (shared fields, data model only) ─────────────────────────────────────


class AuditLogBase(SQLModel):
    """Audit fields shared by the table model and the API schema."""

    # Username of the principal that performed the action. Recorded even when the
    # action failed (a rejected login names the account that was attempted), and
    # set to ``anonymous`` when no principal could be established.
    actor: str = Field(default="anonymous", index=True, max_length=255)
    category: str = Field(default="user", index=True, max_length=32)
    # Dotted, stable identifier, e.g. ``auth.login`` or ``user.deactivate``.
    action: str = Field(default="", index=True, max_length=64)
    # What the action was performed on (a username, a settings group, …).
    target: str = Field(default="", max_length=255)
    status: str = Field(default="success", max_length=16)
    # Free-form context. Never carries a secret: services log what changed, not
    # the values.
    detail: str = Field(default="", max_length=2000)
    ip: str = Field(default="", max_length=64)


# ── Table model ───────────────────────────────────────────────────────────────


class AuditLog(AuditLogBase, table=True):
    """One audited action — append-only."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)


# ── API schemas (not stored) ──────────────────────────────────────────────────


class AuditLogPublic(AuditLogBase):
    """Response schema for a single audit entry."""

    id: int
    created_at: datetime


class AuditPage(SQLModel):
    """A page of audit entries, with the total matching the active filters.

    ``total`` is what the UI needs to paginate; it counts every row matching the
    filters, not just the ones in ``items``.
    """

    items: list[AuditLogPublic]
    total: int
