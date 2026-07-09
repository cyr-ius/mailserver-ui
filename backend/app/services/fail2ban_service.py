"""Fail2ban service: drive docker-mailserver's fail2ban via ``docker exec``.

Like every other mailserver action, fail2ban runs inside the mailserver
container over the Docker socket — here as runtime commands rather than config
files. It goes through the shared :func:`app.services.container.run_in_container`
runner, so it needs ``MAILSERVER_EXEC_ENABLED`` (the master switch that allows
exec at all) plus its own feature toggle ``FAIL2BAN_ENABLED``.

* structured reads use ``fail2ban-client`` (stable, machine-friendly output);
* ban/unban/log actions use docker-mailserver's ``setup fail2ban`` wrapper.

Commands are executed with an argument list (never ``shell=True``) and every IP
is validated with :mod:`ipaddress` before use, so no user input reaches a shell.
"""

import configparser
import ipaddress
import logging

from ..config import settings
from ..exceptions import BadRequestException
from ..models.fail2ban_models import (
    BannedIp,
    Fail2banActionResult,
    Fail2banJail,
    Fail2banLog,
    Fail2banPolicy,
    Fail2banPolicyUpdate,
    Fail2banStatus,
)
from . import container
from .container import run_in_container

logger = logging.getLogger(__name__)

# Ban policy file in the shared config volume, copied to
# ``/etc/fail2ban/jail.d/user-jail.local`` when the mailserver starts.
_JAIL_FILENAME = "fail2ban-jail.cf"

# docker-mailserver's shipped defaults: six failures per week, banned a week.
_DEFAULT_BANTIME = 604800
_DEFAULT_FINDTIME = 604800
_DEFAULT_MAXRETRY = 6

# Header written at the top of the jail file this service owns.
_MANAGED_HEADER = "# Managed by Mailserver UI — manual edits may be overwritten."


# ── Command execution ─────────────────────────────────────────────────────────


def _ensure_enabled() -> None:
    """Raise unless the fail2ban feature toggle is on.

    The Docker socket / exec prerequisite (``MAILSERVER_EXEC_ENABLED``) is
    enforced separately by :func:`app.services.container.run_in_container`.
    """
    if not settings.fail2ban_enabled:
        raise BadRequestException(
            "Fail2ban management is disabled. Set FAIL2BAN_ENABLED=true (and "
            "MAILSERVER_EXEC_ENABLED=true, with the Docker socket mounted) to enable it."
        )


def _run(args: list[str]) -> str:
    """Run a fail2ban command inside the mailserver container and return stdout.

    Ensures the fail2ban feature is enabled, then delegates to the shared
    ``docker exec`` runner. See :func:`app.services.container.run_in_container`.
    """
    _ensure_enabled()
    return run_in_container(args, timeout=settings.fail2ban_command_timeout)


def _validate_ip(raw: str) -> str:
    """Return the normalised IP string, raising ``BadRequestException`` if invalid."""
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError as exc:
        raise BadRequestException(f"Invalid IP address: {raw!r}") from exc


# ── Parsing helpers ───────────────────────────────────────────────────────────


def _field_after(text: str, label: str) -> str:
    """Return the trimmed value following ``label:`` in a fail2ban-client dump."""
    for line in text.splitlines():
        if label in line:
            return line.split(":", 1)[1].strip()
    return ""


def _as_int(value: str) -> int:
    """Parse a leading integer from ``value`` (fail2ban pads with tabs/spaces)."""
    value = value.strip()
    return int(value) if value.isdigit() else 0


def _split_tokens(value: str) -> list[str]:
    """Split a whitespace/comma separated fail2ban list into clean tokens."""
    return [token for token in value.replace(",", " ").split() if token]


def _parse_jail_names(status_text: str) -> list[str]:
    """Extract the jail names from ``fail2ban-client status`` output."""
    return _split_tokens(_field_after(status_text, "Jail list"))


def _parse_jail(name: str, status_text: str) -> Fail2banJail:
    """Build a :class:`Fail2banJail` from ``fail2ban-client status <jail>`` output."""
    return Fail2banJail(
        name=name,
        currently_failed=_as_int(_field_after(status_text, "Currently failed")),
        total_failed=_as_int(_field_after(status_text, "Total failed")),
        currently_banned=_as_int(_field_after(status_text, "Currently banned")),
        total_banned=_as_int(_field_after(status_text, "Total banned")),
        banned_ips=_split_tokens(_field_after(status_text, "Banned IP list")),
        file_list=_split_tokens(_field_after(status_text, "File list")),
    )


