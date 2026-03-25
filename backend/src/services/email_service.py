import logging
import smtplib
from email.message import EmailMessage

from src.core.config import settings

logger = logging.getLogger(__name__)


def _build_password_reset_message(to_email: str, reset_link: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Reset your password"
    msg["From"] = settings.SMTP_FROM or "no-reply@ambience.local"
    msg["To"] = to_email

    text_body = (
        "We received a request to reset your password.\n\n"
        f"Reset your password using this link: {reset_link}\n\n"
        "If you did not request a password reset, you can safely ignore this email.\n"
        "This link will expire soon."
    )
    msg.set_content(text_body)

    html_body = (
        "<p>We received a request to reset your password.</p>"
        f'<p><a href="{reset_link}">Reset your password</a></p>'
        "<p>If you did not request a password reset, you can safely ignore this email.</p>"
        "<p>This link will expire soon.</p>"
    )
    msg.add_alternative(html_body, subtype="html")
    return msg


def _build_verification_message(to_email: str, verify_link: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Verify your email"
    msg["From"] = settings.SMTP_FROM or "no-reply@ambience.local"
    msg["To"] = to_email

    text_body = (
        "Welcome to Ambience AI.\n\n"
        f"Verify your email using this link: {verify_link}\n\n"
        "If you did not create this account, you can ignore this email.\n"
        "This link will expire soon."
    )
    msg.set_content(text_body)

    html_body = (
        "<p>Welcome to Ambience AI.</p>"
        f'<p><a href="{verify_link}">Verify your email</a></p>'
        "<p>If you did not create this account, you can ignore this email.</p>"
        "<p>This link will expire soon.</p>"
    )
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    if settings.PASSWORD_RESET_EMAIL_LOG_ONLY or not settings.SMTP_HOST:
        logger.info(
            "Password reset email (log mode) to=%s link=%s", to_email, reset_link
        )
        return

    message = _build_password_reset_message(to_email, reset_link)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()

        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

        smtp.send_message(message)


def send_verification_email(to_email: str, verify_link: str) -> None:
    if settings.EMAIL_VERIFICATION_EMAIL_LOG_ONLY or not settings.SMTP_HOST:
        logger.info(
            "Verification email (log mode) to=%s link=%s", to_email, verify_link
        )
        return

    message = _build_verification_message(to_email, verify_link)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()

        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

        smtp.send_message(message)
