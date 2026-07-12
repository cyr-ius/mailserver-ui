"""Mail service: outgoing SMTP notifications.

The connector sends two kinds of message: a test message triggered from the
settings page, and notifications for audit events (all of them, or sign-in and
sign-out alone — see :class:`~app.models.mail_models.MailSettings`).

Sending is done with the standard library's ``smtplib`` — a blocking client —
run in a worker thread so the event loop is never held up. Notifications are
fire-and-forget: a mail server that is down or misconfigured must never turn a
successful action into a failed HTTP request, so failures are logged and
swallowed. The test button is the opposite: it reports the error to the caller,
because diagnosing the configuration is its whole purpose.
"""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from ..models.audit_models import AuditLog
from ..models.mail_models import MailSettings

logger = logging.getLogger(__name__)

# Timeout (seconds) for the whole SMTP conversation.
_SMTP_TIMEOUT = 15.0


class MailError(Exception):
    """Raised when a message could not be handed over to the SMTP server."""


def parse_recipients(raw: str) -> list[str]:
    """Split the stored comma-separated recipient list into addresses."""
    return [address.strip() for address in raw.split(",") if address.strip()]


def is_sendable(config: MailSettings) -> tuple[bool, str]:
    """Report whether ``config`` is complete enough to send anything."""
    if not config.enabled:
        return False, "The mail connector is disabled"
    if not config.host:
        return False, "An SMTP host is required"
    if not config.from_address:
        return False, "A sender address is required"
    return True, ""


# ── Sending ──────────────────────────────────────────────────────────────────


async def send(
    config: MailSettings,
    recipients: list[str],
    subject: str,
    body: str,
) -> None:
    """Send one plaintext message. Raises :class:`MailError` on any failure."""
    sendable, reason = is_sendable(config)
    if not sendable:
        raise MailError(reason)
    if not recipients:
        raise MailError("At least one recipient is required")

    message = EmailMessage()
    message["From"] = config.from_address
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    try:
        await asyncio.to_thread(_send_blocking, config, message)
    except MailError:
        raise
    except (OSError, smtplib.SMTPException) as exc:
        # The exception text is safe to surface (host, code, server greeting);
        # the traceback is not, and stays in the logs.
        logger.error("SMTP delivery to %s failed: %s", config.host, exc)
        raise MailError(f"SMTP delivery failed: {exc}") from exc


def _send_blocking(config: MailSettings, message: EmailMessage) -> None:
    """Blocking SMTP conversation, executed in a worker thread."""
    context = ssl.create_default_context()
    client: smtplib.SMTP
    if config.use_ssl:
        client = smtplib.SMTP_SSL(
            config.host, config.port, timeout=_SMTP_TIMEOUT, context=context
        )
    else:
        client = smtplib.SMTP(config.host, config.port, timeout=_SMTP_TIMEOUT)
    with client:
        if config.use_tls and not config.use_ssl:
            client.starttls(context=context)
        if config.username:
            client.login(config.username, config.password)
        client.send_message(message)


# ── Notifications ────────────────────────────────────────────────────────────


def wants(config: MailSettings, entry: AuditLog) -> bool:
    """Return True when ``entry`` matches what the connector is asked to notify."""
    if not config.enabled:
        return False
    if entry.category == "auth":
        return config.notify_auth_events or config.notify_audit_events
    return config.notify_audit_events


def notify(config: MailSettings, entry: AuditLog) -> None:
    """Dispatch a notification for ``entry`` in the background, if configured.

    Returns immediately: the message is sent by a task the caller does not await,
    so a slow or unreachable SMTP server cannot delay the request that triggered
    the event. ``config`` is a detached snapshot — the task must not touch the
    request's database session, which is closed by the time it runs.
    """
    if not wants(config, entry):
        return
    recipients = parse_recipients(config.recipients)
    if not recipients:
        logger.warning("Mail notifications are enabled but no recipient is configured")
        return

    subject = f"[Mailserver UI] {entry.action} — {entry.status}"
    body = "\n".join(
        (
            f"Action:    {entry.action}",
            f"Status:    {entry.status}",
            f"Actor:     {entry.actor}",
            f"Target:    {entry.target or '-'}",
            f"Source IP: {entry.ip or '-'}",
            f"Time:      {entry.created_at:%Y-%m-%d %H:%M:%S} UTC",
            f"Detail:    {entry.detail or '-'}",
        )
    )
    # Detached from the request: never awaited, never cancelled by the response.
    task = asyncio.create_task(_send_quietly(config, recipients, subject, body))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


#: Strong references to in-flight notification tasks. ``asyncio`` only keeps a
#: weak one, so a task that is not held here may be garbage-collected mid-send.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


async def _send_quietly(
    config: MailSettings,
    recipients: list[str],
    subject: str,
    body: str,
) -> None:
    """Send a notification, logging any failure instead of propagating it."""
    try:
        await send(config, recipients, subject, body)
    except MailError as exc:
        logger.warning("Audit notification not delivered: %s", exc)
