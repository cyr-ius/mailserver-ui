"""API schemas for fail2ban management inside docker-mailserver.

Fail2ban runs inside the mailserver container and exposes no shared config
file, so — unlike mailboxes or relays — it is driven with ``docker exec``
(``fail2ban-client`` for structured reads, ``setup fail2ban`` for actions).
See :mod:`app.services.fail2ban_service`. These schemas describe the
request/response shapes only.
"""

from pydantic import BaseModel, Field


class Fail2banJail(BaseModel):
    """A single fail2ban jail with its counters and currently banned IPs."""

    name: str
    currently_failed: int = 0
    total_failed: int = 0
    currently_banned: int = 0
    total_banned: int = 0
    # IPs currently banned in this jail.
    banned_ips: list[str] = Field(default_factory=list)
    # Log files watched by the jail's filter.
    file_list: list[str] = Field(default_factory=list)


class Fail2banStatus(BaseModel):
    """Aggregated fail2ban status: every configured jail."""

    jails: list[Fail2banJail] = Field(default_factory=list)


class BannedIp(BaseModel):
    """A single banned IP and the jail it is banned in."""

    ip: str
    jail: str


class BanRequest(BaseModel):
    """Request schema to ban an IP address."""

    ip: str = Field(min_length=1, max_length=45)


class Fail2banActionResult(BaseModel):
    """Result of a ban/unban action: the raw command output, for feedback."""

    output: str = ""


class Fail2banLog(BaseModel):
    """Trailing lines of the fail2ban log file."""

    lines: list[str] = Field(default_factory=list)


class Fail2banPolicy(BaseModel):
    """The ban policy stored in ``fail2ban-jail.cf`` under ``[DEFAULT]``.

    docker-mailserver copies that file to ``/etc/fail2ban/jail.d/user-jail.local``
    when it starts, so a changed policy only takes effect after a restart.
    """

    # Seconds a banned IP stays banned.
    bantime: int = Field(ge=1)
    # Seconds over which failures are counted towards ``maxretry``.
    findtime: int = Field(ge=1)
    # Failures within ``findtime`` before an IP is banned.
    maxretry: int = Field(ge=1)
    # False when no ``fail2ban-jail.cf`` exists yet: the values above are then
    # the defaults docker-mailserver ships with, not a stored policy.
    configured: bool = False
    restart_required: bool = True


class Fail2banPolicyUpdate(BaseModel):
    """Request schema replacing the fail2ban ``[DEFAULT]`` ban policy."""

    # One week is the docker-mailserver default; cap at a year to stay sane.
    bantime: int = Field(ge=60, le=31_536_000)
    findtime: int = Field(ge=60, le=31_536_000)
    maxretry: int = Field(ge=1, le=100)


class Fail2banConfig(BaseModel):
    """The raw contents of ``fail2ban-fail2ban.cf``.

    Tunes the fail2ban daemon itself — log level, database retention — rather
    than any jail. docker-mailserver copies it to ``/etc/fail2ban/fail2ban.local``
    when it starts, so a change only applies after a restart.
    """

    content: str = ""
    restart_required: bool = True


class Fail2banConfigUpdate(BaseModel):
    """Request schema replacing the fail2ban daemon configuration."""

    content: str = Field(default="", max_length=65536)
