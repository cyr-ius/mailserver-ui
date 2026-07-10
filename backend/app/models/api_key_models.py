"""SQLModel models for personal API keys.

An API key is a bearer credential a user issues to themselves so scripts and
integrations can call the REST API without a browser session. Only the SHA-256
digest of the secret is stored: the plaintext is returned once, at creation, and
can never be recovered afterwards.

A key carries no privileges of its own — every request it authenticates is
resolved to the owning account and its effective role.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Base (shared fields) ──────────────────────────────────────────────────────


class ApiKeyBase(SQLModel):
    """Fields shared by the table model and the public API schema."""

    name: str = Field(min_length=1, max_length=255)


# ── Table model ───────────────────────────────────────────────────────────────


class ApiKey(ApiKeyBase, table=True):
    """API key table model — stored in the database."""

    __tablename__ = "api_key"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # Leading characters of the plaintext key, kept so the owner can tell two
    # keys apart in the UI. Far too short to be usable as a credential.
    prefix: str = Field(max_length=32)
    # SHA-256 of the plaintext key. Unique and indexed so a presented key is
    # resolved with a single lookup instead of a row-by-row comparison.
    key_hash: str = Field(index=True, unique=True, max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime | None = Field(default=None)
    last_used_at: datetime | None = Field(default=None)


# ── API schemas (not stored) ──────────────────────────────────────────────────


class ApiKeyCreate(ApiKeyBase):
    """Request schema for issuing a key.

    ``expires_in_days`` left to None issues a key that never expires.
    """

    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyPublic(ApiKeyBase):
    """Response schema — never exposes the secret nor its digest."""

    id: int
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class ApiKeyCreated(ApiKeyPublic):
    """Creation response: the only time the plaintext key is ever returned."""

    key: str
