"""SQLModel models for application users (local and OIDC).

A single ``user`` table backs both authentication providers. Local users own a
bcrypt ``password_hash``; OIDC users have ``password_hash`` set to ``None`` and
are provisioned/updated automatically on each successful sign-in.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from ..auth import Role


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Base (shared fields, data model only) ─────────────────────────────────────


class UserBase(SQLModel):
    """Fields shared by the table model and the public API schema."""

    username: str = Field(index=True, unique=True, min_length=1, max_length=255)
    display_name: str = Field(default="", max_length=255)
    # Role assigned to the account itself. OIDC rewrites it from the group claims
    # on every sign-in; local group memberships can only raise it further (see
    # ``user_service.resolve_role``).
    role: str = Field(default="guest")
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
    # Role actually enforced at request time: the account role raised by the
    # roles of every local group the user belongs to.
    effective_role: Role


class UserCreate(SQLModel):
    """Request schema for creating a local user.

    No role is accepted: a new account starts as ``guest`` and is promoted
    solely through membership in a local group (see ``group_models.Group``).
    """

    username: str = Field(min_length=1, max_length=255)
    display_name: str = Field(default="", max_length=255)
    password: str = Field(min_length=8, max_length=1024)


class PasswordChangeRequest(SQLModel):
    """Request schema for changing a local user's password."""

    new_password: str = Field(min_length=8, max_length=1024)
