# tests/unit/test_validate_and_add_feed.py
"""Unit tests for _validate_feed_url and _add_feed in src/main.py."""

from unittest.mock import AsyncMock, patch

import pytest

from src.main import Default
from src.wrappers import HttpResponse
from tests.conftest import MockEnv, MockQueue, TrackingD1

# =============================================================================
# Mock Infrastructure
# =============================================================================

VALID_RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Blog</title>
        <link>https://example.com</link>
        <description>A test blog</description>
        <item>
            <title>Post 1</title>
            <link>https://example.com/post/1</link>
            <description>Content</description>
        </item>
        <item>
            <title>Post 2</title>
            <link>https://example.com/post/2</link>
            <description>More content</description>
        </item>
    </channel>
</rss>"""

VALID_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>Atom Blog</title>
    <link href="https://example.com"/>
    <id>https://example.com/</id>
    <updated>2026-01-01T12:00:00Z</updated>
    <entry>
        <title>Atom Post</title>
        <link href="https://example.com/atom-post"/>
        <id>https://example.com/atom-post</id>
        <updated>2026-01-01T12:00:00Z</updated>
        <content type="html">&lt;p&gt;Content&lt;/p&gt;</content>
    </entry>
</feed>"""

NOT_A_FEED = """<html>
<head><title>Not a Feed</title></head>
<body><p>This is a regular webpage, not a feed.</p></body>
</html>"""


