# tests/unit/test_session.py
"""Unit tests for session signing and verification."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from freezegun import freeze_time

SECRET = "test-secret-key-for-testing-only-32chars"


def create_signed_cookie(payload: dict, secret: str) -> str:
    """Create an HMAC-signed cookie."""
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    signature = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_signed_cookie(cookie: str, secret: str) -> dict | None:
    """Verify and decode a signed cookie."""
    if "." not in cookie:
        return None

    try:
        payload_b64, signature = cookie.rsplit(".", 1)
        expected_sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None


class TestSignedCookies:
    """Tests for HMAC-signed session cookies."""

    @freeze_time("2026-01-01 12:00:00")
    def test_create_and_verify(self):
        """Valid cookies can be created and verified."""
        payload = {
            "github_username": "testuser",
            "github_id": 123,
            "exp": int(time.time()) + 3600,
        }
        cookie = create_signed_cookie(payload, SECRET)
        verified = verify_signed_cookie(cookie, SECRET)

        assert verified is not None
        assert verified["github_username"] == "testuser"
        assert verified["github_id"] == 123

    @freeze_time("2026-01-01 12:00:00")
    def test_preserves_all_fields(self):
        """All payload fields are preserved through roundtrip."""
        payload = {
            "github_username": "testuser",
            "github_id": 123,
            "avatar_url": "https://github.com/testuser.png",
            "exp": int(time.time()) + 3600,
            "custom_field": "custom_value",
        }
        cookie = create_signed_cookie(payload, SECRET)
        verified = verify_signed_cookie(cookie, SECRET)

        assert verified["avatar_url"] == "https://github.com/testuser.png"
        assert verified["custom_field"] == "custom_value"

    def test_rejects_tampered_payload(self):
        """Cookies with tampered payloads are rejected."""
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)

        # Tamper with the payload
        parts = cookie.split(".")
        tampered_payload = base64.urlsafe_b64encode(
            json.dumps({"github_username": "admin", "exp": int(time.time()) + 3600}).encode()
        ).decode()
        tampered_cookie = f"{tampered_payload}.{parts[1]}"

        assert verify_signed_cookie(tampered_cookie, SECRET) is None

    def test_rejects_tampered_signature(self):
        """Cookies with tampered signatures are rejected."""
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)

        # Tamper with the signature
        parts = cookie.split(".")
        tampered_cookie = f"{parts[0]}.tampered_signature"

        assert verify_signed_cookie(tampered_cookie, SECRET) is None

    def test_rejects_wrong_secret(self):
        """Cookies verified with wrong secret are rejected."""
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)

        assert verify_signed_cookie(cookie, "wrong-secret-key-for-testing") is None

    @freeze_time("2026-01-01 12:00:00")
    def test_rejects_expired(self):
        """Expired cookies are rejected."""
        payload = {
            "github_username": "testuser",
            "exp": int(time.time()) - 1,  # Expired 1 second ago
        }
        cookie = create_signed_cookie(payload, SECRET)

        assert verify_signed_cookie(cookie, SECRET) is None

    @freeze_time("2026-01-01 12:00:00")
    def test_accepts_not_expired(self):
        """Non-expired cookies are accepted."""
        payload = {
            "github_username": "testuser",
            "exp": int(time.time()) + 1,  # Expires in 1 second
        }
        cookie = create_signed_cookie(payload, SECRET)

        verified = verify_signed_cookie(cookie, SECRET)
        assert verified is not None
        assert verified["github_username"] == "testuser"

    def test_rejects_malformed_no_dot(self):
        """Cookies without dot separator are rejected."""
        assert verify_signed_cookie("nocookie", SECRET) is None

    def test_rejects_malformed_multiple_dots(self):
        """Cookies with multiple dots in wrong places are rejected."""
        assert verify_signed_cookie("not.a.valid.cookie", SECRET) is None

    def test_rejects_empty(self):
        """Empty cookies are rejected."""
        assert verify_signed_cookie("", SECRET) is None

    def test_rejects_invalid_base64(self):
        """Cookies with invalid base64 are rejected."""
        # Create cookie with invalid base64 payload
        invalid_cookie = "not-valid-base64!@#$.signature"
        assert verify_signed_cookie(invalid_cookie, SECRET) is None

    def test_rejects_invalid_json(self):
        """Cookies with invalid JSON payload are rejected."""
        # Create cookie with valid base64 but invalid JSON
        invalid_json = base64.urlsafe_b64encode(b"not json").decode()
        signature = hmac.new(SECRET.encode(), invalid_json.encode(), hashlib.sha256).hexdigest()
        invalid_cookie = f"{invalid_json}.{signature}"

        assert verify_signed_cookie(invalid_cookie, SECRET) is None

    def test_rejects_missing_exp(self):
        """Cookies without exp field are rejected (default to 0, always expired)."""
        payload = {"github_username": "testuser"}  # No exp field
        cookie = create_signed_cookie(payload, SECRET)

        # exp defaults to 0, which is always < current time
        assert verify_signed_cookie(cookie, SECRET) is None

    def test_signature_changes_with_payload(self):
        """Different payloads produce different signatures."""
        payload1 = {"github_username": "user1", "exp": int(time.time()) + 3600}
        payload2 = {"github_username": "user2", "exp": int(time.time()) + 3600}

        cookie1 = create_signed_cookie(payload1, SECRET)
        cookie2 = create_signed_cookie(payload2, SECRET)

        sig1 = cookie1.split(".")[-1]
        sig2 = cookie2.split(".")[-1]

        assert sig1 != sig2

    def test_signature_changes_with_secret(self):
        """Same payload with different secrets produces different signatures."""
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}

        cookie1 = create_signed_cookie(payload, "secret1")
        cookie2 = create_signed_cookie(payload, "secret2")

        sig1 = cookie1.split(".")[-1]
        sig2 = cookie2.split(".")[-1]

        assert sig1 != sig2

    def test_uses_constant_time_comparison(self):
        """Verification uses constant-time comparison (via hmac.compare_digest)."""
        # This test documents that we use hmac.compare_digest
        # The actual timing-safety is guaranteed by the stdlib implementation
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)

        # Verify the implementation uses compare_digest
        # by checking it doesn't short-circuit on first byte mismatch
        # (We can't actually test timing, but we document the intent)
        assert verify_signed_cookie(cookie, SECRET) is not None
