"""PAT service: issuing, listing and authenticating personal access tokens.

Tokens are high-entropy random secrets, so a single SHA-256 digest is enough to
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
from ..models.pat_models import Pat
from ..models.user_models import User

logger = logging.getLogger(__name__)

#: Prefix carried by every issued token: makes a leaked secret recognisable in
#: logs and lets the auth layer tell a PAT from a session JWT.
TOKEN_PREFIX = "pat_"

#: Entropy of the token, in bytes.
_TOKEN_BYTES = 32

#: ``last_used_at`` is refreshed at most once per interval: a busy script must
#: not write a row on every single request it makes.
_LAST_USED_REFRESH_SECONDS = 60


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    """Attach UTC to a timestamp read back naive from SQLite."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _digest(raw: str) -> str:
    """Return the SHA-256 hex digest of a plaintext secret."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _token_hint(raw_token: str) -> str:
    """Return the masked token shown in the UI (``AbCd…Wx12``).

    Both ends of the secret are taken: the prefix alone would be enough to tell
    two tokens apart, but the tail is what the owner reads back from a script's
    configuration. Eight characters out of 43 leave the secret unguessable.
    """
    bare = raw_token.removeprefix(TOKEN_PREFIX)
    return f"{bare[:4]}…{bare[-4:]}"


def is_expired(pat: Pat) -> bool:
    """Return True when ``pat`` carries an expiry date that has passed."""
    return pat.expires_at is not None and _as_aware(pat.expires_at) <= _utcnow()


# ── Queries ──────────────────────────────────────────────────────────────────


def list_for_user(session: Session, user_id: int) -> list[Pat]:
    """Return every token owned by a user, most recently issued first."""
    return list(
        session.exec(
            select(Pat)
            .where(Pat.user_id == user_id)
            .order_by(col(Pat.created_at).desc())
        ).all()
    )


def get_for_user(session: Session, pat_id: int, user_id: int) -> Pat | None:
    """Return a token by primary key, but only if ``user_id`` owns it."""
    pat = session.get(Pat, pat_id)
    return pat if pat is not None and pat.user_id == user_id else None


# ── Mutations ────────────────────────────────────────────────────────────────


def create(
    session: Session,
    user: User,
    name: str,
    expires_in_days: int | None = None,
) -> tuple[Pat, str]:
    """Issue a token for ``user``, returning it with its plaintext secret.

    The secret is returned only here: the database keeps its digest, so a token
    lost by its owner has to be revoked and reissued.
    """
    if user.id is None:
        raise BadRequestException(
            "The account must be persisted before issuing a token"
        )

    name = name.strip()
    if not name:
        raise BadRequestException("A token name is required")
    if len(list_for_user(session, user.id)) >= settings.pat_max_per_user:
        raise ConflictException(
            f"You cannot own more than {settings.pat_max_per_user} tokens"
        )

    raw_token = TOKEN_PREFIX + secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = (
        _utcnow() + timedelta(days=expires_in_days) if expires_in_days else None
    )

    pat = Pat(
        user_id=user.id,
        name=name,
        token_hint=_token_hint(raw_token),
        token_hash=_digest(raw_token),
        expires_at=expires_at,
    )
    session.add(pat)
    session.commit()
    session.refresh(pat)
    logger.info(
        "Issued PAT %s (id=%s) for user %s", pat.token_hint, pat.id, user.username
    )
    return pat, raw_token


def delete_pat(session: Session, pat: Pat) -> None:
    """Revoke a token: further requests presenting it are rejected immediately."""
    hint, pat_id = pat.token_hint, pat.id
    session.delete(pat)
    session.commit()
    logger.info("Revoked PAT %s (id=%s)", hint, pat_id)


def delete_for_user(session: Session, user_id: int) -> None:
    """Revoke every token of a user, without committing.

    Called just before deleting the account so the tokens and the user itself
    are wiped in a single transaction.
    """
    session.exec(
        sql_text("DELETE FROM pat WHERE user_id = :user_id").bindparams(user_id=user_id)
    )


# ── Authentication ───────────────────────────────────────────────────────────


def authenticate(session: Session, raw_token: str) -> User | None:
    """Resolve a presented token to its owner, or None when it is not usable.

    A token is unusable when unknown, expired, or orphaned by an account that
    has since been deleted.
    """
    candidate = raw_token.strip()
    if not candidate.removeprefix(TOKEN_PREFIX):
        return None

    pat = session.exec(select(Pat).where(Pat.token_hash == _digest(candidate))).first()
    if pat is None:
        return None
    if is_expired(pat):
        logger.info("Rejected expired PAT %s (id=%s)", pat.token_hint, pat.id)
        return None

    user = session.get(User, pat.user_id)
    if user is None:
        return None

    _touch_last_used(session, pat)
    return user


def _touch_last_used(session: Session, pat: Pat) -> None:
    """Record the token's last use, at most once per refresh interval."""
    now = _utcnow()
    if (
        pat.last_used_at is not None
        and (now - _as_aware(pat.last_used_at)).total_seconds()
        < _LAST_USED_REFRESH_SECONDS
    ):
        return
    pat.last_used_at = now
    session.add(pat)
    session.commit()
