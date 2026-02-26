# tests/unit/test_auth.py
"""Unit tests for src/auth.py — session cookie management with HMAC signing."""

import time

from src.auth import (
    build_clear_oauth_state_cookie_header,
    build_clear_session_cookie_header,
    build_oauth_state_cookie_header,
    build_session_cookie_header,
    create_session_cookie,
    create_signed_cookie,
    get_session_from_cookies,
    parse_cookie_value,
    verify_signed_cookie,
)

SECRET = "test-secret-key-for-testing-only-32chars"  # pragma: allowlist secret


# =============================================================================
# parse_cookie_value
# =============================================================================


class TestParseCookieValue:
    """Tests for parse_cookie_value()."""

    def test_extracts_cookie_from_header(self):
        """Extracts a named cookie from a Cookie header."""
        assert parse_cookie_value("session=abc123; foo=bar", "session") == "abc123"

    def test_extracts_middle_cookie(self):
        """Extracts a cookie that is not first in the header."""
        assert parse_cookie_value("a=1; target=value; b=2", "target") == "value"

    def test_returns_none_for_missing_cookie(self):
        """Returns None when the named cookie is not present."""
        assert parse_cookie_value("foo=bar; baz=qux", "session") is None

    def test_returns_none_for_empty_header(self):
        """Returns None for empty or None cookie header."""
        assert parse_cookie_value("", "session") is None
        assert parse_cookie_value(None, "session") is None

    def test_handles_cookie_with_equals_in_value(self):
        """Handles cookie values that contain '=' characters."""
        result = parse_cookie_value("session=abc=def=ghi", "session")
        assert result == "abc=def=ghi"

    def test_handles_whitespace_around_cookies(self):
        """Handles whitespace around cookie pairs (strip removes trailing space)."""
        # split(";") → ["  session=abc ", "  foo=bar  "], strip() → "session=abc"
        assert parse_cookie_value("  session=abc ;  foo=bar  ", "session") == "abc"


# =============================================================================
# create_signed_cookie / verify_signed_cookie
# =============================================================================


class TestSignedCookieRoundtrip:
    """Tests for create_signed_cookie() and verify_signed_cookie()."""

    def test_roundtrip_verify(self):
        """Created cookie can be verified with the same secret."""
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)
        result = verify_signed_cookie(cookie, SECRET)
        assert result is not None
        assert result["user"] == "test"

    def test_deterministic_output(self):
        """Same payload and secret produce the same cookie."""
        payload = {"user": "test", "exp": 999999999}
        cookie1 = create_signed_cookie(payload, SECRET)
        cookie2 = create_signed_cookie(payload, SECRET)
        assert cookie1 == cookie2

    def test_different_secrets_produce_different_signatures(self):
        """Different secrets produce different cookie values."""
        payload = {"user": "test", "exp": 999999999}
        cookie1 = create_signed_cookie(payload, "secret-one-abcdefghijklmnop")
        cookie2 = create_signed_cookie(payload, "secret-two-abcdefghijklmnop")
        assert cookie1 != cookie2

    def test_cookie_format_is_base64_dot_signature(self):
        """Cookie format is base64(payload).signature."""
        payload = {"user": "test", "exp": 999999999}
        cookie = create_signed_cookie(payload, SECRET)
        parts = cookie.split(".")
        assert len(parts) == 2
        assert len(parts[1]) == 64  # SHA-256 hex digest


class TestVerifySignedCookie:
    """Tests for verify_signed_cookie() edge cases."""

    def test_rejects_tampered_payload(self):
        """Rejects cookie with tampered payload bytes."""
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)
        # Tamper with the base64 payload
        tampered = "X" + cookie[1:]
        assert verify_signed_cookie(tampered, SECRET) is None

    def test_rejects_tampered_signature(self):
        """Rejects cookie with modified signature."""
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)
        payload_b64, sig = cookie.rsplit(".", 1)
        # Flip a character in the signature
        bad_sig = ("a" if sig[0] != "a" else "b") + sig[1:]
        assert verify_signed_cookie(f"{payload_b64}.{bad_sig}", SECRET) is None

    def test_rejects_expired_session(self):
        """Rejects cookie with expired timestamp."""
        payload = {"user": "test", "exp": int(time.time()) - 3600}
        cookie = create_signed_cookie(payload, SECRET)
        assert verify_signed_cookie(cookie, SECRET) is None

    def test_rejects_wrong_secret(self):
        """Rejects cookie verified with a different secret."""
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, "correct-secret-abcdefghijk")
        assert verify_signed_cookie(cookie, "wrong-secret-abcdefghijklm") is None

    def test_rejects_none_cookie(self):
        """Returns None for None cookie value."""
        assert verify_signed_cookie(None, SECRET) is None

    def test_rejects_cookie_without_dot(self):
        """Returns None for cookie missing the payload.signature separator."""
        assert verify_signed_cookie("nodothere", SECRET) is None

    def test_rejects_empty_string(self):
        """Returns None for empty string."""
        assert verify_signed_cookie("", SECRET) is None

    def test_grace_period_allows_recent_expiry(self):
        """Grace period allows recently-expired sessions."""
        # Expired 3 seconds ago, grace period is 5 seconds
        payload = {"user": "test", "exp": int(time.time()) - 3}
        cookie = create_signed_cookie(payload, SECRET)
        result = verify_signed_cookie(cookie, SECRET, grace_seconds=5)
        assert result is not None
        assert result["user"] == "test"


