# tests/unit/test_auth.py
"""Unit tests for src/auth.py — session cookie management with HMAC signing."""

import time

from freezegun import freeze_time

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
        result = parse_cookie_value("session=abc123; foo=bar", "session")
        assert result == "abc123"
        assert isinstance(result, str)
        # Other cookie is not returned
        assert result != "bar"

    def test_extracts_middle_cookie(self):
        """Extracts a cookie that is not first in the header."""
        result = parse_cookie_value("a=1; target=value; b=2", "target")
        assert result == "value"
        # Neighboring cookies are not confused
        assert parse_cookie_value("a=1; target=value; b=2", "a") == "1"
        assert parse_cookie_value("a=1; target=value; b=2", "b") == "2"

    def test_returns_none_for_missing_cookie(self):
        """Returns None when the named cookie is not present."""
        result = parse_cookie_value("foo=bar; baz=qux", "session")
        assert result is None
        # But existing cookies in that header are still accessible
        assert parse_cookie_value("foo=bar; baz=qux", "foo") == "bar"

    def test_returns_none_for_empty_header(self):
        """Returns None for empty or None cookie header."""
        assert parse_cookie_value("", "session") is None
        assert parse_cookie_value(None, "session") is None
        # Also None for any cookie name when header is empty
        assert parse_cookie_value("", "foo") is None
        assert parse_cookie_value(None, "foo") is None

    def test_handles_cookie_with_equals_in_value(self):
        """Handles cookie values that contain '=' characters."""
        result = parse_cookie_value("session=abc=def=ghi", "session")
        assert result == "abc=def=ghi"
        # The full value including extra = signs is preserved
        assert result.count("=") == 2
        assert result.startswith("abc")

    def test_handles_whitespace_around_cookies(self):
        """Handles whitespace around cookie pairs (strip removes trailing space)."""
        # split(";") → ["  session=abc ", "  foo=bar  "], strip() → "session=abc"
        result = parse_cookie_value("  session=abc ;  foo=bar  ", "session")
        assert result == "abc"
        # Whitespace-padded second cookie is also accessible
        assert parse_cookie_value("  session=abc ;  foo=bar  ", "foo") == "bar"


# =============================================================================
# create_signed_cookie / verify_signed_cookie
# =============================================================================


class TestSignedCookieRoundtrip:
    """Tests for create_signed_cookie() and verify_signed_cookie()."""

    @freeze_time("2026-01-01 12:00:00")
    def test_roundtrip_verify(self):
        """Created cookie can be verified with the same secret."""
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)
        result = verify_signed_cookie(cookie, SECRET)
        assert result is not None
        assert result["user"] == "test"
        assert result["exp"] == payload["exp"]
        assert isinstance(result, dict)
        # Wrong secret fails
        assert verify_signed_cookie(cookie, "wrong-secret-padded-to-32chars") is None

    def test_deterministic_output(self):
        """Same payload and secret produce the same cookie."""
        payload = {"user": "test", "exp": 999999999}
        cookie1 = create_signed_cookie(payload, SECRET)
        cookie2 = create_signed_cookie(payload, SECRET)
        assert cookie1 == cookie2
        assert isinstance(cookie1, str)
        assert "." in cookie1

    def test_different_secrets_produce_different_signatures(self):
        """Different secrets produce different cookie values."""
        payload = {"user": "test", "exp": 999999999}
        cookie1 = create_signed_cookie(payload, "secret-one-abcdefghijklmnop")
        cookie2 = create_signed_cookie(payload, "secret-two-abcdefghijklmnop")
        assert cookie1 != cookie2
        # The payload portion (before the dot) is the same since same payload
        assert cookie1.split(".")[0] == cookie2.split(".")[0]
        # But the signatures differ
        assert cookie1.split(".")[1] != cookie2.split(".")[1]

    def test_cookie_format_is_base64_dot_signature(self):
        """Cookie format is base64(payload).signature."""
        payload = {"user": "test", "exp": 999999999}
        cookie = create_signed_cookie(payload, SECRET)
        parts = cookie.split(".")
        assert len(parts) == 2
        assert len(parts[1]) == 64  # SHA-256 hex digest
        # Signature is hex characters only
        assert all(c in "0123456789abcdef" for c in parts[1])
        # Payload part is valid base64
        import base64

        decoded = base64.urlsafe_b64decode(parts[0])
        assert b'"user"' in decoded


