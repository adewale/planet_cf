# tests/e2e/conftest.py
"""E2E test configuration and shared fixtures.

Centralizes all E2E test configuration to avoid duplication across test files.
All E2E tests should import from here instead of defining their own config.

Configuration (override via environment variables):
    E2E_BASE_URL         Base URL of the test server (default: http://localhost:8787)
    E2E_SESSION_SECRET   Session secret matching the worker's SESSION_SECRET
    E2E_ADMIN_USERNAME   Admin username seeded in the test database
    RUN_E2E_TESTS        Set to "1" to enable tests requiring indexed fixture data
"""

import base64
import hashlib
import hmac
import json
import os
import time

import httpx
import pytest

# =============================================================================
# E2E Configuration
# =============================================================================

#: Base URL of the test server
E2E_BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8787")

#: Session secret - MUST match the deployed test-planet's SESSION_SECRET
E2E_SESSION_SECRET = os.environ.get(
    "E2E_SESSION_SECRET",
    "test-session-secret-for-e2e-testing-only",
)

#: Test admin username - MUST be seeded in the test-planet database
E2E_ADMIN_USERNAME = os.environ.get("E2E_ADMIN_USERNAME", "testadmin")

#: Service identifier the /health endpoint must return to confirm this is Planet CF
EXPECTED_SERVICE = "planetcf"


# =============================================================================
# Server Connectivity
# =============================================================================

#: Health endpoint used to verify the correct app is responding
E2E_HEALTH_URL = f"{E2E_BASE_URL}/health"


def is_planetcf_running(base_url: str = E2E_BASE_URL, timeout: float = 10) -> bool:
    """Check if a Planet CF instance is running at the given URL.

    Makes an HTTP GET to /health and verifies:
    1. HTTP 200
    2. Valid JSON
    3. ``"service": "planetcf"`` — confirms identity, not just "something is listening"

    This is the single source of truth for server detection.  All test
    skip-guards must call this function rather than implementing their own
    socket or HTTP checks.
    """
    try:
        resp = httpx.get(f"{base_url}/health", timeout=timeout)
        if resp.status_code != 200:
            return False
        data = resp.json()
        return data.get("service") == EXPECTED_SERVICE
    except (httpx.HTTPError, ValueError):
        return False


#: Marker to skip tests when the server is not running
requires_server = pytest.mark.skipif(
    not is_planetcf_running(),
    reason=(
        f"Planet CF not responding at {E2E_HEALTH_URL} "
        f"(expected JSON with service={EXPECTED_SERVICE!r}). "
        "Start with: npx wrangler dev --remote --config examples/test-planet/wrangler.jsonc"
    ),
)


# =============================================================================
# Session Cookie Creation
# =============================================================================


def create_test_session(
    username: str = E2E_ADMIN_USERNAME,
    github_id: int = 12345,
) -> str:
    """Create a signed session cookie value for testing (bypasses OAuth).

    Uses urlsafe_b64encode to match the production cookie format in src/auth.py.

    Returns:
        The cookie value (without 'session=' prefix).
    """
    payload = {
        "github_username": username,
        "github_id": github_id,
        "avatar_url": None,
        "exp": int(time.time()) + 3600,
    }
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    signature = hmac.new(
        E2E_SESSION_SECRET.encode(),
        payload_b64.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{signature}"


# =============================================================================
# Shared Fixtures
# =============================================================================


@pytest.fixture
def admin_session() -> dict[str, str]:
    """Provide admin session cookies dict for httpx."""
    return {"session": create_test_session()}


@pytest.fixture
def base_url() -> str:
    """Provide the E2E base URL."""
    return E2E_BASE_URL