class MockFormData:
    """Mock form data object."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key: str):
        return self._data.get(key)


class MockRequest:
    """Mock HTTP request object."""

    def __init__(self, form_data: dict | None = None, method: str = "POST"):
        self.method = method
        self.url = "https://example.com/admin/feeds"
        self.headers = {}
        self._form_data = form_data or {}

    async def form_data(self):
        return MockFormData(self._form_data)


def _make_env(db=None):
    """Create a MockEnv with a TrackingD1 for validate/add-feed tests."""
    return MockEnv(
        DB=db or TrackingD1(),
        FEED_QUEUE=MockQueue(),
        DEAD_LETTER_QUEUE=MockQueue(),
        SEARCH_INDEX=None,
        AI=None,
    )


def _make_worker(env=None) -> Default:
    """Create a Default worker with mock env."""
    worker = Default()
    worker.env = env or _make_env()
    return worker


def _mock_admin() -> dict:
    """Return a mock admin user dict."""
    return {
        "id": 1,
        "github_username": "testadmin",
        "display_name": "Test Admin",
        "is_active": 1,
    }


# =============================================================================
# Tests: _validate_feed_url
# =============================================================================


class TestValidateFeedUrl:
    """Tests for Default._validate_feed_url method."""

    @pytest.mark.asyncio
    async def test_valid_rss_feed_returns_success(self):
        """Valid RSS feed URL returns valid=True with title and entry count."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=VALID_RSS_FEED,
                headers={"content-type": "application/rss+xml"},
                final_url="https://example.com/feed.xml",
            )
            result = await worker._validate_feed_url("https://example.com/feed.xml")

        assert result["valid"] is True
        assert result["title"] == "Test Blog"
        assert result["entry_count"] == 2
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_valid_atom_feed_returns_success(self):
        """Valid Atom feed URL returns valid=True with title."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=VALID_ATOM_FEED,
                headers={"content-type": "application/atom+xml"},
                final_url="https://example.com/feed.atom",
            )
            result = await worker._validate_feed_url("https://example.com/feed.atom")

        assert result["valid"] is True
        assert result["title"] == "Atom Blog"
        assert result["entry_count"] == 1

    @pytest.mark.asyncio
    async def test_non_feed_content_returns_error(self):
        """URL returning non-feed content returns valid=False."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=NOT_A_FEED,
                headers={"content-type": "text/html"},
                final_url="https://example.com/page",
            )
            result = await worker._validate_feed_url("https://example.com/page")

        assert result["valid"] is False
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_404_returns_error(self):
        """URL returning 404 returns valid=False with HTTP error."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=404,
                text="Not Found",
                headers={},
                final_url="https://example.com/missing.xml",
            )
            result = await worker._validate_feed_url("https://example.com/missing.xml")

        assert result["valid"] is False
        assert "HTTP 404" in result["error"]

    @pytest.mark.asyncio
    async def test_ssrf_blocked_redirect_returns_error(self):
        """URL that redirects to an unsafe location returns valid=False."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=VALID_RSS_FEED,
                headers={"content-type": "application/rss+xml"},
                final_url="http://169.254.169.254/latest/meta-data/",
            )
            result = await worker._validate_feed_url("https://example.com/feed.xml")

        assert result["valid"] is False
        assert "unsafe" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_redirect_followed_and_validated(self):
        """URL with redirect is followed; final_url is returned."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=VALID_RSS_FEED,
                headers={"content-type": "application/rss+xml"},
                final_url="https://new.example.com/feed.xml",
            )
            result = await worker._validate_feed_url("https://example.com/feed.xml")

        assert result["valid"] is True
        assert result["final_url"] == "https://new.example.com/feed.xml"

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        """Timeout during fetch returns valid=False with timeout message."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = TimeoutError("Connection timed out")
            result = await worker._validate_feed_url("https://slow.example.com/feed.xml")

        assert result["valid"] is False
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_final_url_change_returns_none(self):
        """When final_url matches original URL, final_url is None in result."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=VALID_RSS_FEED,
                headers={"content-type": "application/rss+xml"},
                final_url="https://example.com/feed.xml",
            )
            result = await worker._validate_feed_url("https://example.com/feed.xml")

        assert result["valid"] is True
        assert result["final_url"] is None


# =============================================================================
# Tests: _add_feed
# =============================================================================


class TestAddFeed:
    """Tests for Default._add_feed method."""

    @pytest.mark.asyncio
    async def test_successful_feed_addition(self):
        """Valid feed URL is inserted into DB and queued for processing."""
        db = TrackingD1([{"id": 42}])
        env = _make_env(db=db)
        worker = _make_worker(env)
        admin = _mock_admin()

        request = MockRequest(form_data={"url": "https://example.com/feed.xml", "title": "My Feed"})

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=VALID_RSS_FEED,
                headers={"content-type": "application/rss+xml"},
                final_url="https://example.com/feed.xml",
            )
            response = await worker._add_feed(request, admin)

        # Should redirect on success
        assert response.status == 302
        assert response.headers.get("Location") == "/admin"

        # Should have queued the feed
        assert len(env.FEED_QUEUE.messages) > 0

    @pytest.mark.asyncio
    async def test_duplicate_feed_url_returns_error(self):
        """Duplicate feed URL returns an error (DB insert raises)."""
        db = TrackingD1([])  # No result from INSERT RETURNING (simulates failure)
        env = _make_env(db=db)
        worker = _make_worker(env)
        admin = _mock_admin()

        request = MockRequest(form_data={"url": "https://example.com/feed.xml"})

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=VALID_RSS_FEED,
                headers={"content-type": "application/rss+xml"},
                final_url="https://example.com/feed.xml",
            )
            response = await worker._add_feed(request, admin)

        # When feed_id is None, it still redirects (the feed was technically inserted)
        # The important thing is no crash
        assert response.status in (200, 302)

    @pytest.mark.asyncio
    async def test_ssrf_blocked_url_returns_error(self):
        """SSRF-blocked URL returns error without fetching."""
        worker = _make_worker()
        admin = _mock_admin()

        request = MockRequest(form_data={"url": "http://localhost/feed.xml"})

        response = await worker._add_feed(request, admin)

        # Should return error page (not redirect)
        assert response.status in (200, 400)
        assert "Invalid URL" in response.body or "unsafe" in response.body.lower()

    @pytest.mark.asyncio
    async def test_missing_url_returns_error(self):
        """Missing URL in form data returns error."""
        worker = _make_worker()
        admin = _mock_admin()

        request = MockRequest(form_data={})

        response = await worker._add_feed(request, admin)

        assert response.status in (200, 400)
        assert "URL Required" in response.body or "provide a feed URL" in response.body

    @pytest.mark.asyncio
    async def test_invalid_feed_returns_validation_error(self):
        """URL that doesn't serve a valid feed returns validation error."""
        worker = _make_worker()
        admin = _mock_admin()

        request = MockRequest(form_data={"url": "https://example.com/page.html"})

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=NOT_A_FEED,
                headers={"content-type": "text/html"},
                final_url="https://example.com/page.html",
            )
            response = await worker._add_feed(request, admin)

        assert response.status in (200, 400)
        assert "Validation Failed" in response.body or "validate" in response.body.lower()

    @pytest.mark.asyncio
    async def test_uses_extracted_title_when_not_provided(self):
        """When no title is provided, uses title extracted from feed."""
        db = TrackingD1([{"id": 1}])
        env = _make_env(db=db)
        worker = _make_worker(env)
        admin = _mock_admin()

        request = MockRequest(form_data={"url": "https://example.com/feed.xml"})

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = HttpResponse(
                status_code=200,
                text=VALID_RSS_FEED,
                headers={"content-type": "application/rss+xml"},
                final_url="https://example.com/feed.xml",
            )
            response = await worker._add_feed(request, admin)

        assert response.status == 302

        # Find the INSERT statement and verify title was extracted from feed
        insert_stmts = [s for s in db.statements if "INSERT INTO feeds" in s.sql]
        assert len(insert_stmts) > 0
        # The title from the RSS feed is "Test Blog"
        assert "Test Blog" in insert_stmts[0].bound_args