class TestVerifySignedCookie:
    """Tests for verify_signed_cookie() edge cases."""

    @freeze_time("2026-01-01 12:00:00")
    def test_rejects_tampered_payload(self):
        """Rejects cookie with tampered payload bytes."""
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)
        # Tamper with the base64 payload
        tampered = "X" + cookie[1:]
        assert verify_signed_cookie(tampered, SECRET) is None
        # Original untampered cookie still verifies
        assert verify_signed_cookie(cookie, SECRET) is not None
        assert verify_signed_cookie(cookie, SECRET)["user"] == "test"

    @freeze_time("2026-01-01 12:00:00")
    def test_rejects_tampered_signature(self):
        """Rejects cookie with modified signature."""
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)
        payload_b64, sig = cookie.rsplit(".", 1)
        # Flip a character in the signature
        bad_sig = ("a" if sig[0] != "a" else "b") + sig[1:]
        tampered = f"{payload_b64}.{bad_sig}"
        assert verify_signed_cookie(tampered, SECRET) is None
        # The bad signature is indeed different from the original
        assert bad_sig != sig
        # Original cookie still works
        assert verify_signed_cookie(cookie, SECRET) is not None

    @freeze_time("2026-01-01 12:00:00")
    def test_rejects_expired_session(self):
        """Rejects cookie with expired timestamp."""
        payload = {"user": "test", "exp": int(time.time()) - 3600}
        cookie = create_signed_cookie(payload, SECRET)
        assert verify_signed_cookie(cookie, SECRET) is None
        # A non-expired cookie with the same user is accepted
        valid_payload = {"user": "test", "exp": int(time.time()) + 3600}
        valid_cookie = create_signed_cookie(valid_payload, SECRET)
        assert verify_signed_cookie(valid_cookie, SECRET) is not None
        assert verify_signed_cookie(valid_cookie, SECRET)["user"] == "test"

    @freeze_time("2026-01-01 12:00:00")
    def test_rejects_wrong_secret(self):
        """Rejects cookie verified with a different secret."""
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, "correct-secret-abcdefghijk")
        assert verify_signed_cookie(cookie, "wrong-secret-abcdefghijklm") is None
        # But the correct secret still works
        result = verify_signed_cookie(cookie, "correct-secret-abcdefghijk")
        assert result is not None
        assert result["user"] == "test"

    def test_rejects_none_cookie(self):
        """Returns None for None cookie value."""
        assert verify_signed_cookie(None, SECRET) is None
        assert verify_signed_cookie(None, "any-secret-at-all-32chars") is None

    def test_rejects_cookie_without_dot(self):
        """Returns None for cookie missing the payload.signature separator."""
        assert verify_signed_cookie("nodothere", SECRET) is None
        assert verify_signed_cookie("alsonomiddledot", SECRET) is None
        # A cookie WITH a dot but invalid content also fails
        assert verify_signed_cookie("invalid.invalid", SECRET) is None

    def test_rejects_empty_string(self):
        """Returns None for empty string."""
        assert verify_signed_cookie("", SECRET) is None
        # Whitespace-only is also not a valid cookie
        assert verify_signed_cookie("   ", SECRET) is None

    @freeze_time("2026-01-01 12:00:00")
    def test_grace_period_allows_recent_expiry(self):
        """Grace period allows recently-expired sessions."""
        # Expired 3 seconds ago, grace period is 5 seconds
        payload = {"user": "test", "exp": int(time.time()) - 3}
        cookie = create_signed_cookie(payload, SECRET)
        result = verify_signed_cookie(cookie, SECRET, grace_seconds=5)
        assert result is not None
        assert result["user"] == "test"
        # Without grace period (0), the same cookie is rejected
        assert verify_signed_cookie(cookie, SECRET, grace_seconds=0) is None
        # Expired beyond grace period is also rejected
        old_payload = {"user": "test", "exp": int(time.time()) - 10}
        old_cookie = create_signed_cookie(old_payload, SECRET)
        assert verify_signed_cookie(old_cookie, SECRET, grace_seconds=5) is None


# =============================================================================
# create_session_cookie
# =============================================================================


