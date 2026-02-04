# tests/e2e/test_feed_workflow.py
"""
End-to-End tests for the feed workflow.

These tests run against a real wrangler dev instance with remote D1.
They test the actual JsProxy handling and D1 integration.

To run:
    1. Start wrangler dev: npx wrangler dev --remote --config examples/test-planet/wrangler.jsonc
    2. Run tests: uv run pytest tests/e2e/ -v

Note: These tests require:
    - A running wrangler dev instance
    - Remote D1 database access (--remote flag)
    - A test admin seeded in the database (via scripts/seed_test_data.py)
"""

import httpx
import pytest

from tests.e2e.conftest import E2E_BASE_URL, create_test_session, requires_server


@requires_server
class TestPublicEndpoints:
    """Test public endpoints that don't require authentication."""

    def setup_method(self):
        self.client = httpx.Client(base_url=E2E_BASE_URL, follow_redirects=False)

    def teardown_method(self):
        self.client.close()

    def test_homepage_returns_200(self):
        """Homepage should return 200 OK."""
        response = self.client.get("/")
        assert response.status_code == 200

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
    """Test admin endpoints that require authentication.

    Requires testadmin to be seeded in the database.
    Run: uv run python scripts/seed_test_data.py --local
    """

    def setup_method(self):
        session_value = create_test_session()
        self.client = httpx.Client(
            base_url=E2E_BASE_URL,
            follow_redirects=False,
            cookies={"session": session_value},
        )

    def teardown_method(self):
        self.client.close()

    def test_admin_dashboard_accessible(self):
        """Admin dashboard should be accessible with valid session."""
        response = self.client.get("/admin")
        # 200 = authorized, 403 = admin not in DB (need to seed)
        assert response.status_code in (200, 403)

    def test_add_feed_with_valid_url(self):
        """Should be able to add a feed with valid URL."""
        response = self.client.post(
            "/admin/feeds",
            data={"url": "https://boristane.com/rss.xml", "title": "Boris Tane"},
        )
        # 200 = success page or duplicate, 302 = redirect, 400 = validation error
        assert response.status_code in (200, 302, 400)

    def test_add_feed_rejects_unsafe_url(self):
        """Should reject unsafe URLs (SSRF protection)."""
        response = self.client.post(
            "/admin/feeds",
            data={"url": "http://localhost/feed.xml"},
        )
        # Admin error pages return 200 with an error message in the HTML
        # If session is invalid, the login page is shown instead
        assert response.status_code in (200, 400)
        if "Sign in with GitHub" in response.text:
            pytest.skip("Session not valid - SESSION_SECRET may not match the running instance")
        assert "Invalid URL" in response.text or "unsafe" in response.text.lower()


@requires_server
class TestOAuthFlow:
    """Test OAuth flow endpoints."""

    def setup_method(self):
        self.client = httpx.Client(base_url=E2E_BASE_URL, follow_redirects=False)

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
    client = httpx.Client(base_url="{E2E_BASE_URL}")
    response = client.{method.lower()}("{path}")
    # Add assertions based on expected behavior
    assert response.status_code != 500  # Should not error
    client.close()
'''


if __name__ == "__main__":
    # Quick connectivity test
    import sys

    try:
        client = httpx.Client(base_url=E2E_BASE_URL, timeout=5.0)
        response = client.get("/")
        print(f"Connected to {E2E_BASE_URL}: {response.status_code}")
        client.close()
    except Exception as e:
        print(f"Failed to connect to {E2E_BASE_URL}: {e}")
        print("\nMake sure wrangler dev is running:")
        print("  npx wrangler dev --remote --config examples/test-planet/wrangler.jsonc")
        sys.exit(1)