# ── Public API ────────────────────────────────────────────────────────────────


def get_status() -> Fail2banStatus:
    """Return the status of every fail2ban jail, including banned IPs."""
    jail_names = _parse_jail_names(_run(["fail2ban-client", "status"]))
    jails = [_parse_jail(name, _run(["fail2ban-client", "status", name])) for name in jail_names]
    return Fail2banStatus(jails=jails)


def list_banned_ips() -> list[BannedIp]:
    """Return every currently banned IP with the jail it is banned in."""
    banned: list[BannedIp] = []
    for jail in get_status().jails:
        banned.extend(BannedIp(ip=ip, jail=jail.name) for ip in jail.banned_ips)
    return banned


def ban_ip(ip: str) -> Fail2banActionResult:
    """Ban an IP address across the mailserver's active jails."""
    address = _validate_ip(ip)
    output = _run(["setup", "fail2ban", "ban", address])
    logger.info("Banned IP %s via fail2ban", address)
    return Fail2banActionResult(output=output.strip())


def unban_ip(ip: str) -> Fail2banActionResult:
    """Remove any ban for an IP address across all jails."""
    address = _validate_ip(ip)
    output = _run(["setup", "fail2ban", "unban", address])
    logger.info("Unbanned IP %s via fail2ban", address)
    return Fail2banActionResult(output=output.strip())


def get_log() -> Fail2banLog:
    """Return the trailing lines of the fail2ban log file."""
    output = _run(["setup", "fail2ban", "log"])
    lines = output.splitlines()
    return Fail2banLog(lines=lines[-settings.fail2ban_log_lines :])


# ── Ban policy (fail2ban-jail.cf) ─────────────────────────────────────────────


def get_policy() -> Fail2banPolicy:
    """Return the ``[DEFAULT]`` ban policy, or docker-mailserver's own defaults.

    Unlike the actions above, the policy is a config file rather than a runtime
    command: it is read from the shared config volume, and the mailserver only
    picks it up when it starts.
    """
    _ensure_enabled()
    content = container.read_config(_JAIL_FILENAME)
    if not content.strip():
        return Fail2banPolicy(
            bantime=_DEFAULT_BANTIME,
            findtime=_DEFAULT_FINDTIME,
            maxretry=_DEFAULT_MAXRETRY,
            configured=False,
        )

    parser = configparser.ConfigParser()
    try:
        parser.read_string(content)
    except configparser.Error:
        logger.warning("Unparsable %s; reporting docker-mailserver's defaults", _JAIL_FILENAME)
        return Fail2banPolicy(
            bantime=_DEFAULT_BANTIME,
            findtime=_DEFAULT_FINDTIME,
            maxretry=_DEFAULT_MAXRETRY,
            configured=False,
        )

    section = parser["DEFAULT"]
    return Fail2banPolicy(
        bantime=section.getint("bantime", _DEFAULT_BANTIME),
        findtime=section.getint("findtime", _DEFAULT_FINDTIME),
        maxretry=section.getint("maxretry", _DEFAULT_MAXRETRY),
        configured=True,
    )


def set_policy(payload: Fail2banPolicyUpdate) -> Fail2banPolicy:
    """Rewrite ``fail2ban-jail.cf`` with a new ``[DEFAULT]`` ban policy.

    The file is owned by this app and rewritten wholesale, so any jail-specific
    section added by hand is dropped. The new policy applies once the mailserver
    container restarts.
    """
    _ensure_enabled()
    container.write_config(
        _JAIL_FILENAME,
        f"{_MANAGED_HEADER}\n"
        "[DEFAULT]\n"
        f"bantime = {payload.bantime}\n"
        f"findtime = {payload.findtime}\n"
        f"maxretry = {payload.maxretry}\n",
    )
    logger.info(
        "Updated the fail2ban policy (bantime=%s, findtime=%s, maxretry=%s)",
        payload.bantime,
        payload.findtime,
        payload.maxretry,
    )
    return Fail2banPolicy(
        bantime=payload.bantime,
        findtime=payload.findtime,
        maxretry=payload.maxretry,
        configured=True,
    )