class TestCreateSessionCookie:
    """Tests for create_session_cookie()."""

    @freeze_time("2026-01-01 12:00:00")
    def test_contains_expected_fields(self):
        """Session cookie payload contains github_username, github_id, avatar_url, exp."""
        cookie = create_session_cookie("testuser", 12345, "https://avatar.url", SECRET)
        payload = verify_signed_cookie(cookie, SECRET)
        assert payload is not None
        assert payload["github_username"] == "testuser"
        assert payload["github_id"] == 12345
        assert payload["avatar_url"] == "https://avatar.url"
        assert "exp" in payload
        # Exactly 4 fields in the payload
        assert len(payload) == 4
        assert isinstance(payload["exp"], int)

    @freeze_time("2026-01-01 12:00:00")
    def test_expiry_is_in_the_future(self):
        """Session expiry is set in the future."""
        cookie = create_session_cookie("testuser", 12345, None, SECRET)
        payload = verify_signed_cookie(cookie, SECRET)
        assert payload["exp"] > time.time()
        # Default TTL is SESSION_TTL_SECONDS (7 days)
        assert payload["exp"] == int(time.time()) + 7 * 24 * 60 * 60
        assert payload["github_username"] == "testuser"

    def test_avatar_url_none_handled(self):
        """Handles None avatar_url without error."""
        cookie = create_session_cookie("testuser", 12345, None, SECRET)
        payload = verify_signed_cookie(cookie, SECRET)
        assert payload["avatar_url"] is None
        assert payload is not None
        assert payload["github_username"] == "testuser"
        assert payload["github_id"] == 12345

    def test_custom_ttl(self):
        """Respects custom TTL."""
        from unittest.mock import patch

        frozen_time = 1700000000.0
        with patch("src.auth.time.time", return_value=frozen_time):
            cookie = create_session_cookie("testuser", 12345, None, SECRET, ttl_seconds=60)
            payload = verify_signed_cookie(cookie, SECRET)
        # Expiry should be exactly frozen_time + 60
        assert payload["exp"] == int(frozen_time) + 60
        assert payload["github_username"] == "testuser"
        # A different TTL produces a different expiry
        with patch("src.auth.time.time", return_value=frozen_time):
            cookie2 = create_session_cookie("testuser", 12345, None, SECRET, ttl_seconds=120)
            payload2 = verify_signed_cookie(cookie2, SECRET)
        assert payload2["exp"] == int(frozen_time) + 120
        assert payload2["exp"] != payload["exp"]


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
        assert result["github_id"] == 12345
        assert "exp" in result
        assert isinstance(result, dict)

    def test_returns_none_for_no_session_cookie(self):
        """Returns None when no session cookie exists."""
        result = get_session_from_cookies("foo=bar; baz=qux", SECRET)
        assert result is None
        # Even with many cookies, missing 'session' returns None
        assert get_session_from_cookies("a=1; b=2; c=3", SECRET) is None

    def test_returns_none_for_invalid_session(self):
        """Returns None for session with invalid signature."""
        result = get_session_from_cookies("session=invalid.cookie", SECRET)
        assert result is None
        # Also fails for gibberish value
        assert get_session_from_cookies("session=totalgarbage", SECRET) is None

    def test_returns_none_for_empty_header(self):
        """Returns None for empty cookie header."""
        result = get_session_from_cookies("", SECRET)
        assert result is None
        # Confirm a valid session in the same format would work
        cookie_value = create_session_cookie("testuser", 99, None, SECRET)
        valid_result = get_session_from_cookies(f"session={cookie_value}", SECRET)
        assert valid_result is not None
        assert valid_result["github_username"] == "testuser"


# =============================================================================
# Cookie Header Builders
# =============================================================================


class TestBuildSessionCookieHeader:
    """Tests for build_session_cookie_header()."""

    def test_returns_set_cookie_string(self):
        """Returns a valid Set-Cookie header string."""
        header = build_session_cookie_header("cookie-value")
        assert header.startswith("session=cookie-value;")
        assert isinstance(header, str)
        assert "session=" in header

    def test_contains_security_attributes(self):
        """Contains HttpOnly, Secure, SameSite, Path."""
        header = build_session_cookie_header("val")
        assert "HttpOnly" in header
        assert "Secure" in header
        assert "SameSite=Lax" in header
        assert "Path=/" in header
        # SameSite is not None or Strict (Lax is the intended value)
        assert "SameSite=None" not in header
        assert "SameSite=Strict" not in header

    def test_contains_max_age(self):
        """Contains Max-Age directive."""
        header = build_session_cookie_header("val")
        assert "Max-Age=" in header
        # Default Max-Age matches SESSION_TTL_SECONDS (7 days = 604800)
        assert "Max-Age=604800" in header
        # Max-Age is not 0 (that's for clearing)
        assert "Max-Age=0" not in header


class TestBuildClearSessionCookieHeader:
    """Tests for build_clear_session_cookie_header()."""

    def test_sets_max_age_zero(self):
        """Clear cookie has Max-Age=0."""
        header = build_clear_session_cookie_header()
        assert "Max-Age=0" in header
        assert "HttpOnly" in header
        assert "Secure" in header
        assert "Path=/" in header

    def test_clears_session_cookie_name(self):
        """Clear cookie targets the session cookie."""
        header = build_clear_session_cookie_header()
        assert header.startswith("session=;")
        # Value is empty between = and ;
        assert "session=;" in header
        assert "SameSite=Lax" in header


class TestBuildOauthStateCookieHeader:
    """Tests for build_oauth_state_cookie_header()."""

    def test_returns_set_cookie_string(self):
        """Returns a valid Set-Cookie header for oauth_state."""
        header = build_oauth_state_cookie_header("state-abc")
        assert "oauth_state=state-abc" in header
        assert "HttpOnly" in header
        assert "Secure" in header
        assert "Path=/" in header

    def test_has_short_max_age(self):
        """OAuth state cookie has a short TTL (600s)."""
        header = build_oauth_state_cookie_header("state-abc")
        assert "Max-Age=600" in header
        # Not the session TTL (604800) — OAuth state is short-lived
        assert "Max-Age=604800" not in header
        assert "SameSite=Lax" in header


class TestBuildClearOauthStateCookieHeader:
    """Tests for build_clear_oauth_state_cookie_header()."""

    def test_sets_max_age_zero(self):
        """Clear oauth state has Max-Age=0."""
        header = build_clear_oauth_state_cookie_header()
        assert "Max-Age=0" in header
        assert "HttpOnly" in header
        assert "Secure" in header

    def test_clears_oauth_state_cookie_name(self):
        """Clear cookie targets the oauth_state cookie."""
        header = build_clear_oauth_state_cookie_header()
        assert header.startswith("oauth_state=;")
        assert "oauth_state=;" in header
        assert "Path=/" in header
        assert "SameSite=Lax" in header
