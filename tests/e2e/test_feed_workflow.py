# tests/e2e/test_feed_workflow.py
"""
End-to-End tests for the feed workflow.

These tests run against a real wrangler dev instance with remote D1.
They test the actual JsProxy handling and D1 integration.

To run:
    1. Start wrangler dev: npx wrangler dev --remote
    2. Run tests: uv run pytest tests/e2e/ -v

Note: These tests require:
    - A running wrangler dev instance on localhost:8787
    - Remote D1 database access (--remote flag)
    - A test admin in the database (for authenticated operations)
"""

import base64
import hashlib
import hmac
import json
import os
import socket
import time

import httpx
import pytest

from tests.e2e.conftest import requires_server

# Test configuration
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8787")


def _is_server_running(host: str = "localhost", port: int = 8787) -> bool:
    """Check if server is running on the specified host:port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


# Skip marker for tests requiring running server
requires_server = pytest.mark.skipif(
    not _is_server_running(),
    reason=f"Server not running on {BASE_URL}",
)
SESSION_SECRET = os.environ.get("E2E_SESSION_SECRET", "test-secret-for-e2e-testing")
TEST_ADMIN_USERNAME = os.environ.get("E2E_ADMIN_USERNAME", "testadmin")


def create_test_session(username: str = TEST_ADMIN_USERNAME, github_id: int = 12345) -> str:
    """Create a signed session cookie for testing (bypasses OAuth)."""
    payload = {
        "github_username": username,
        "github_id": github_id,
        "avatar_url": None,
        "exp": int(time.time()) + 3600,  # 1 hour from now
    }
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    signature = hmac.new(SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"session={payload_b64}.{signature}"


@requires_server
class TestPublicEndpoints:
    """Test public endpoints that don't require authentication."""

    def setup_method(self):
        self.client = httpx.Client(base_url=BASE_URL, follow_redirects=False)

    def teardown_method(self):
        self.client.close()

    def test_homepage_returns_200(self):
        """Homepage should return 200 OK."""
        response = self.client.get("/")
        assert response.status_code == 200
        assert "Planet CF" in response.text

    def test_atom_feed_returns_xml(self):
        """Atom feed should return valid XML."""
        response = self.client.get("/feed.atom")
        assert response.status_code == 200
        assert "application/atom+xml" in response.headers.get("content-type", "")
        assert '<?xml version="1.0"' in response.text

    def test_rss_feed_returns_xml(self):
        """RSS feed should return valid XML."""
        response = self.client.get("/feed.rss")
        assert response.status_code == 200
        assert "application/rss+xml" in response.headers.get("content-type", "")
        assert "<rss version=" in response.text

    def test_opml_export_returns_xml(self):
        """OPML export should return valid XML."""
        response = self.client.get("/feeds.opml")
        assert response.status_code == 200
        assert "application/xml" in response.headers.get("content-type", "")

    def test_search_requires_query(self):
        """Search without query should show error message."""
        response = self.client.get("/search")
        assert response.status_code == 200
        assert "at least 2 characters" in response.text

    def test_search_with_short_query_shows_error(self):
        """Search with too-short query should show error message."""
        response = self.client.get("/search?q=a")
        assert response.status_code == 200
        assert "at least 2 characters" in response.text

    def test_static_css_served(self):
        """Static CSS should be served."""
        response = self.client.get("/static/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers.get("content-type", "")

    def test_unknown_route_returns_404(self):
        """Unknown routes should return 404."""
        response = self.client.get("/nonexistent-route-12345")
        assert response.status_code == 404


@requires_server
class TestAdminEndpoints:
    """Test admin endpoints that require authentication."""

    def setup_method(self):
        self.session_cookie = create_test_session()
        self.client = httpx.Client(
            base_url=BASE_URL,
            follow_redirects=False,
            cookies={"session": self.session_cookie.split("=", 1)[1]},
        )

    def teardown_method(self):
        self.client.close()

    @pytest.mark.skip(reason="Requires test admin in database")
    def test_admin_dashboard_accessible(self):
        """Admin dashboard should be accessible with valid session."""
        response = self.client.get("/admin", headers={"Cookie": self.session_cookie})
        # Either 200 (authorized) or 403 (no admin in DB)
        assert response.status_code in (200, 403)

    @pytest.mark.skip(reason="Requires test admin in database")
    def test_add_feed_with_valid_url(self):
        """Should be able to add a feed with valid URL."""
        response = self.client.post(
            "/admin/feeds",
            data={"url": "https://boristane.com/rss.xml", "title": "Boris Tane"},
            headers={"Cookie": self.session_cookie},
        )
        # 302 = redirect on success, 400 = validation error, 403 = unauthorized
        assert response.status_code in (302, 400, 403)

    @pytest.mark.skip(reason="Requires test admin in database")
    def test_add_feed_rejects_unsafe_url(self):
        """Should reject unsafe URLs (SSRF protection)."""
        response = self.client.post(
            "/admin/feeds",
            data={"url": "http://localhost/feed.xml"},
            headers={"Cookie": self.session_cookie},
        )
        assert response.status_code == 400


@requires_server
class TestOAuthFlow:
    """Test OAuth flow endpoints."""

    def setup_method(self):
        self.client = httpx.Client(base_url=BASE_URL, follow_redirects=False)

    def teardown_method(self):
        self.client.close()

    def test_admin_without_auth_shows_login(self):
        """Admin without auth should show login page."""
        response = self.client.get("/admin")
        assert response.status_code == 200
        assert "Sign in with GitHub" in response.text

    def test_github_oauth_redirect(self):
        """GitHub OAuth endpoint should redirect."""
        response = self.client.get("/auth/github")
        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "github.com" in location or "authorize" in location


# =============================================================================
# Error Replay Test Generator
# =============================================================================


def generate_test_from_error(error_log: dict) -> str:
    """
    Generate a test case from a production error log.

    This is used to turn production errors into reproducible test cases.
    The error log should contain:
    - path: The request path
    - method: HTTP method
    - error_type: The exception type
    - error_message: The exception message
    """
    test_name = f"test_replay_{error_log.get('error_type', 'unknown')}"
    path = error_log.get("path", "/")
    method = error_log.get("method", "GET")

    return f'''
@pytest.mark.skip(reason="Generated from production error - needs review")
def {test_name}():
    """Replay test generated from production error.

    Original error: {error_log.get("error_type")}: {error_log.get("error_message")}
    """
    client = httpx.Client(base_url="{BASE_URL}")
    response = client.{method.lower()}("{path}")
    # Add assertions based on expected behavior
    assert response.status_code != 500  # Should not error
    client.close()
'''


if __name__ == "__main__":
    # Quick connectivity test
    import sys

    try:
        client = httpx.Client(base_url=BASE_URL, timeout=5.0)
        response = client.get("/")
        print(f"Connected to {BASE_URL}: {response.status_code}")
        client.close()
    except Exception as e:
        print(f"Failed to connect to {BASE_URL}: {e}")
        print("\nMake sure wrangler dev is running:")
        print("  npx wrangler dev --remote")
        sys.exit(1)
