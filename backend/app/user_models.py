"""SQLModel models for application users (local and OIDC).

A single ``user`` table backs both authentication providers. Local users own a
bcrypt ``password_hash``; OIDC users have ``password_hash`` set to ``None`` and
are provisioned/updated automatically on each successful sign-in.
"""

from datetime import UTC, datetime
from typing import Literal

from sqlmodel import Field, SQLModel

Role = Literal["admin", "user"]
AuthProvider = Literal["local", "oidc"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Base (shared fields, data model only) ─────────────────────────────────────


class UserBase(SQLModel):
    """Fields shared by the table model and the public API schema."""

    username: str = Field(index=True, unique=True, min_length=1, max_length=255)
    display_name: str = Field(default="", max_length=255)
    role: str = Field(default="user")
    provider: str = Field(default="local")


# ── Table model ───────────────────────────────────────────────────────────────


class User(UserBase, table=True):
    """User table model — stored in the database."""

    id: int | None = Field(default=None, primary_key=True)
    # Present only for local users; OIDC accounts authenticate externally.
    password_hash: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    last_login_at: datetime | None = Field(default=None)


# ── API schemas (not stored) ──────────────────────────────────────────────────


class UserPublic(UserBase):
    """Response schema — never exposes the password hash."""

    id: int
    created_at: datetime
    last_login_at: datetime | None


class PasswordChangeRequest(SQLModel):
    """Request schema for changing a local user's password."""

    new_password: str = Field(min_length=8, max_length=1024)
