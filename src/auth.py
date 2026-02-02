# src/auth.py
"""Authentication utilities for Planet CF.

Session cookie management with HMAC signing for stateless authentication.
These are pure functions with no dependencies on the Worker class.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from utils import log_op, truncate_error

# =============================================================================
# Constants
# =============================================================================

# Session configuration
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
SESSION_GRACE_SECONDS = 5  # Clock skew grace period (reduced from 60s for security)


# =============================================================================
# Cookie Parsing
# =============================================================================


def parse_cookie_value(cookies_header: str, cookie_name: str) -> str | None:
    """Extract a cookie value from a Cookie header string.

    Args:
        cookies_header: The raw Cookie header value (e.g., "session=abc; foo=bar")
        cookie_name: The name of the cookie to extract

    Returns:
        The cookie value, or None if not found.
    """
    if not cookies_header:
        return None

    prefix = f"{cookie_name}="
    for cookie in cookies_header.split(";"):
        cookie = cookie.strip()
        if cookie.startswith(prefix):
            return cookie[len(prefix) :]
    return None


# =============================================================================
# Cookie Signing
# =============================================================================


def create_signed_cookie(payload: dict[str, Any], secret: str) -> str:
    """Create an HMAC-signed cookie.

    Format: base64(json_payload).signature

    Args:
        payload: The session data to encode (will be JSON serialized)
        secret: The HMAC signing secret

    Returns:
        The signed cookie value (base64 payload + signature)
    """
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

    signature = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()

    return f"{payload_b64}.{signature}"


def verify_signed_cookie(
    cookie_value: str | None,
    secret: str,
    grace_seconds: int = SESSION_GRACE_SECONDS,
) -> dict[str, Any] | None:
    """Verify an HMAC-signed cookie and return the payload.

    Cookie format: base64(json_payload).signature

    Args:
        cookie_value: The raw cookie value to verify
        secret: The HMAC signing secret
        grace_seconds: Clock skew tolerance for expiration check

    Returns:
        The decoded payload dict if valid, None otherwise.
    """
    if not cookie_value or "." not in cookie_value:
        return None

    try:
        payload_b64, signature = cookie_value.rsplit(".", 1)

        # Verify signature
        expected_sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Decode payload
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        # Check expiration with grace period for clock skew
        if payload.get("exp", 0) < time.time() - grace_seconds:
            return None

        return payload
    except Exception as e:
        log_op(
            "session_verify_failed",
            error_type=type(e).__name__,
            error=truncate_error(e),
        )
        return None


# =============================================================================
# Session Cookie Helpers
# =============================================================================


def create_session_cookie(
    github_username: str,
    github_id: int,
    avatar_url: str | None,
    secret: str,
    ttl_seconds: int = SESSION_TTL_SECONDS,
) -> str:
    """Create a signed session cookie for an authenticated user.

    Args:
        github_username: The user's GitHub username
        github_id: The user's GitHub ID
        avatar_url: The user's GitHub avatar URL
        secret: The HMAC signing secret
        ttl_seconds: Session lifetime in seconds

    Returns:
        The signed session cookie value.
    """
    payload = {
        "github_username": github_username,
        "github_id": github_id,
        "avatar_url": avatar_url,
        "exp": int(time.time()) + ttl_seconds,
    }
    return create_signed_cookie(payload, secret)


def get_session_from_cookies(cookies_header: str, secret: str) -> dict[str, Any] | None:
    """Extract and verify a session from a Cookie header.

    Args:
        cookies_header: The raw Cookie header value
        secret: The HMAC signing secret

    Returns:
        The session payload if valid, None otherwise.
    """
    session_cookie = parse_cookie_value(cookies_header, "session")
    if not session_cookie:
        return None
    return verify_signed_cookie(session_cookie, secret)


# =============================================================================
# Cookie Header Builders
# =============================================================================

# Standard cookie security attributes (HttpOnly, Secure, SameSite=Lax)
COOKIE_SECURITY_ATTRS = "HttpOnly; Secure; SameSite=Lax; Path=/"


def _build_cookie_header(name: str, value: str, max_age: int) -> str:
    """Build a Set-Cookie header with standard security attributes.

    Args:
        name: Cookie name
        value: Cookie value
        max_age: Cookie lifetime in seconds (0 to expire immediately)

    Returns:
        The complete Set-Cookie header value.
    """
    return f"{name}={value}; {COOKIE_SECURITY_ATTRS}; Max-Age={max_age}"


def build_session_cookie_header(cookie_value: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """Build the Set-Cookie header for a session cookie."""
    return _build_cookie_header("session", cookie_value, ttl_seconds)


def build_clear_session_cookie_header() -> str:
    """Build the Set-Cookie header to clear the session cookie."""
    return _build_cookie_header("session", "", 0)


def build_oauth_state_cookie_header(state: str) -> str:
    """Build the Set-Cookie header for an OAuth state cookie."""
    return _build_cookie_header("oauth_state", state, 600)


def build_clear_oauth_state_cookie_header() -> str:
    """Build the Set-Cookie header to clear the OAuth state cookie."""
    return _build_cookie_header("oauth_state", "", 0)
