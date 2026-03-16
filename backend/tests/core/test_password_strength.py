"""
Tests for sub-issue 4 — password strength validation.

Rules enforced on register, reset-password, and profile PATCH:
  • Minimum 8 characters
  • At least 1 uppercase letter
  • At least 1 lowercase letter
  • At least 1 digit
  • At least 1 special character
"""

STRONG_PASSWORD = "Secure1!"


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


class TestPasswordStrengthOnRegister:
    def test_strong_password_is_accepted(self, client, gp_user_payload):
        gp_user_payload["password"] = STRONG_PASSWORD
        assert client.post("/auth/register", json=gp_user_payload).status_code == 201

    def test_too_short_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Ab1!"  # 4 chars
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]

    def test_no_uppercase_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "abcdefg1!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 400
        assert "uppercase" in resp.json()["detail"]

    def test_no_lowercase_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "ABCDEFG1!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 400
        assert "lowercase" in resp.json()["detail"]

    def test_no_digit_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Abcdefgh!"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 400
        assert "digit" in resp.json()["detail"]

    def test_no_special_char_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Abcdefg1"
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 400
        assert "special" in resp.json()["detail"]

    def test_multiple_failing_rules_reported_together(self, client, gp_user_payload):
        gp_user_payload["password"] = "abc"  # short, no upper, no digit, no special
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "8 characters" in detail
        assert "uppercase" in detail
        assert "digit" in detail
        assert "special" in detail

    def test_boundary_exactly_8_chars_all_rules_met(self, client, gp_user_payload):
        gp_user_payload["password"] = "Secure1!"  # exactly 8 chars
        assert client.post("/auth/register", json=gp_user_payload).status_code == 201

    def test_boundary_7_chars_rejected(self, client, gp_user_payload):
        gp_user_payload["password"] = "Secur1!"  # 7 chars
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /auth/reset-password
# ---------------------------------------------------------------------------


class TestPasswordStrengthOnReset:
    def test_strong_password_accepted_on_reset(
        self, client, registered_gp, gp_user_payload
    ):
        resp = client.post(
            "/auth/reset-password",
            json={
                "email": gp_user_payload["email"],
                "new_password": "NewSecure1!",
            },
        )
        assert resp.status_code == 200

    def test_weak_password_rejected_on_reset(
        self, client, registered_gp, gp_user_payload
    ):
        resp = client.post(
            "/auth/reset-password",
            json={
                "email": gp_user_payload["email"],
                "new_password": "weak",
            },
        )
        assert resp.status_code == 400

    def test_no_uppercase_rejected_on_reset(
        self, client, registered_gp, gp_user_payload
    ):
        resp = client.post(
            "/auth/reset-password",
            json={
                "email": gp_user_payload["email"],
                "new_password": "abcdefg1!",
            },
        )
        assert resp.status_code == 400
        assert "uppercase" in resp.json()["detail"]

    def test_no_special_char_rejected_on_reset(
        self, client, registered_gp, gp_user_payload
    ):
        resp = client.post(
            "/auth/reset-password",
            json={
                "email": gp_user_payload["email"],
                "new_password": "Abcdefg1",
            },
        )
        assert resp.status_code == 400
        assert "special" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# PATCH /auth/profile
# ---------------------------------------------------------------------------


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
        assert resp.status_code == 400

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
        assert resp.status_code == 400
        assert "uppercase" in resp.json()["detail"]

    def test_no_digit_rejected_on_profile(self, client, gp_headers, gp_user_payload):
        resp = client.patch(
            "/auth/profile",
            json={
                "current_password": gp_user_payload["password"],
                "new_password": "Abcdefgh!",
            },
            headers=gp_headers,
        )
        assert resp.status_code == 400
        assert "digit" in resp.json()["detail"]

    def test_profile_update_without_new_password_not_affected(self, client, gp_headers):
        """Updating only full_name skips password validation entirely."""
        resp = client.patch(
            "/auth/profile", json={"full_name": "Dr. Alice Updated"}, headers=gp_headers
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Dr. Alice Updated"
