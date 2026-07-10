"""Shared helpers to drive the docker-mailserver container over the Docker socket.

Every mailserver management action goes through ``docker exec`` into the
mailserver container — no host directory is bind-mounted. The docker-mailserver
flat config files (``postfix-accounts.cf`` and friends) are read and written
*inside* the container, and runtime-only actions (fail2ban, DKIM generation,
reading the mail log) run there too. This requires the Docker socket to be
mounted into this container: without it every command fails with a bad gateway.

Commands always use a fixed argument list (never ``shell=True`` on our side).
When a POSIX shell is needed inside the container, user-influenced data is
passed as positional arguments or streamed on stdin — never interpolated into
the script string — so nothing reaches a shell for evaluation.
"""

import logging
import subprocess

from ..config import DOCKER_BINARY, MAILSERVER_CONFIG_DIR, settings
from ..exceptions import BadGatewayException

logger = logging.getLogger(__name__)


def _docker_exec(
    args: list[str],
    *,
    timeout: int,
    stdin: str | None = None,
    check: bool = True,
) -> str:
    """Run ``docker exec [-i] <container> <args…>`` and return stdout.

    ``stdin`` is streamed to the process (implying ``-i``) when provided. Raises
    :class:`BadGatewayException` when the Docker CLI is missing, the command
    times out, or the container reports a non-zero exit status.

    ``check=False`` suits commands that report state through their exit code
    (``supervisorctl status`` exits 3 when a service is down) yet still print
    their answer. A failure that printed *nothing* — an unreachable container,
    say — is still raised, so a silent empty result cannot pass for data.
    """
    cmd = [DOCKER_BINARY, "exec"]
    if stdin is not None:
        cmd.append("-i")
    cmd += [settings.mailserver_container, *args]
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell, validated input
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise BadGatewayException(
            "Docker CLI not found in this container. Managing the mailserver "
            "container requires the docker binary and a mounted Docker socket."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BadGatewayException("The mailserver command timed out.") from exc

    if result.returncode != 0 and (check or not result.stdout.strip()):
        detail = (result.stderr or result.stdout or "").strip() or "unknown error"
        logger.warning("container command %s failed (%s): %s", args, result.returncode, detail)
        raise BadGatewayException(f"Mailserver command failed: {detail[:300]}")
    return result.stdout


def run_in_container(args: list[str], *, timeout: int, check: bool = True) -> str:
    """Run ``docker exec <container> <args…>`` and return stdout (see module docs).

    Validating any user-provided token before it reaches this function is the
    caller's responsibility. Pass ``check=False`` to accept a non-zero exit
    status *that produced output*.
    """
    return _docker_exec(args, timeout=timeout, check=check)


# ── Config files inside the container ─────────────────────────────────────────

# The config directory path inside the container, without its trailing slash.
_CONFIG_DIR = MAILSERVER_CONFIG_DIR.rstrip("/")


def read_file(path: str) -> str:
    """Return the contents of ``path`` inside the container (``""`` when absent).

    ``path`` is absolute and container-side; a missing file reads as an empty
    string rather than an error.
    """
    # ``cat`` on a missing file exits non-zero; swallow it so absent == empty.
    return _docker_exec(
        ["sh", "-c", 'cat -- "$1" 2>/dev/null || true', "sh", path],
        timeout=settings.mailserver_command_timeout,
    )


def read_config(rel_path: str) -> str:
    """Return the contents of ``<config_dir>/<rel_path>`` (``""`` when absent).

    A missing file reads as an empty string rather than an error, mirroring the
    "no file yet" case of the previous filesystem-backed implementation.
    """
    return read_file(f"{_CONFIG_DIR}/{rel_path}")


def write_config(rel_path: str, content: str) -> None:
    """Atomically (over)write ``<config_dir>/<rel_path>`` inside the container.

    ``content`` is streamed on stdin to a temp file that is ``mv``-ed into place,
    so docker-mailserver's file watcher never observes a half-written file.
    """
    path = f"{_CONFIG_DIR}/{rel_path}"
    script = (
        'dir=$(dirname -- "$1"); mkdir -p -- "$dir"; '
        'tmp="$1.tmp"; cat > "$tmp" && mv -- "$tmp" "$1"'
    )
    _docker_exec(
        ["sh", "-c", script, "sh", path],
        timeout=settings.mailserver_command_timeout,
        stdin=content,
    )


def delete_config(rel_path: str) -> None:
    """Delete ``<config_dir>/<rel_path>`` inside the container; absent is not an error."""
    _docker_exec(
        ["sh", "-c", 'rm -f -- "$1"', "sh", f"{_CONFIG_DIR}/{rel_path}"],
        timeout=settings.mailserver_command_timeout,
    )


def list_config_files(rel_dir: str, suffix: str) -> list[str]:
    """Return the ``suffix`` files under ``<config_dir>/<rel_dir>``.

    Paths are returned relative to ``rel_dir`` and sorted; an empty list is
    returned when the directory does not exist.
    """
    base = f"{_CONFIG_DIR}/{rel_dir}"
    out = _docker_exec(
        [
            "sh",
            "-c",
            'test -d "$1" && find "$1" -type f -name "$2" 2>/dev/null || true',
            "sh",
            base,
            f"*{suffix}",
        ],
        timeout=settings.mailserver_command_timeout,
    )
    prefix = f"{base}/"
    return sorted(line[len(prefix) :] for line in out.splitlines() if line.startswith(prefix))
