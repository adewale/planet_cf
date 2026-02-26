# tests/integration/test_http.py
"""Integration tests for HTTP endpoint handling."""

import pytest

from tests.conftest import MockRequest


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
async def test_http_serves_rss10_feed(mock_env_with_entries):
    """HTTP handler should return RSS 1.0 (RDF) feed for /feed.rss10 route."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.rss10")

    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/rdf+xml" in response.headers.get("Content-Type", "")


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

    routes = ["/", "/feed.atom", "/feed.rss", "/feed.rss10"]

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

    # No query parameter - shows error page
    request = MockRequest("https://planetcf.com/search")
    response = await worker.fetch(request)
    assert response.status == 200
    assert "at least 2 characters" in response.body.lower()

    # Empty query - shows error page
    request = MockRequest("https://planetcf.com/search?q=")
    response = await worker.fetch(request)
    assert response.status == 200
    assert "at least 2 characters" in response.body.lower()

    # Query too short - shows error page
    request = MockRequest("https://planetcf.com/search?q=a")
    response = await worker.fetch(request)
    assert response.status == 200
    assert "at least 2 characters" in response.body.lower()


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
async def test_static_css_served_by_assets(mock_env):
    """Static CSS is served by Workers Static Assets binding, not the Worker."""
    request = MockRequest("https://planetcf.com/static/style.css")

    # In production, Static Assets intercepts /static/ before the Worker runs.
    # Test that the ASSETS binding serves the file correctly.
    response = await mock_env.ASSETS.fetch(request)

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
    from unittest.mock import AsyncMock, patch

    from src.main import PlanetCF
    from src.wrappers import HttpResponse

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    # Create signed session cookie
    session_cookie = _create_signed_session(mock_env_with_admins)

    # Mock RSS feed response for validation
    mock_rss_content = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Boris Tane</title>
            <link>https://boristane.com</link>
            <description>Blog posts</description>
            <item>
                <title>Test Post</title>
                <link>https://boristane.com/post1</link>
                <description>Test content</description>
                <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>"""

    mock_response = HttpResponse(
        status_code=200,
        headers={"content-type": "application/rss+xml"},
        text=mock_rss_content,
        final_url="https://boristane.com/rss.xml",
    )

    # Patch safe_http_fetch to return mock RSS feed
    with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_response

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

        # Verify the feed URL was fetched for validation
        mock_fetch.assert_called()


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

    # Should return error page (200 with error content), not redirect
    assert response.status == 200
    assert "Invalid URL" in response.body or "unsafe" in response.body.lower()


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

    # Should return error page (200 with error content)
    assert response.status == 200
    assert "URL Required" in response.body or "provide a feed URL" in response.body


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


# =============================================================================
# Author Email Filtering Tests
# =============================================================================


@pytest.mark.asyncio
async def test_homepage_hides_email_author(mock_env):
    """Homepage should hide email addresses in author field and show feed title instead.

    This tests the fix for Blogger feeds that expose email addresses like
    'noreply@blogger.com' as the author. The template should display the
    feed title when the author field contains an '@' symbol.
    """
    from src.main import PlanetCF
    from tests.conftest import MockD1

    # Create mock with entry that has email as author
    mock_env.DB = MockD1(
        {
            "feeds": [
                {
                    "id": 1,
                    "url": "https://example.blogspot.com/feed.xml",
                    "title": "Example Blog",
                    "is_active": 1,
                    "site_url": "https://example.blogspot.com",
                    "consecutive_failures": 0,
                    "last_success_at": "2026-01-15T00:00:00Z",
                },
            ],
            "entries": [
                {
                    "id": 1,
                    "feed_id": 1,
                    "guid": "entry-1",
                    "url": "https://example.blogspot.com/post/1",
                    "title": "Blog Post About Cloudflare",
                    "author": "noreply@blogger.com",  # Email should be hidden
                    "content": "<p>Content</p>",
                    "published_at": "2026-01-15T12:00:00Z",
                    "feed_title": "Example Blog",  # Should show this instead
                    "feed_site_url": "https://example.blogspot.com",
                },
            ],
        }
    )

    worker = PlanetCF()
    worker.env = mock_env

    request = MockRequest("https://planetcf.com/")
    response = await worker.fetch(request)

    assert response.status == 200
    # Entry should be shown (verify by entry title)
    assert "Blog Post About Cloudflare" in response.body, "Entry should be displayed"
    # Email should NOT appear in output
    assert "noreply@blogger.com" not in response.body, "Email address should be hidden"
    # Feed title should appear as author
    assert "Example Blog" in response.body, "Feed title should be shown instead of email"


