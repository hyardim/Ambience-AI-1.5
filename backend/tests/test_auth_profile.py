"""
Tests for PATCH /auth/profile.
"""


class TestUpdateProfile:

    def test_update_full_name_success(self, client, gp_headers):
        resp = client.patch("/auth/profile", json={"full_name": "New Name"}, headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "New Name"

    def test_update_specialty_success(self, client, gp_headers):
        resp = client.patch("/auth/profile", json={"specialty": "cardiology"}, headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["specialty"] == "cardiology"

    def test_update_password_success(self, client, gp_user_payload, gp_headers):
        resp = client.patch("/auth/profile", json={
            "current_password": gp_user_payload["password"],
            "new_password": "NewPass456!",
        }, headers=gp_headers)
        assert resp.status_code == 200
        # Verify the new password works for login
        login = client.post("/auth/login", data={
            "username": gp_user_payload["email"],
            "password": "NewPass456!",
        })
        assert login.status_code == 200

    def test_update_password_wrong_current_fails(self, client, gp_headers):
        resp = client.patch("/auth/profile", json={
            "current_password": "wrongpassword",
            "new_password": "NewPass456!",
        }, headers=gp_headers)
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()

    def test_update_password_without_current_fails(self, client, gp_headers):
        resp = client.patch("/auth/profile", json={"new_password": "NewPass456!"}, headers=gp_headers)
        assert resp.status_code == 400
        assert "current_password" in resp.json()["detail"].lower()

    def test_update_unauthenticated_fails(self, client):
        resp = client.patch("/auth/profile", json={"full_name": "Hacker"})
        assert resp.status_code == 401

    def test_update_reflects_in_me(self, client, gp_headers):
        client.patch("/auth/profile", json={"full_name": "Updated Name"}, headers=gp_headers)
        me = client.get("/auth/me", headers=gp_headers)
        assert me.json()["full_name"] == "Updated Name"
