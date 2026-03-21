"""
Tests for sub-issue 4 — password strength validation.

Rules enforced on register, reset-password, and profile PATCH:
  - Minimum 8 characters
  - At least 1 uppercase letter
  - At least 1 lowercase letter
  - At least 1 digit
  - At least 1 special character
"""

from urllib.parse import parse_qs, urlparse

STRONG_PASSWORD = "Secure1!"


class TestPasswordStrengthOnRegister:
    def test_strong_password_is_accepted(self, client, gp_user_payload):
        gp_user_payload["password"] = STRONG_PASSWORD
        assert client.post("/auth/register", json=gp_user_payload).status_code == 201

    def test_too_short_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Ab1!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 422

    def test_no_uppercase_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "abcdefg1!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 422

    def test_no_lowercase_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "ABCDEFG1!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 422

    def test_no_digit_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Abcdefgh!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 422

    def test_no_special_char_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Abcdefg1"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 422

    def test_common_password_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Password123!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 422

    def test_multiple_failing_rules_reported_together(self, client, gp_user_payload):
        gp_user_payload["password"] = "abc"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 422

    def test_boundary_exactly_8_chars_all_rules_met(self, client, gp_user_payload):
        gp_user_payload["password"] = "Secure1!"
        assert client.post("/auth/register", json=gp_user_payload).status_code == 201

    def test_boundary_7_chars_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Secur1!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 422


class TestPasswordStrengthOnReset:
    @staticmethod
    def _issue_reset_token(client, email: str, monkeypatch) -> str:
        payload: dict[str, str] = {}

        def _fake_send_password_reset_email(to_email: str, reset_link: str) -> None:
            payload["to_email"] = to_email
            payload["reset_link"] = reset_link

        monkeypatch.setattr(
            "src.services.email_service.send_password_reset_email",
            _fake_send_password_reset_email,
        )
        resp = client.post("/auth/forgot-password", json={"email": email})
        assert resp.status_code == 200

        token = parse_qs(urlparse(payload["reset_link"]).query).get("token", [""])[0]
        assert token
        return token

    def test_strong_password_accepted_on_reset(
        self, client, registered_gp, gp_user_payload, monkeypatch
    ):
        token = self._issue_reset_token(client, gp_user_payload["email"], monkeypatch)
        resp = client.post(
            "/auth/reset-password/confirm",
            json={"token": token, "new_password": "NewSecure1!"},
        )
        assert resp.status_code == 200

    def test_weak_password_rejected_on_reset(
        self, client, registered_gp, gp_user_payload, monkeypatch
    ):
        token = self._issue_reset_token(client, gp_user_payload["email"], monkeypatch)
        resp = client.post(
            "/auth/reset-password/confirm",
            json={"token": token, "new_password": "weak"},
        )
        assert resp.status_code == 422

    def test_no_uppercase_rejected_on_reset(
        self, client, registered_gp, gp_user_payload, monkeypatch
    ):
        token = self._issue_reset_token(client, gp_user_payload["email"], monkeypatch)
        resp = client.post(
            "/auth/reset-password/confirm",
            json={"token": token, "new_password": "abcdefg1!"},
        )
        assert resp.status_code == 422

    def test_no_special_char_rejected_on_reset(
        self, client, registered_gp, gp_user_payload, monkeypatch
    ):
        token = self._issue_reset_token(client, gp_user_payload["email"], monkeypatch)
        resp = client.post(
            "/auth/reset-password/confirm",
            json={"token": token, "new_password": "Abcdefg1"},
        )
        assert resp.status_code == 422

    def test_common_password_rejected_on_reset(
        self, client, registered_gp, gp_user_payload, monkeypatch
    ):
        token = self._issue_reset_token(client, gp_user_payload["email"], monkeypatch)
        resp = client.post(
            "/auth/reset-password/confirm",
            json={"token": token, "new_password": "Password123!"},
        )
        assert resp.status_code == 422


class TestPasswordStrengthOnProfileUpdate:
    def test_strong_new_password_accepted(self, client, gp_headers, gp_user_payload):
        resp = client.patch(
            "/auth/profile",
            json={
                "current_password": gp_user_payload["password"],
                "new_password": "NewSecure1!",
            },
            headers=gp_headers,
        )
        assert resp.status_code == 200

    def test_weak_new_password_rejected(self, client, gp_headers, gp_user_payload):
        resp = client.patch(
            "/auth/profile",
            json={
                "current_password": gp_user_payload["password"],
                "new_password": "weak",
            },
            headers=gp_headers,
        )
        assert resp.status_code == 422

    def test_no_uppercase_rejected_on_profile(
        self, client, gp_headers, gp_user_payload
    ):
        resp = client.patch(
            "/auth/profile",
            json={
                "current_password": gp_user_payload["password"],
                "new_password": "abcdefg1!",
            },
            headers=gp_headers,
        )
        assert resp.status_code == 422

    def test_no_digit_rejected_on_profile(self, client, gp_headers, gp_user_payload):
        resp = client.patch(
            "/auth/profile",
            json={
                "current_password": gp_user_payload["password"],
                "new_password": "Abcdefgh!",
            },
            headers=gp_headers,
        )
        assert resp.status_code == 422

    def test_common_password_rejected_on_profile(
        self, client, gp_headers, gp_user_payload
    ):
        resp = client.patch(
            "/auth/profile",
            json={
                "current_password": gp_user_payload["password"],
                "new_password": "Password123!",
            },
            headers=gp_headers,
        )
        assert resp.status_code == 422

    def test_profile_update_without_new_password_not_affected(self, client, gp_headers):
        resp = client.patch(
            "/auth/profile",
            json={"full_name": "Dr. Alice Updated"},
            headers=gp_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Dr. Alice Updated"
