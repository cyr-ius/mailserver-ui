"""SQLModel models for user groups.

A group grants a role to every one of its members: membership is how an
administrator promotes an account (an OIDC user provisioned as ``guest``, for
instance) without touching the identity provider.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from ..auth import Role


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ── Association table for many-to-many relationship ────────────────────────


class UserGroupLink(SQLModel, table=True):
    """Association table linking users to groups."""

    __tablename__ = "user_group"
    user_id: int | None = Field(default=None, foreign_key="user.id", primary_key=True)
    group_id: int | None = Field(default=None, foreign_key="group.id", primary_key=True)


# ── Base (shared fields) ──────────────────────────────────────────────────


class GroupBase(SQLModel):
    """Fields shared by the table model and the public API schema."""

    name: str = Field(index=True, unique=True, min_length=1, max_length=255)
    description: str = Field(default="", max_length=1024)
    # Role granted to every member of this group.
    role: str = Field(default="guest", max_length=32)


# ── Table model ───────────────────────────────────────────────────────────


class Group(GroupBase, table=True):
    """Group table model — stored in the database."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ── API schemas (not stored) ──────────────────────────────────────────────


class GroupWrite(SQLModel):
    """Request schema for creating and updating a group.

    Unlike the table model, ``role`` is constrained to the known roles so an
    unknown value is rejected with a 422 rather than silently stored.
    """

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=1024)
    role: Role = "guest"


class GroupPublic(GroupBase):
    """Response schema for group details."""

    id: int
    created_at: datetime
    updated_at: datetime


class GroupWithMembers(GroupPublic):
    """Response schema for group with member information."""

    member_count: int = 0