# =============================================================================
# create_session_cookie
# =============================================================================


class TestCreateSessionCookie:
    """Tests for create_session_cookie()."""

    def test_contains_expected_fields(self):
        """Session cookie payload contains github_username, github_id, avatar_url, exp."""
        cookie = create_session_cookie("testuser", 12345, "https://avatar.url", SECRET)
        payload = verify_signed_cookie(cookie, SECRET)
        assert payload is not None
        assert payload["github_username"] == "testuser"
        assert payload["github_id"] == 12345
        assert payload["avatar_url"] == "https://avatar.url"
        assert "exp" in payload

    def test_expiry_is_in_the_future(self):
        """Session expiry is set in the future."""
        cookie = create_session_cookie("testuser", 12345, None, SECRET)
        payload = verify_signed_cookie(cookie, SECRET)
        assert payload["exp"] > time.time()

    def test_avatar_url_none_handled(self):
        """Handles None avatar_url without error."""
        cookie = create_session_cookie("testuser", 12345, None, SECRET)
        payload = verify_signed_cookie(cookie, SECRET)
        assert payload["avatar_url"] is None

    def test_custom_ttl(self):
        """Respects custom TTL."""
        cookie = create_session_cookie("testuser", 12345, None, SECRET, ttl_seconds=60)
        payload = verify_signed_cookie(cookie, SECRET)
        # Expiry should be within ~60s of now
        assert payload["exp"] <= int(time.time()) + 61
        assert payload["exp"] >= int(time.time()) + 59


# =============================================================================
# get_session_from_cookies
# =============================================================================


class TestGetSessionFromCookies:
    """Tests for get_session_from_cookies()."""

    def test_extracts_valid_session(self):
        """Extracts and verifies a valid session from Cookie header."""
        cookie_value = create_session_cookie("testuser", 12345, None, SECRET)
        header = f"session={cookie_value}; other=foo"
        result = get_session_from_cookies(header, SECRET)
        assert result is not None
        assert result["github_username"] == "testuser"

    def test_returns_none_for_no_session_cookie(self):
        """Returns None when no session cookie exists."""
        assert get_session_from_cookies("foo=bar; baz=qux", SECRET) is None

    def test_returns_none_for_invalid_session(self):
        """Returns None for session with invalid signature."""
        assert get_session_from_cookies("session=invalid.cookie", SECRET) is None

    def test_returns_none_for_empty_header(self):
        """Returns None for empty cookie header."""
        assert get_session_from_cookies("", SECRET) is None


# =============================================================================
# Cookie Header Builders
# =============================================================================


class TestBuildSessionCookieHeader:
    """Tests for build_session_cookie_header()."""

    def test_returns_set_cookie_string(self):
        """Returns a valid Set-Cookie header string."""
        header = build_session_cookie_header("cookie-value")
        assert header.startswith("session=cookie-value;")

    def test_contains_security_attributes(self):
        """Contains HttpOnly, Secure, SameSite, Path."""
        header = build_session_cookie_header("val")
        assert "HttpOnly" in header
        assert "Secure" in header
        assert "SameSite=Lax" in header
        assert "Path=/" in header

    def test_contains_max_age(self):
        """Contains Max-Age directive."""
        header = build_session_cookie_header("val")
        assert "Max-Age=" in header


class TestBuildClearSessionCookieHeader:
    """Tests for build_clear_session_cookie_header()."""

    def test_sets_max_age_zero(self):
        """Clear cookie has Max-Age=0."""
        header = build_clear_session_cookie_header()
        assert "Max-Age=0" in header

    def test_clears_session_cookie_name(self):
        """Clear cookie targets the session cookie."""
        header = build_clear_session_cookie_header()
        assert header.startswith("session=;")


class TestBuildOauthStateCookieHeader:
    """Tests for build_oauth_state_cookie_header()."""

    def test_returns_set_cookie_string(self):
        """Returns a valid Set-Cookie header for oauth_state."""
        header = build_oauth_state_cookie_header("state-abc")
        assert "oauth_state=state-abc" in header

    def test_has_short_max_age(self):
        """OAuth state cookie has a short TTL (600s)."""
        header = build_oauth_state_cookie_header("state-abc")
        assert "Max-Age=600" in header


class TestBuildClearOauthStateCookieHeader:
    """Tests for build_clear_oauth_state_cookie_header()."""

    def test_sets_max_age_zero(self):
        """Clear oauth state has Max-Age=0."""
        header = build_clear_oauth_state_cookie_header()
        assert "Max-Age=0" in header

    def test_clears_oauth_state_cookie_name(self):
        """Clear cookie targets the oauth_state cookie."""
        header = build_clear_oauth_state_cookie_header()
        assert header.startswith("oauth_state=;")
