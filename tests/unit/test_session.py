# tests/unit/test_session.py
"""Unit tests for session signing and verification.

Tests the HMAC-signed session cookie functions from src.auth.
"""

import base64
import hashlib
import hmac
import json
import time

from freezegun import freeze_time

from src.auth import create_signed_cookie
from src.auth import verify_signed_cookie as _verify_signed_cookie

SECRET = "test-secret-key-for-testing-only-32chars"


def verify_signed_cookie(cookie: str, secret: str) -> dict | None:
    """Wrapper around src.auth.verify_signed_cookie with grace_seconds=0 for exact expiry tests."""
    return _verify_signed_cookie(cookie, secret, grace_seconds=0)


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
        assert verified["exp"] == int(time.time()) + 3600
        # Cookie format is base64_payload.signature
        assert "." in cookie
        parts = cookie.split(".")
        assert len(parts) == 2
        # Same cookie with wrong secret must be rejected
        assert verify_signed_cookie(cookie, "wrong-secret") is None

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
        assert verified["github_username"] == "testuser"
        assert verified["github_id"] == 123
        assert verified["exp"] == int(time.time()) + 3600
        # All original keys present in the verified result
        assert set(payload.keys()) == set(verified.keys())

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
        # Original cookie still works (tampering doesn't corrupt the original)
        assert verify_signed_cookie(cookie, SECRET) is not None
        assert verify_signed_cookie(cookie, SECRET)["github_username"] == "testuser"

    def test_rejects_tampered_signature(self):
        """Cookies with tampered signatures are rejected."""
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)

        # Tamper with the signature
        parts = cookie.split(".")
        tampered_cookie = f"{parts[0]}.tampered_signature"

        assert verify_signed_cookie(tampered_cookie, SECRET) is None
        # Even a single character change in the signature should cause rejection
        real_sig = parts[1]
        flipped_sig = ("1" if real_sig[0] == "0" else "0") + real_sig[1:]
        assert verify_signed_cookie(f"{parts[0]}.{flipped_sig}", SECRET) is None
        # Original cookie is still valid
        assert verify_signed_cookie(cookie, SECRET) is not None

    def test_rejects_wrong_secret(self):
        """Cookies verified with wrong secret are rejected."""
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)

        assert verify_signed_cookie(cookie, "wrong-secret-key-for-testing") is None
        # Verify with the correct secret succeeds
        assert verify_signed_cookie(cookie, SECRET) is not None
        # Even a slightly different secret (off by one char) is rejected
        assert verify_signed_cookie(cookie, SECRET + "x") is None

    @freeze_time("2026-01-01 12:00:00")
    def test_rejects_expired(self):
        """Expired cookies are rejected."""
        payload = {
            "github_username": "testuser",
            "exp": int(time.time()) - 1,  # Expired 1 second ago
        }
        cookie = create_signed_cookie(payload, SECRET)

        assert verify_signed_cookie(cookie, SECRET) is None
        # The signature is still valid -- it's specifically the expiry that causes rejection
        parts = cookie.split(".")
        expected_sig = hmac.new(SECRET.encode(), parts[0].encode(), hashlib.sha256).hexdigest()
        assert hmac.compare_digest(parts[1], expected_sig)
        # A non-expired cookie with the same user would pass
        valid_payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        valid_cookie = create_signed_cookie(valid_payload, SECRET)
        assert verify_signed_cookie(valid_cookie, SECRET) is not None

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
        assert verified["exp"] == int(time.time()) + 1
        assert isinstance(verified, dict)

    def test_rejects_malformed_no_dot(self):
        """Cookies without dot separator are rejected."""
        assert verify_signed_cookie("nocookie", SECRET) is None
        assert verify_signed_cookie("nocookie", SECRET) is None  # deterministic
        # Valid cookie with a dot works for contrast
        payload = {"github_username": "x", "exp": int(time.time()) + 3600}
        assert verify_signed_cookie(create_signed_cookie(payload, SECRET), SECRET) is not None

    def test_rejects_malformed_multiple_dots(self):
        """Cookies with multiple dots in wrong places are rejected."""
        assert verify_signed_cookie("not.a.valid.cookie", SECRET) is None
        # Two dots also rejected (uses rsplit so payload would be "not.a.valid", sig "cookie")
        assert verify_signed_cookie("a.b.c", SECRET) is None
        assert verify_signed_cookie("...", SECRET) is None

    def test_rejects_empty(self):
        """Empty cookies are rejected."""
        assert verify_signed_cookie("", SECRET) is None
        # None is also rejected
        assert verify_signed_cookie(None, SECRET) is None
        # Whitespace-only is also rejected (no dot separator)
        assert verify_signed_cookie("   ", SECRET) is None

    def test_rejects_invalid_base64(self):
        """Cookies with invalid base64 are rejected."""
        # Create cookie with invalid base64 payload
        invalid_cookie = "not-valid-base64!@#$.signature"
        assert verify_signed_cookie(invalid_cookie, SECRET) is None
        # Even if the signature matches the garbage payload, base64 decode fails
        garbage = "not-valid-base64!@#$"
        sig = hmac.new(SECRET.encode(), garbage.encode(), hashlib.sha256).hexdigest()
        assert verify_signed_cookie(f"{garbage}.{sig}", SECRET) is None

    def test_rejects_invalid_json(self):
        """Cookies with invalid JSON payload are rejected."""
        # Create cookie with valid base64 but invalid JSON
        invalid_json = base64.urlsafe_b64encode(b"not json").decode()
        signature = hmac.new(SECRET.encode(), invalid_json.encode(), hashlib.sha256).hexdigest()
        invalid_cookie = f"{invalid_json}.{signature}"

        assert verify_signed_cookie(invalid_cookie, SECRET) is None
        # Valid JSON in base64 works for contrast
        valid_json = base64.urlsafe_b64encode(
            json.dumps({"github_username": "test", "exp": int(time.time()) + 3600}).encode()
        ).decode()
        valid_sig = hmac.new(SECRET.encode(), valid_json.encode(), hashlib.sha256).hexdigest()
        assert verify_signed_cookie(f"{valid_json}.{valid_sig}", SECRET) is not None

    def test_rejects_missing_exp(self):
        """Cookies without exp field are rejected (default to 0, always expired)."""
        payload = {"github_username": "testuser"}  # No exp field
        cookie = create_signed_cookie(payload, SECRET)

        # exp defaults to 0, which is always < current time
        assert verify_signed_cookie(cookie, SECRET) is None
        # Adding exp field makes the same user valid
        payload_with_exp = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        valid_cookie = create_signed_cookie(payload_with_exp, SECRET)
        assert verify_signed_cookie(valid_cookie, SECRET) is not None

    def test_signature_changes_with_payload(self):
        """Different payloads produce different signatures."""
        payload1 = {"github_username": "user1", "exp": int(time.time()) + 3600}
        payload2 = {"github_username": "user2", "exp": int(time.time()) + 3600}

        cookie1 = create_signed_cookie(payload1, SECRET)
        cookie2 = create_signed_cookie(payload2, SECRET)

        sig1 = cookie1.split(".")[-1]
        sig2 = cookie2.split(".")[-1]

        assert sig1 != sig2
        # Payloads are also different
        assert cookie1.split(".")[0] != cookie2.split(".")[0]
        # Both are independently valid
        assert verify_signed_cookie(cookie1, SECRET) is not None
        assert verify_signed_cookie(cookie2, SECRET) is not None

    def test_signature_changes_with_secret(self):
        """Same payload with different secrets produces different signatures."""
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}

        cookie1 = create_signed_cookie(payload, "secret1")
        cookie2 = create_signed_cookie(payload, "secret2")

        sig1 = cookie1.split(".")[-1]
        sig2 = cookie2.split(".")[-1]

        assert sig1 != sig2
        # Payloads are the same (same data, different signing key)
        assert cookie1.split(".")[0] == cookie2.split(".")[0]
        # Cross-verification fails: cookie1 doesn't verify with secret2
        assert verify_signed_cookie(cookie1, "secret2") is None
        assert verify_signed_cookie(cookie2, "secret1") is None

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
        # Signature with completely wrong first byte is still rejected (not short-circuited)
        parts = cookie.split(".")
        wrong_first_byte = ("f" if parts[1][0] == "0" else "0") + parts[1][1:]
        assert verify_signed_cookie(f"{parts[0]}.{wrong_first_byte}", SECRET) is None
        # Signature with wrong last byte is also rejected
        wrong_last_byte = parts[1][:-1] + ("f" if parts[1][-1] == "0" else "0")
        assert verify_signed_cookie(f"{parts[0]}.{wrong_last_byte}", SECRET) is None


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestSessionEdgeCases:
    """Edge case tests for session handling."""

    @freeze_time("2026-01-01 12:00:00")
    def test_session_expiry_boundary(self):
        """Cookie expiring exactly at current time is still valid (exp < check)."""
        now = int(time.time())
        payload = {
            "github_username": "testuser",
            "exp": now,  # Expires exactly now
        }
        cookie = create_signed_cookie(payload, SECRET)
        # exp < time.time() check means exp==now is still valid (not less than)
        # This is acceptable - the session expires within the same second
        verified = verify_signed_cookie(cookie, SECRET)
        assert verified is not None
        assert verified["exp"] == now
        # One second earlier would be expired
        expired_payload = {"github_username": "testuser", "exp": now - 1}
        expired_cookie = create_signed_cookie(expired_payload, SECRET)
        assert verify_signed_cookie(expired_cookie, SECRET) is None

    @freeze_time("2026-01-01 12:00:00")
    def test_session_very_old_timestamp(self):
        """Very old exp timestamp is rejected."""
        payload = {
            "github_username": "testuser",
            "exp": 0,  # Unix epoch
        }
        cookie = create_signed_cookie(payload, SECRET)
        assert verify_signed_cookie(cookie, SECRET) is None
        # The cookie itself is well-formed (signature is valid), just expired
        parts = cookie.split(".")
        assert len(parts) == 2
        expected_sig = hmac.new(SECRET.encode(), parts[0].encode(), hashlib.sha256).hexdigest()
        assert hmac.compare_digest(parts[1], expected_sig)

    @freeze_time("2026-01-01 12:00:00")
    def test_session_future_timestamp(self):
        """Far future exp timestamp is accepted (no max check)."""
        future_exp = int(time.time()) + 86400 * 365 * 10  # 10 years
        payload = {
            "github_username": "testuser",
            "exp": future_exp,
        }
        cookie = create_signed_cookie(payload, SECRET)
        verified = verify_signed_cookie(cookie, SECRET)
        assert verified is not None
        assert verified["github_username"] == "testuser"
        assert verified["exp"] == future_exp

    @freeze_time("2026-01-01 12:00:00")
    def test_session_empty_avatar(self):
        """Empty avatar URL is preserved."""
        payload = {
            "github_username": "testuser",
            "avatar_url": "",
            "exp": int(time.time()) + 3600,
        }
        cookie = create_signed_cookie(payload, SECRET)
        verified = verify_signed_cookie(cookie, SECRET)
        assert verified["avatar_url"] == ""
        assert verified is not None
        assert "avatar_url" in verified

    @freeze_time("2026-01-01 12:00:00")
    def test_session_none_avatar(self):
        """None avatar URL is preserved as null."""
        payload = {
            "github_username": "testuser",
            "avatar_url": None,
            "exp": int(time.time()) + 3600,
        }
        cookie = create_signed_cookie(payload, SECRET)
        verified = verify_signed_cookie(cookie, SECRET)
        assert verified["avatar_url"] is None
        assert verified is not None
        assert "avatar_url" in verified

    @freeze_time("2026-01-01 12:00:00")
    def test_session_special_chars_username(self):
        """Username with special characters is preserved."""
        payload = {
            "github_username": "user-name_123",
            "exp": int(time.time()) + 3600,
        }
        cookie = create_signed_cookie(payload, SECRET)
        verified = verify_signed_cookie(cookie, SECRET)
        assert verified["github_username"] == "user-name_123"
        assert verified is not None
        assert isinstance(verified["github_username"], str)

    @freeze_time("2026-01-01 12:00:00")
    def test_session_unicode_username(self):
        """Unicode characters in payload are handled."""
        payload = {
            "github_username": "test",
            "display_name": "Test User \u2603",  # Snowman
            "exp": int(time.time()) + 3600,
        }
        cookie = create_signed_cookie(payload, SECRET)
        verified = verify_signed_cookie(cookie, SECRET)
        assert verified["display_name"] == "Test User \u2603"
        assert verified["github_username"] == "test"
        assert "\u2603" in verified["display_name"]

    def test_signature_length(self):
        """Signature is valid SHA256 hex (64 characters)."""
        payload = {"github_username": "testuser", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)
        signature = cookie.split(".")[-1]
        assert len(signature) == 64
        # Should be valid hex
        int(signature, 16)
        # All chars should be hex digits
        assert all(c in "0123456789abcdef" for c in signature)
        # Cookie has exactly one dot separator
        assert cookie.count(".") == 1

    @freeze_time("2026-01-01 12:00:00")
    def test_session_very_large_payload(self):
        """Large payload is handled (within limits)."""
        payload = {
            "github_username": "testuser",
            "extra_data": "x" * 1000,  # 1KB of data
            "exp": int(time.time()) + 3600,
        }
        cookie = create_signed_cookie(payload, SECRET)
        verified = verify_signed_cookie(cookie, SECRET)
        assert verified is not None
        assert len(verified["extra_data"]) == 1000
        assert verified["extra_data"] == "x" * 1000
        assert verified["github_username"] == "testuser"
        # Signature is still exactly 64 hex chars regardless of payload size
        assert len(cookie.split(".")[-1]) == 64