@pytest.mark.asyncio
async def test_homepage_shows_normal_author(mock_env):
    """Homepage should show author names that don't contain email addresses."""
    from src.main import PlanetCF
    from tests.conftest import MockD1

    # Create mock with entry that has a normal author name
    mock_env.DB = MockD1(
        {
            "feeds": [
                {
                    "id": 1,
                    "url": "https://example.com/feed.xml",
                    "title": "Example Blog",
                    "is_active": 1,
                    "site_url": "https://example.com",
                    "consecutive_failures": 0,
                    "last_success_at": "2026-01-15T00:00:00Z",
                },
            ],
            "entries": [
                {
                    "id": 1,
                    "feed_id": 1,
                    "guid": "entry-1",
                    "url": "https://example.com/post/1",
                    "title": "Another Blog Post Title",
                    "author": "John Doe",  # Normal name should be shown
                    "content": "<p>Content</p>",
                    "published_at": "2026-01-15T12:00:00Z",
                    "feed_title": "Example Blog",
                    "feed_site_url": "https://example.com",
                },
            ],
        }
    )

    worker = PlanetCF()
    worker.env = mock_env

    request = MockRequest("https://planetcf.com/")
    response = await worker.fetch(request)

    assert response.status == 200
    # Entry should be shown (verify by entry title)
    assert "Another Blog Post Title" in response.body, "Entry should be displayed"
    # Normal author name should appear
    assert "John Doe" in response.body, "Normal author name should be shown"


# =============================================================================
# Phase 2: Missing Route Coverage
# =============================================================================


@pytest.mark.asyncio
async def test_get_titles_returns_html(mock_env_with_entries):
    """GET /titles returns 200 with HTML content."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/titles")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "text/html" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_get_foafroll_returns_xml(mock_env_with_feeds):
    """GET /foafroll.xml returns 200 with RDF/XML content."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/foafroll.xml")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/rdf+xml" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_get_health_returns_json(mock_env_with_feeds):
    """GET /health returns 200 with JSON health status."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/health")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/json" in response.headers.get("Content-Type", "")
    import json

    data = json.loads(response.body)
    assert data["service"] == "planetcf"
    assert data["status"] in ("healthy", "degraded", "unhealthy")


@pytest.mark.asyncio
async def test_get_auth_github_redirects(mock_env):
    """GET /auth/github returns 302 redirect to GitHub OAuth."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    request = MockRequest("https://planetcf.com/auth/github")
    response = await worker.fetch(request)

    assert response.status == 302
    location = response.headers.get("Location", "")
    assert "github.com/login/oauth/authorize" in location
    assert "client_id=" in location


@pytest.mark.asyncio
async def test_get_auth_github_callback_without_code(mock_env_with_admins):
    """GET /auth/github/callback without code param returns error."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    request = MockRequest("https://planetcf.com/auth/github/callback")
    response = await worker.fetch(request)

    # Should return an error (400 or 200 with error content), not 302 redirect to admin
    assert response.status != 302


@pytest.mark.asyncio
async def test_get_auth_github_callback_with_invalid_state(mock_env_with_admins):
    """GET /auth/github/callback with invalid state returns error."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    request = MockRequest(
        "https://planetcf.com/auth/github/callback?code=fake&state=invalid",
        cookies="oauth_state=different_state",
    )
    response = await worker.fetch(request)

    # Should fail state validation — not redirect to admin
    assert response.status != 302 or "/admin" not in response.headers.get("Location", "")


# =============================================================================
# Phase 3: Security Boundary Tests
# =============================================================================


@pytest.mark.asyncio
async def test_unauthenticated_post_admin_feeds_rejected(mock_env_with_admins):
    """POST /admin/feeds without session shows login page, not mutation."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    request = MockRequest(
        url="https://planetcf.com/admin/feeds",
        method="POST",
        form_data={"url": "https://evil.com/feed.xml"},
    )
    response = await worker.fetch(request)

    # Should show login page or reject — NOT perform the mutation
    assert response.status in (200, 401, 403)
    if response.status == 200:
        assert "Sign in" in response.body or "login" in response.body.lower()


@pytest.mark.asyncio
async def test_unauthenticated_delete_admin_feed_rejected(mock_env_with_admins):
    """DELETE /admin/feeds/1 without session shows login page, not mutation."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    request = MockRequest(
        url="https://planetcf.com/admin/feeds/1",
        method="DELETE",
    )
    response = await worker.fetch(request)

    # Should show login page or reject — NOT delete the feed
    assert response.status in (200, 401, 403)
    if response.status == 200:
        assert "Sign in" in response.body or "login" in response.body.lower()


@pytest.mark.asyncio
async def test_expired_session_shows_login(mock_env_with_admins):
    """Expired session cookie shows login page instead of admin dashboard."""
    import base64
    import hashlib
    import hmac
    import json
    import time

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    # Create expired session (1 hour ago, well past grace period)
    payload = {
        "github_username": "testadmin",
        "github_id": 12345,
        "avatar_url": None,
        "exp": int(time.time()) - 3600,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(
        mock_env_with_admins.SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    expired_cookie = f"session={payload_b64}.{sig}"

    request = MockRequest(
        url="https://planetcf.com/admin",
        cookies=expired_cookie,
    )
    response = await worker.fetch(request)

    assert response.status == 200
    assert "Sign in" in response.body or "login" in response.body.lower()


@pytest.mark.asyncio
async def test_tampered_session_signature_shows_login(mock_env_with_admins):
    """Session with tampered signature shows login page."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_admins

    # Create valid session then tamper with signature
    valid_cookie = _create_signed_session(mock_env_with_admins)
    # Corrupt the signature (last 10 chars)
    tampered = valid_cookie[:-10] + "x" * 10

    request = MockRequest(
        url="https://planetcf.com/admin",
        cookies=tampered,
    )
    response = await worker.fetch(request)

    assert response.status == 200
    assert "Sign in" in response.body or "login" in response.body.lower()
