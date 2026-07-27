"""SQLModel models for pending actions the operator still needs to apply.

Right now the only kind tracked is "the mailserver container needs a restart":
several docker-mailserver configuration files (Postfix, Dovecot, Sieve, spam
filtering, Rspamd, LDAP, fail2ban — see :mod:`app.models.mailserver_models`)
are only read when the container starts, so saving one leaves the running
container stale until an operator restarts it. Each save registers (or
refreshes) one row here, keyed by a stable identifier, so repeating the same
edit does not pile up duplicate entries; the navbar bell surfaces the list.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Base (shared fields, data model only) ─────────────────────────────────────


class PendingActionBase(SQLModel):
    """Pending-action fields shared by the table model and the API schema."""

    # Stable identifier of what changed, e.g. "dovecot-config" or "sieve-before".
    # Saving the same area again refreshes the existing row instead of adding one.
    key: str = Field(index=True, unique=True, max_length=128)
    title: str = Field(default="", max_length=255)
    detail: str = Field(default="", max_length=500)


# ── Table model ───────────────────────────────────────────────────────────────


class PendingAction(PendingActionBase, table=True):
    """One area of configuration awaiting a mailserver restart."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ── API schemas (not stored) ──────────────────────────────────────────────────


class PendingActionPublic(PendingActionBase):
    """Response schema for a single pending action."""

    id: int
    created_at: datetime
    updated_at: datetime


class PendingActionsSummary(SQLModel):
    """Every pending action, plus the count the navbar badge displays."""

    items: list[PendingActionPublic]
    count: int
