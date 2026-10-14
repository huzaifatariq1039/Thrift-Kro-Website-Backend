import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote


logger = logging.getLogger(__name__)


def _is_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def send_auth_action_email(recipient: str, purpose: str, token: str) -> bool:
    """Deliver a one-time authentication link without logging or storing the raw token."""
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    if not smtp_host or not sender:
        logger.error("Authentication email delivery is not configured")
        return False

    frontend_url = os.getenv("FRONTEND_PUBLIC_URL", "http://localhost:5173").rstrip("/")
    if purpose == "verify_email":
        path = "/verify-email"
        subject = "Verify your Thrift Kro email"
        heading = "Verify your email address"
    elif purpose == "reset_password":
        path = "/reset-password"
        subject = "Reset your Thrift Kro password"
        heading = "Reset your password"
    else:
        raise ValueError("Unsupported authentication email purpose")

    action_url = f"{frontend_url}{path}?token={quote(token, safe='')}"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(
        f"{heading}\n\nOpen this one-time link:\n{action_url}\n\n"
        "If you did not request this action, you can ignore this email."
    )

    use_ssl = _is_enabled(os.getenv("SMTP_USE_SSL"))
    start_tls = _is_enabled(os.getenv("SMTP_STARTTLS", "true")) and not use_ssl
    default_port = 465 if use_ssl else 587
    port = int(os.getenv("SMTP_PORT", str(default_port)))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP

    try:
        with smtp_class(smtp_host, port, timeout=10) as client:
            if start_tls:
                client.starttls(context=ssl.create_default_context())
            if username:
                client.login(username, password)
            client.send_message(message)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("Authentication email delivery failed")
        return False
