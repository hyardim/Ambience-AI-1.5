"""
Tests for src/core/security.py — password hashing and JWT utilities.
"""

from datetime import timedelta

import jwt
import pytest

from src.core.config import settings
from src.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_hash_is_not_plaintext(self):
        hashed = get_password_hash("mysecret")
        assert hashed != "mysecret"

    def test_verify_correct_password(self):
        hashed = get_password_hash("correcthorse")
        assert verify_password("correcthorse", hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("correcthorse")
        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_produces_different_hashes(self):
        h1 = get_password_hash("samepassword")
        h2 = get_password_hash("samepassword")
        # bcrypt uses a random salt each time
        assert h1 != h2

    def test_both_hashes_verify_against_same_plaintext(self):
        h1 = get_password_hash("samepassword")
        h2 = get_password_hash("samepassword")
        assert verify_password("samepassword", h1) is True
        assert verify_password("samepassword", h2) is True

    def test_empty_string_password_hashes_and_verifies(self):
        hashed = get_password_hash("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False


# ---------------------------------------------------------------------------
# JWT token creation
# ---------------------------------------------------------------------------

class TestCreateAccessToken:

    def test_token_is_a_string(self):
        token = create_access_token({"sub": "user@nhs.uk", "role": "gp"})
        assert isinstance(token, str)

    def test_token_has_three_jwt_parts(self):
        token = create_access_token({"sub": "user@nhs.uk", "role": "gp"})
        assert len(token.split(".")) == 3

    def test_token_contains_sub_claim(self):
        token = create_access_token({"sub": "dr.house@nhs.uk", "role": "gp"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "dr.house@nhs.uk"

    def test_token_contains_role_claim(self):
        token = create_access_token({"sub": "specialist@nhs.uk", "role": "specialist"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["role"] == "specialist"

    def test_token_contains_exp_claim(self):
        token = create_access_token({"sub": "user@nhs.uk", "role": "gp"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_custom_expiry_is_respected(self):
        short = create_access_token({"sub": "a@b.com"}, expires_delta=timedelta(seconds=5))
        long = create_access_token({"sub": "a@b.com"}, expires_delta=timedelta(hours=24))
        short_exp = jwt.decode(short, SECRET_KEY, algorithms=[ALGORITHM])["exp"]
        long_exp = jwt.decode(long, SECRET_KEY, algorithms=[ALGORITHM])["exp"]
        assert long_exp > short_exp

    def test_expired_token_raises_on_decode(self):
        token = create_access_token(
            {"sub": "user@nhs.uk", "role": "gp"},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    def test_tampered_token_raises_on_decode(self):
        token = create_access_token({"sub": "user@nhs.uk", "role": "gp"})
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(jwt.PyJWTError):
            jwt.decode(tampered, SECRET_KEY, algorithms=[ALGORITHM])

    def test_wrong_secret_raises_on_decode(self):
        token = create_access_token({"sub": "user@nhs.uk", "role": "gp"})
        with pytest.raises(jwt.PyJWTError):
            jwt.decode(token, "wrong_secret", algorithms=[ALGORITHM])
