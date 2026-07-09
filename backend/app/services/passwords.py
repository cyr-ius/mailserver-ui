"""Password hashing shared by the mailserver services.

docker-mailserver stores account and Dovecot master passwords as Dovecot-style
``{SHA512-CRYPT}`` hashes, the same scheme ``setup email add`` generates. This
helper is reused by :mod:`app.services.mailbox_service` and
:mod:`app.services.mailserver_service` so hashing stays consistent.
"""

from passlib.hash import sha512_crypt

# Dovecot password-scheme prefix expected by docker-mailserver / Dovecot.
_HASH_SCHEME = "{SHA512-CRYPT}"


def hash_dovecot_password(password: str) -> str:
    """Return a Dovecot ``{SHA512-CRYPT}`` hash for ``password``."""
    return f"{_HASH_SCHEME}{sha512_crypt.hash(password)}"
