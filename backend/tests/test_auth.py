"""
Tests for /auth endpoints: register, login, and /me.
"""

import pytest


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

class TestRegister:

    def test_register_gp_success(self, client, gp_user_payload):
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == gp_user_payload["email"]
        assert data["user"]["role"] == "gp"
        assert data["user"]["full_name"] == "Alice GP"

    def test_register_specialist_success(self, client, specialist_user_payload):
        resp = client.post("/auth/register", json=specialist_user_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["user"]["role"] == "specialist"
        assert data["user"]["email"] == specialist_user_payload["email"]

    def test_register_specialist_without_specialty_fails(self, client):
        resp = client.post("/auth/register", json={
            "first_name": "No",
            "last_name": "Specialty",
            "email": "no.specialty@nhs.uk",
            "password": "pass123",
            "role": "specialist",
        })
        assert resp.status_code == 400
        assert "specialty" in resp.json()["detail"].lower()

    def test_register_duplicate_email_fails(self, client, gp_user_payload):
        client.post("/auth/register", json=gp_user_payload)
        resp = client.post("/auth/register", json=gp_user_payload)
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_invalid_email_fails(self, client):
        resp = client.post("/auth/register", json={
            "first_name": "Bad",
            "last_name": "Email",
            "email": "not-an-email",
            "password": "pass123",
            "role": "gp",
        })
        assert resp.status_code == 422

    def test_register_missing_required_fields_fails(self, client):
        resp = client.post("/auth/register", json={"email": "test@nhs.uk"})
        assert resp.status_code == 422

    def test_register_full_name_is_concatenated(self, client):
        resp = client.post("/auth/register", json={
            "first_name": "  John  ",
            "last_name": "  Doe  ",
            "email": "john.doe@nhs.uk",
            "password": "pass123",
            "role": "gp",
        })
        assert resp.status_code == 201
        assert resp.json()["user"]["full_name"] == "John Doe"

    def test_register_returns_jwt_token(self, client, gp_user_payload):
        resp = client.post("/auth/register", json=gp_user_payload)
        token = resp.json()["access_token"]
        # JWT has three dot-separated parts
        assert len(token.split(".")) == 3


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

class TestLogin:

    def test_login_success(self, client, gp_user_payload, registered_gp):
        resp = client.post("/auth/login", data={
            "username": gp_user_payload["email"],
            "password": gp_user_payload["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == gp_user_payload["email"]

    def test_login_wrong_password_fails(self, client, gp_user_payload, registered_gp):
        resp = client.post("/auth/login", data={
            "username": gp_user_payload["email"],
            "password": "wrongpassword",
        })
        assert resp.status_code == 401
        assert "incorrect" in resp.json()["detail"].lower()

    def test_login_nonexistent_user_fails(self, client):
        resp = client.post("/auth/login", data={
            "username": "ghost@nhs.uk",
            "password": "doesntmatter",
        })
        assert resp.status_code == 401

    def test_login_returns_correct_role(self, client, specialist_user_payload, registered_specialist):
        resp = client.post("/auth/login", data={
            "username": specialist_user_payload["email"],
            "password": specialist_user_payload["password"],
        })
        assert resp.status_code == 200
        assert resp.json()["user"]["role"] == "specialist"

    def test_login_returns_jwt_token(self, client, gp_user_payload, registered_gp):
        resp = client.post("/auth/login", data={
            "username": gp_user_payload["email"],
            "password": gp_user_payload["password"],
        })
        token = resp.json()["access_token"]
        assert len(token.split(".")) == 3

    def test_login_empty_credentials_fails(self, client):
        # FastAPI's OAuth2PasswordRequestForm rejects empty strings at
        # validation layer (422) before the handler is even reached.
        resp = client.post("/auth/login", data={"username": "", "password": ""})
        assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------

class TestMe:

    def test_me_returns_current_user(self, client, gp_user_payload, gp_headers):
        resp = client.get("/auth/me", headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == gp_user_payload["email"]
        assert data["role"] == "gp"
        assert data["full_name"] == "Alice GP"

    def test_me_unauthenticated_fails(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token_fails(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.valid.token"})
        assert resp.status_code == 401

    def test_me_malformed_header_fails(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "NotBearer sometoken"})
        assert resp.status_code == 401

    def test_me_specialist_returns_correct_data(self, client, specialist_user_payload, specialist_headers):
        resp = client.get("/auth/me", headers=specialist_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "specialist"
        assert resp.json()["email"] == specialist_user_payload["email"]
