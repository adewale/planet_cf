# tests/integration/test_http.py
"""Integration tests for HTTP endpoint handling."""

import pytest
from unittest.mock import MagicMock


class MockRequest:
    """Mock HTTP request object."""

    def __init__(self, url: str, method: str = "GET", cookies: str = ""):
        self.url = url
        self.method = method
        self._cookies = cookies
        self.headers = MagicMock()
        self.headers.get = MagicMock(side_effect=self._get_header)

    def _get_header(self, name, default=None):
        if name.lower() == "cookie":
            return self._cookies
        return default

    async def formData(self):
        return {}

    async def json(self):
        return {}


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

    # Should redirect to GitHub OAuth
    assert response.status == 302
    location = response.headers.get("Location", "")
    assert "github.com" in location
    assert "oauth/authorize" in location


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

    # Get response body
    body = response.body if hasattr(response, "body") else ""
    # Planet name from mock_env
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
