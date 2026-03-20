from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from src.db.models import AuditLog, User
from src.db.models.password_reset_token import PasswordResetToken
from src.services import auth_service


def _capture_reset_link(monkeypatch) -> dict[str, str]:
    captured: dict[str, str] = {}

    def _fake_send_password_reset_email(to_email: str, reset_link: str) -> None:
        captured["to_email"] = to_email
        captured["reset_link"] = reset_link

    monkeypatch.setattr(
        "src.services.email_service.send_password_reset_email",
        _fake_send_password_reset_email,
    )
    return captured


def _token_from_link(reset_link: str) -> str:
    return parse_qs(urlparse(reset_link).query).get("token", [""])[0]


def test_forgot_password_generic_success_for_existing_and_non_existing(
    client,
    registered_gp,
    gp_user_payload,
    monkeypatch,
):
    captured = _capture_reset_link(monkeypatch)

    existing = client.post("/auth/forgot-password", json={"email": gp_user_payload["email"]})
    non_existing = client.post("/auth/forgot-password", json={"email": "ghost@nhs.uk"})

    assert existing.status_code == 200
    assert non_existing.status_code == 200
    assert existing.json() == non_existing.json()
    assert "message" in existing.json()
    assert captured["to_email"] == gp_user_payload["email"]


def test_forgot_password_creates_hashed_token_record(
    client,
    db_session,
    registered_gp,
    gp_user_payload,
    monkeypatch,
):
    captured = _capture_reset_link(monkeypatch)

    resp = client.post("/auth/forgot-password", json={"email": gp_user_payload["email"]})
    assert resp.status_code == 200

    token_row = db_session.query(PasswordResetToken).one()
    raw_token = _token_from_link(captured["reset_link"])

    assert raw_token
    assert token_row.token_hash
    assert token_row.token_hash != raw_token
    assert len(token_row.token_hash) == 64


def test_valid_token_resets_password_successfully(
    client,
    db_session,
    registered_gp,
    gp_user_payload,
    monkeypatch,
):
    captured = _capture_reset_link(monkeypatch)
    client.post("/auth/forgot-password", json={"email": gp_user_payload["email"]})

    token = _token_from_link(captured["reset_link"])
    reset = client.post(
        "/auth/reset-password/confirm",
        json={"token": token, "new_password": "NewSecure1!"},
    )
    assert reset.status_code == 200

    login = client.post(
        "/auth/login",
        data={"username": gp_user_payload["email"], "password": "NewSecure1!"},
    )
    assert login.status_code == 200

    used_row = db_session.query(PasswordResetToken).one()
    assert used_row.used_at is not None


def test_token_cannot_be_reused(client, registered_gp, gp_user_payload, monkeypatch):
    captured = _capture_reset_link(monkeypatch)
    client.post("/auth/forgot-password", json={"email": gp_user_payload["email"]})

    token = _token_from_link(captured["reset_link"])
    first = client.post(
        "/auth/reset-password/confirm",
        json={"token": token, "new_password": "NewSecure1!"},
    )
    second = client.post(
        "/auth/reset-password/confirm",
        json={"token": token, "new_password": "Another1!"},
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert "invalid or expired" in second.json()["detail"].lower()


def test_expired_token_rejected(
    client,
    db_session,
    registered_gp,
    gp_user_payload,
    monkeypatch,
):
    captured = _capture_reset_link(monkeypatch)
    client.post("/auth/forgot-password", json={"email": gp_user_payload["email"]})

    token_row = db_session.query(PasswordResetToken).one()
    token_row.expires_at = auth_service._utcnow() - timedelta(minutes=1)
    db_session.commit()

    token = _token_from_link(captured["reset_link"])
    resp = client.post(
        "/auth/reset-password/confirm",
        json={"token": token, "new_password": "NewSecure1!"},
    )

    assert resp.status_code == 400
    assert "invalid or expired" in resp.json()["detail"].lower()


def test_invalid_token_rejected(client, registered_gp):
    resp = client.post(
        "/auth/reset-password/confirm",
        json={"token": "not-a-real-token", "new_password": "NewSecure1!"},
    )
    assert resp.status_code == 400
    assert "invalid or expired" in resp.json()["detail"].lower()


def test_password_policy_enforced_during_reset(
    client,
    registered_gp,
    gp_user_payload,
    monkeypatch,
):
    captured = _capture_reset_link(monkeypatch)
    client.post("/auth/forgot-password", json={"email": gp_user_payload["email"]})

    token = _token_from_link(captured["reset_link"])
    resp = client.post(
        "/auth/reset-password/confirm",
        json={"token": token, "new_password": "weak"},
    )

    assert resp.status_code == 400
    assert "password must contain" in resp.json()["detail"].lower()


def test_audit_entries_created_for_request_and_completion(
    client,
    db_session,
    registered_gp,
    gp_user_payload,
    monkeypatch,
):
    captured = _capture_reset_link(monkeypatch)
    client.post("/auth/forgot-password", json={"email": gp_user_payload["email"]})

    token = _token_from_link(captured["reset_link"])
    reset = client.post(
        "/auth/reset-password/confirm",
        json={"token": token, "new_password": "NewSecure1!"},
    )
    assert reset.status_code == 200

    user = db_session.query(User).filter(User.email == gp_user_payload["email"]).first()
    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.user_id == user.id).all()
    }

    assert "PASSWORD_RESET_REQUESTED" in actions
    assert "PASSWORD_RESET_COMPLETED" in actions
