"""SQLModel models for personal access tokens (PAT).

A PAT is a bearer credential a user issues to themselves so scripts and
integrations can call the REST API without a browser session. Only the SHA-256
digest of the secret is stored: the plaintext is returned once, at creation, and
can never be recovered afterwards.

A token is a single secret — ``pat_`` followed by 43 random characters — sent as
``Authorization: Bearer``. A masked hint of it is kept for display, so its owner
can tell two tokens apart in the UI without the API ever echoing a usable secret.

A PAT carries no privileges of its own — every request it authenticates is
resolved to the owning account and its effective role.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Base (shared fields) ──────────────────────────────────────────────────────


class PatBase(SQLModel):
    """Fields shared by the table model and the public API schema."""

    name: str = Field(min_length=1, max_length=255)


# ── Table model ───────────────────────────────────────────────────────────────


class Pat(PatBase, table=True):
    """Personal access token table model — stored in the database."""

    __tablename__ = "pat"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # Masked form of the token (``AbCd…Wx12``), kept so the owner can tell two
    # tokens apart in the UI. Far too partial to be usable as a credential.
    token_hint: str = Field(max_length=32)
    # SHA-256 of the token: unique and indexed, so a presented token is resolved
    # with a single lookup.
    token_hash: str = Field(index=True, unique=True, max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime | None = Field(default=None)
    last_used_at: datetime | None = Field(default=None)


# ── API schemas (not stored) ──────────────────────────────────────────────────


class PatCreate(PatBase):
    """Request schema for issuing a token.

    ``expires_in_days`` left to None issues a token that never expires.
    """

    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class PatPublic(PatBase):
    """Response schema — never exposes the secret nor its digest."""

    id: int
    token_hint: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class PatCreated(PatPublic):
    """Creation response: the only time the plaintext secret is returned."""

    token: str
