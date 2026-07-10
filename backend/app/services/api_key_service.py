"""API key service: issuing, listing and authenticating personal API keys.

Keys are high-entropy random tokens, so a single SHA-256 digest is enough to
store them safely — a slow KDF like bcrypt would only tax every authenticated
request without adding guessing resistance to a 256-bit secret.
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import text as sql_text
from sqlmodel import Session, col, select

from ..config import settings
from ..exceptions import BadRequestException, ConflictException
from ..models.api_key_models import ApiKey
from ..models.user_models import User

logger = logging.getLogger(__name__)

#: Prefix carried by every issued key: makes a leaked token recognisable in logs
#: and lets the auth layer tell an API key from a session JWT.
KEY_PREFIX = "msu_"

#: Entropy of the secret part, in bytes.
_SECRET_BYTES = 32

#: Number of leading characters kept in clear for display purposes.
_DISPLAY_PREFIX_LENGTH = len(KEY_PREFIX) + 8

#: ``last_used_at`` is refreshed at most once per interval: a busy script must
#: not write a row on every single request it makes.
_LAST_USED_REFRESH_SECONDS = 60


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    """Attach UTC to a timestamp read back naive from SQLite."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _digest(raw_key: str) -> str:
    """Return the SHA-256 hex digest of a plaintext key."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def is_expired(key: ApiKey) -> bool:
    """Return True when ``key`` carries an expiry date that has passed."""
    return key.expires_at is not None and _as_aware(key.expires_at) <= _utcnow()


# ── Queries ──────────────────────────────────────────────────────────────────


def list_for_user(session: Session, user_id: int) -> list[ApiKey]:
    """Return every key owned by a user, most recently issued first."""
    return list(
        session.exec(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(col(ApiKey.created_at).desc())
        ).all()
    )


def get_for_user(session: Session, key_id: int, user_id: int) -> ApiKey | None:
    """Return a key by primary key, but only if ``user_id`` owns it."""
    key = session.get(ApiKey, key_id)
    return key if key is not None and key.user_id == user_id else None


# ── Mutations ────────────────────────────────────────────────────────────────


def create(
    session: Session,
    user: User,
    name: str,
    expires_in_days: int | None = None,
) -> tuple[ApiKey, str]:
    """Issue a key for ``user`` and return it along with the plaintext secret.

    The secret is returned only here: the database keeps its digest, so a key
    lost by its owner has to be revoked and reissued.
    """
    if user.id is None:
        raise BadRequestException("The account must be persisted before issuing a key")

    name = name.strip()
    if not name:
        raise BadRequestException("A key name is required")
    if len(list_for_user(session, user.id)) >= settings.api_key_max_per_user:
        raise ConflictException(
            f"You cannot own more than {settings.api_key_max_per_user} API keys"
        )

    raw_key = KEY_PREFIX + secrets.token_urlsafe(_SECRET_BYTES)
    expires_at = _utcnow() + timedelta(days=expires_in_days) if expires_in_days else None

    key = ApiKey(
        user_id=user.id,
        name=name,
        prefix=raw_key[:_DISPLAY_PREFIX_LENGTH],
        key_hash=_digest(raw_key),
        expires_at=expires_at,
    )
    session.add(key)
    session.commit()
    session.refresh(key)
    logger.info("Issued API key %s (id=%s) for user %s", key.prefix, key.id, user.username)
    return key, raw_key


def delete_key(session: Session, key: ApiKey) -> None:
    """Revoke a key: further requests presenting it are rejected immediately."""
    prefix, key_id = key.prefix, key.id
    session.delete(key)
    session.commit()
    logger.info("Revoked API key %s (id=%s)", prefix, key_id)


def delete_for_user(session: Session, user_id: int) -> None:
    """Revoke every key of a user, without committing.

    Called just before deleting the account so the keys and the user itself are
    wiped in a single transaction.
    """
    session.exec(
        sql_text("DELETE FROM api_key WHERE user_id = :user_id").bindparams(user_id=user_id)
    )


# ── Authentication ───────────────────────────────────────────────────────────


def authenticate(session: Session, raw_key: str) -> User | None:
    """Resolve a plaintext key to its owner, or None when it is not usable.

    A key is unusable when unknown, expired, or orphaned by an account that has
    since been deleted.
    """
    if not raw_key.startswith(KEY_PREFIX):
        return None

    key = session.exec(select(ApiKey).where(ApiKey.key_hash == _digest(raw_key))).first()
    if key is None:
        return None
    if is_expired(key):
        logger.info("Rejected expired API key %s (id=%s)", key.prefix, key.id)
        return None

    user = session.get(User, key.user_id)
    if user is None:
        return None

    _touch_last_used(session, key)
    return user


def _touch_last_used(session: Session, key: ApiKey) -> None:
    """Record the key's last use, at most once per refresh interval."""
    now = _utcnow()
    if (
        key.last_used_at is not None
        and (now - _as_aware(key.last_used_at)).total_seconds() < _LAST_USED_REFRESH_SECONDS
    ):
        return
    key.last_used_at = now
    session.add(key)
    session.commit()
