# tests/integration/test_http.py
"""Integration tests for HTTP endpoint handling."""

from unittest.mock import MagicMock

import pytest


class MockFormData:
    """Mock form data that behaves like a dict."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockRequest:
    """Mock HTTP request object matching Cloudflare Workers Python SDK."""

    def __init__(
        self,
        url: str,
        method: str = "GET",
        cookies: str = "",
        form_data: dict | None = None,
        json_data: dict | None = None,
    ):
        self.url = url
        self.method = method
        self._cookies = cookies
        self._form_data = form_data or {}
        self._json_data = json_data or {}
        self.headers = MagicMock()
        self.headers.get = MagicMock(side_effect=self._get_header)

    def _get_header(self, name, default=None):
        if name.lower() == "cookie":
            return self._cookies
        return default

    async def form_data(self):
        """Workers Python SDK uses snake_case form_data(), not formData()."""
        return MockFormData(self._form_data)

    async def json(self):
        return self._json_data


@pytest.mark.asyncio
async def test_http_serves_html_for_root(mock_env_with_entries):
    """HTTP handler should return HTML for / route."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/")

    response = await worker.fetch(request)

    assert response.status == 200
    assert "text/html" in response.headers.get("Content-Type", "")
    assert "Cache-Control" in response.headers


@pytest.mark.asyncio
async def test_http_serves_atom_feed(mock_env_with_entries):
    """HTTP handler should return Atom feed for /feed.atom route."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.atom")

    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/atom+xml" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_http_serves_rss_feed(mock_env_with_entries):
    """HTTP handler should return RSS feed for /feed.rss route."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.rss")

    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/rss+xml" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_http_serves_opml_export(mock_env_with_feeds):
    """HTTP handler should return OPML for /feeds.opml route."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/feeds.opml")

    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/xml" in response.headers.get("Content-Type", "")
    assert "planetcf-feeds.opml" in response.headers.get("Content-Disposition", "")


@pytest.mark.asyncio
async def test_http_returns_404_for_unknown_routes(mock_env):
    """HTTP handler should return 404 for unknown routes."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    request = MockRequest("https://planetcf.com/unknown/path")

    response = await worker.fetch(request)

    assert response.status == 404


@pytest.mark.asyncio
async def test_http_cache_control_headers(mock_env_with_entries):
    """HTTP responses should include Cache-Control headers."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    routes = ["/", "/feed.atom", "/feed.rss"]

    for route in routes:
        request = MockRequest(f"https://planetcf.com{route}")
        response = await worker.fetch(request)

        cache_control = response.headers.get("Cache-Control", "")
        assert "max-age" in cache_control


@pytest.mark.asyncio
async def test_http_search_requires_query(mock_env):
    """Search endpoint should require a query parameter."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    # No query parameter
    request = MockRequest("https://planetcf.com/search")
    response = await worker.fetch(request)
    assert response.status == 400

    # Empty query
    request = MockRequest("https://planetcf.com/search?q=")
    response = await worker.fetch(request)
    assert response.status == 400

    # Query too short
    request = MockRequest("https://planetcf.com/search?q=a")
    response = await worker.fetch(request)
    assert response.status == 400


@pytest.mark.asyncio
async def test_admin_requires_authentication(mock_env):
    """Admin routes should require authentication."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    request = MockRequest("https://planetcf.com/admin")

    response = await worker.fetch(request)

    # Should show login page (not auto-redirect)
    assert response.status == 200
    # Login page contains GitHub OAuth link
    assert "/auth/github" in response.body
    assert "Sign in with GitHub" in response.body


@pytest.mark.asyncio
async def test_static_css_served(mock_env):
    """Static CSS should be served."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    request = MockRequest("https://planetcf.com/static/style.css")

    response = await worker.fetch(request)

    assert response.status == 200
    assert "text/css" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_html_contains_planet_name(mock_env_with_entries):
    """Generated HTML should contain the planet name."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/")
    response = await worker.fetch(request)

    assert response.status == 200


@pytest.mark.asyncio
async def test_feed_contains_entries(mock_env_with_entries):
    """Generated feeds should contain entries."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    # Test Atom feed
    request = MockRequest("https://planetcf.com/feed.atom")
    response = await worker.fetch(request)
    assert response.status == 200

    # Test RSS feed
    request = MockRequest("https://planetcf.com/feed.rss")
    response = await worker.fetch(request)
    assert response.status == 200


def _create_signed_session(env, username="testadmin", github_id=12345):
    """Create a valid signed session cookie for testing."""
    import base64
    import hashlib
    import hmac
    import json
    import time

    payload = {
        "github_username": username,
        "github_id": github_id,
        "avatar_url": None,
        "exp": int(time.time()) + 3600,  # 1 hour from now
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(
        env.SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    return f"session={payload_b64}.{signature}"


@pytest.mark.asyncio
async def test_admin_add_feed_via_post(mock_env_with_admins):
    """Admin should be able to add a feed via POST."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    # Create signed session cookie
    session_cookie = _create_signed_session(mock_env_with_admins)

    # POST to add a feed
    request = MockRequest(
        url="https://planetcf.com/admin/feeds",
        method="POST",
        cookies=session_cookie,
        form_data={"url": "https://boristane.com/rss.xml", "title": "Boris Tane"},
    )

    response = await worker.fetch(request)

    # Should redirect back to admin on success
    assert response.status == 302, f"Expected 302 redirect, got {response.status}"
    assert response.headers.get("Location") == "/admin"


@pytest.mark.asyncio
async def test_admin_add_feed_rejects_unsafe_url(mock_env_with_admins):
    """Admin add feed should reject unsafe URLs (SSRF protection)."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    session_cookie = _create_signed_session(mock_env_with_admins)

    # Try to add a localhost URL (should be blocked)
    request = MockRequest(
        url="https://planetcf.com/admin/feeds",
        method="POST",
        cookies=session_cookie,
        form_data={"url": "http://localhost/feed.xml"},
    )

    response = await worker.fetch(request)

    # Should return error, not redirect
    assert response.status == 400


@pytest.mark.asyncio
async def test_admin_add_feed_requires_url(mock_env_with_admins):
    """Admin add feed should require a URL."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    session_cookie = _create_signed_session(mock_env_with_admins)

    # POST without URL
    request = MockRequest(
        url="https://planetcf.com/admin/feeds",
        method="POST",
        cookies=session_cookie,
        form_data={},
    )

    response = await worker.fetch(request)

    # Should return error
    assert response.status == 400


# =============================================================================
# Issue 5.4: Test Search with No Matches
# =============================================================================


@pytest.mark.asyncio
async def test_search_returns_empty_results(mock_env):
    """Search should handle no results gracefully."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    # Search for something that doesn't exist
    request = MockRequest("https://planetcf.com/search?q=xyznonexistent123")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "No results found" in response.body


@pytest.mark.asyncio
async def test_search_with_valid_query(mock_env_with_entries):
    """Search with valid query should return results or no results message."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=test")
    response = await worker.fetch(request)

    assert response.status == 200
    # Should either show results or "No results found"
    assert "Search Results" in response.body
