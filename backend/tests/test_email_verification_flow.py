from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from src.db.models import AuditLog, User
from src.db.models.email_verification_token import EmailVerificationToken
from src.services import auth_service


def _capture_verification_link(monkeypatch) -> dict[str, str]:
    captured: dict[str, str] = {}

    def _fake_send_verification_email(to_email: str, verify_link: str) -> None:
        captured["to_email"] = to_email
        captured["verify_link"] = verify_link

    monkeypatch.setattr(
        "src.services.email_service.send_verification_email",
        _fake_send_verification_email,
    )
    return captured


def _token_from_link(verify_link: str) -> str:
    return parse_qs(urlparse(verify_link).query).get("token", [""])[0]


def _enable_verification_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.core.config.settings.NEW_USERS_REQUIRE_EMAIL_VERIFICATION", True
    )
    monkeypatch.setattr("src.core.config.settings.ALLOW_LEGACY_UNVERIFIED_LOGIN", False)


def test_register_creates_unverified_user_and_token(
    client, db_session, gp_user_payload, monkeypatch
):
    _enable_verification_mode(monkeypatch)
    captured = _capture_verification_link(monkeypatch)

    resp = client.post("/auth/register", json=gp_user_payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["requires_email_verification"] is True
    assert data["access_token"] is None

    user = db_session.query(User).filter(User.email == gp_user_payload["email"]).first()
    assert user is not None
    assert user.email_verified is False

    token_row = db_session.query(EmailVerificationToken).one()
    assert token_row.user_id == user.id
    assert token_row.token_hash != _token_from_link(captured["verify_link"])


def test_login_blocked_for_unverified_user(client, gp_user_payload, monkeypatch):
    _enable_verification_mode(monkeypatch)
    _capture_verification_link(monkeypatch)

    register = client.post("/auth/register", json=gp_user_payload)
    assert register.status_code == 201

    login = client.post(
        "/auth/login",
        data={
            "username": gp_user_payload["email"],
            "password": gp_user_payload["password"],
        },
    )
    assert login.status_code == 403
    assert "verify your email" in login.json()["detail"].lower()


def test_confirm_email_verification_with_valid_token(
    client, db_session, gp_user_payload, monkeypatch
):
    _enable_verification_mode(monkeypatch)
    captured = _capture_verification_link(monkeypatch)

    client.post("/auth/register", json=gp_user_payload)
    token = _token_from_link(captured["verify_link"])

    verify = client.post("/auth/verify-email/confirm", json={"token": token})
    assert verify.status_code == 200

    user = db_session.query(User).filter(User.email == gp_user_payload["email"]).first()
    assert user is not None
    assert user.email_verified is True
    assert user.email_verified_at is not None

    login = client.post(
        "/auth/login",
        data={
            "username": gp_user_payload["email"],
            "password": gp_user_payload["password"],
        },
    )
    assert login.status_code == 200


def test_token_reuse_rejected(client, gp_user_payload, monkeypatch):
    _enable_verification_mode(monkeypatch)
    captured = _capture_verification_link(monkeypatch)

    client.post("/auth/register", json=gp_user_payload)
    token = _token_from_link(captured["verify_link"])

    first = client.post("/auth/verify-email/confirm", json={"token": token})
    second = client.post("/auth/verify-email/confirm", json={"token": token})

    assert first.status_code == 200
    assert second.status_code == 400
    assert "invalid or expired" in second.json()["detail"].lower()


def test_expired_token_rejected(client, db_session, gp_user_payload, monkeypatch):
    _enable_verification_mode(monkeypatch)
    captured = _capture_verification_link(monkeypatch)

    client.post("/auth/register", json=gp_user_payload)
    row = db_session.query(EmailVerificationToken).one()
    row.expires_at = auth_service._utcnow() - timedelta(minutes=1)
    db_session.commit()

    token = _token_from_link(captured["verify_link"])
    resp = client.post("/auth/verify-email/confirm", json={"token": token})

    assert resp.status_code == 400
    assert "invalid or expired" in resp.json()["detail"].lower()


def test_invalid_token_rejected(client):
    resp = client.post("/auth/verify-email/confirm", json={"token": "not-a-real-token"})
    assert resp.status_code == 400
    assert "invalid or expired" in resp.json()["detail"].lower()


def test_resend_is_generic_and_rate_limited(client, gp_user_payload, monkeypatch):
    _enable_verification_mode(monkeypatch)
    _capture_verification_link(monkeypatch)

    client.post("/auth/register", json=gp_user_payload)

    responses = [
        client.post(
            "/auth/resend-verification", json={"email": gp_user_payload["email"]}
        )
        for _ in range(7)
    ]

    assert all(r.status_code == 200 for r in responses)
    assert all("message" in r.json() for r in responses)

    unknown = client.post("/auth/resend-verification", json={"email": "ghost@nhs.uk"})
    assert unknown.status_code == 200
    assert unknown.json() == responses[0].json()


def test_audit_entries_created_for_verification_flow(
    client, db_session, gp_user_payload, monkeypatch
):
    _enable_verification_mode(monkeypatch)
    captured = _capture_verification_link(monkeypatch)

    client.post("/auth/register", json=gp_user_payload)
    token = _token_from_link(captured["verify_link"])
    client.post("/auth/verify-email/confirm", json={"token": token})

    user = db_session.query(User).filter(User.email == gp_user_payload["email"]).first()
    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.user_id == user.id).all()
    }

    assert "EMAIL_VERIFICATION_REQUESTED" in actions
    assert "EMAIL_VERIFICATION_SENT" in actions
    assert "EMAIL_VERIFIED" in actions


def test_legacy_users_default_to_verified_on_register_when_flag_off(
    client, gp_user_payload, monkeypatch
):
    monkeypatch.setattr(
        "src.core.config.settings.NEW_USERS_REQUIRE_EMAIL_VERIFICATION", False
    )

    resp = client.post("/auth/register", json=gp_user_payload)
    assert resp.status_code == 201

    data = resp.json()
    assert data["requires_email_verification"] is False
    assert data["access_token"]
