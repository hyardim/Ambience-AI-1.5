def test_verification_status_returns_payload_for_authenticated_user(client, gp_headers):
    response = client.get("/auth/verification-status", headers=gp_headers)

    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert "email_verified" in data
