from __future__ import annotations

from src.services import email_service


class FakeSMTP:
    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = None
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password)

    def send_message(self, message):
        self.sent.append(message)


def test_build_password_reset_message_contains_expected_content(monkeypatch):
    monkeypatch.setattr(email_service.settings, "SMTP_FROM", "noreply@example.com")

    msg = email_service._build_password_reset_message(
        "user@example.com", "https://frontend/reset?token=abc"
    )

    assert msg["Subject"] == "Reset your password"
    assert msg["From"] == "noreply@example.com"
    assert msg["To"] == "user@example.com"
    assert "Reset your password using this link" in msg.get_body("plain").get_content()
    assert "https://frontend/reset?token=abc" in msg.get_body("html").get_content()


def test_build_verification_message_contains_expected_content(monkeypatch):
    monkeypatch.setattr(email_service.settings, "SMTP_FROM", "noreply@example.com")

    msg = email_service._build_verification_message(
        "user@example.com", "https://frontend/verify?token=abc"
    )

    assert msg["Subject"] == "Verify your email"
    assert msg["From"] == "noreply@example.com"
    assert msg["To"] == "user@example.com"
    assert "Verify your email using this link" in msg.get_body("plain").get_content()
    assert "https://frontend/verify?token=abc" in msg.get_body("html").get_content()


def test_send_password_reset_email_log_mode(monkeypatch):
    monkeypatch.setattr(email_service.settings, "PASSWORD_RESET_EMAIL_LOG_ONLY", True)
    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "smtp.example.com")
    calls = []
    monkeypatch.setattr(email_service.logger, "info", lambda *args: calls.append(args))

    email_service.send_password_reset_email("user@example.com", "https://reset")

    assert calls


def test_send_password_reset_email_via_smtp(monkeypatch):
    fake = FakeSMTP("smtp.example.com", 587, 20)
    monkeypatch.setattr(email_service.settings, "PASSWORD_RESET_EMAIL_LOG_ONLY", False)
    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "SMTP_PORT", 587)
    monkeypatch.setattr(email_service.settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(email_service.settings, "SMTP_USERNAME", "mailer")
    monkeypatch.setattr(email_service.settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda host, port, timeout: fake)

    email_service.send_password_reset_email("user@example.com", "https://reset")

    assert fake.started_tls is True
    assert fake.logged_in == ("mailer", "secret")
    assert len(fake.sent) == 1


def test_send_verification_email_log_mode_without_host(monkeypatch):
    monkeypatch.setattr(
        email_service.settings, "EMAIL_VERIFICATION_EMAIL_LOG_ONLY", False
    )
    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "")
    calls = []
    monkeypatch.setattr(email_service.logger, "info", lambda *args: calls.append(args))

    email_service.send_verification_email("user@example.com", "https://verify")

    assert calls


def test_send_verification_email_via_smtp_without_login(monkeypatch):
    fake = FakeSMTP("smtp.example.com", 25, 20)
    monkeypatch.setattr(
        email_service.settings, "EMAIL_VERIFICATION_EMAIL_LOG_ONLY", False
    )
    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "SMTP_PORT", 25)
    monkeypatch.setattr(email_service.settings, "SMTP_USE_TLS", False)
    monkeypatch.setattr(email_service.settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(email_service.settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda host, port, timeout: fake)

    email_service.send_verification_email("user@example.com", "https://verify")

    assert fake.started_tls is False
    assert fake.logged_in is None
    assert len(fake.sent) == 1


def test_send_verification_email_via_smtp_with_tls_and_login(monkeypatch):
    fake = FakeSMTP("smtp.example.com", 587, 20)
    monkeypatch.setattr(
        email_service.settings, "EMAIL_VERIFICATION_EMAIL_LOG_ONLY", False
    )
    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "SMTP_PORT", 587)
    monkeypatch.setattr(email_service.settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(email_service.settings, "SMTP_USERNAME", "mailer")
    monkeypatch.setattr(email_service.settings, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda host, port, timeout: fake)

    email_service.send_verification_email("user@example.com", "https://verify")

    assert fake.started_tls is True
    assert fake.logged_in == ("mailer", "secret")
    assert len(fake.sent) == 1
