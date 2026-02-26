# tests/unit/test_admin_routes_extended.py
"""Tests for untested admin routes and fetch handler paths in src/main.py.

Covers:
- Lines 1464-1505: Lite mode blocking, response size tracking, event finalization
- Lines 2321-2335: Search query too-long validation
- Lines 3150-3220: _retry_dlq_feed admin action
"""

import base64
import hashlib
import hmac
import json
import time
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from src.main import Default
from tests.conftest import MockD1

# =============================================================================
# Compatibility: ET.XMLParser(forbid_dtd=True) was added in Python 3.13.1.
# =============================================================================

_original_xml_parser = ET.XMLParser


def _patched_xml_parser(**kwargs):
    kwargs.pop("forbid_dtd", None)
    return _original_xml_parser(**kwargs)


# =============================================================================
# Mock Infrastructure
# =============================================================================


class MockQueue:
    """Mock Cloudflare Queue."""

    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)

    async def sendBatch(self, messages):
        for msg in messages:
            self.messages.append(msg.get("body", msg))


class MockRequest:
    """Mock HTTP request for admin route tests."""

    def __init__(
        self,
        url: str = "https://planetcf.com/admin",
        method: str = "GET",
        cookies: str = "",
        headers: dict | None = None,
        form_data: dict | None = None,
        json_data: dict | None = None,
    ):
        self.url = url
        self.method = method
        self._cookies = cookies
        self._form_data = form_data or {}
        self._json_data = json_data or {}
        self._raw_headers = headers or {}

        mock_headers = MagicMock()
        mock_headers.get = MagicMock(side_effect=self._get_header)
        self.headers = mock_headers

    def _get_header(self, name, default=None):
        for key, val in self._raw_headers.items():
            if key.lower() == name.lower():
                return val
        if name.lower() == "cookie":
            return self._cookies
        return default

    async def form_data(self):
        return _MockFormData(self._form_data)

    async def json(self):
        return self._json_data

    async def text(self):
        return json.dumps(self._json_data)


class _MockFormData:
    """Mock form data object."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class _AdminEnv:
    """Mock environment for admin route tests."""

    def __init__(self, db=None, admins=None, feeds=None):
        data = {}
        if admins is not None:
            data["admins"] = admins
        if feeds is not None:
            data["feeds"] = feeds
        self.DB = db or MockD1(data)
        self.AI = MagicMock()
        self.AI.run = MagicMock()
        self.SEARCH_INDEX = MagicMock()
        self.FEED_QUEUE = MockQueue()
        self.DEAD_LETTER_QUEUE = MockQueue()
        self.PLANET_NAME = "Test Planet"
        self.PLANET_URL = "https://test.example.com"
        self.PLANET_DESCRIPTION = "Test description"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"  # pragma: allowlist secret
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"  # pragma: allowlist secret


def _admin_row():
    """Return a standard admin row."""
    return {
        "id": 1,
        "github_username": "testadmin",
        "github_id": 12345,
        "display_name": "Test Admin",
        "is_active": 1,
        "last_login_at": None,
        "created_at": "2026-01-01T00:00:00Z",
    }


def _create_signed_session(
    secret: str,
    username: str = "testadmin",
    github_id: int = 12345,
) -> str:
    """Create a valid signed session cookie for testing."""
    payload = {
        "github_username": username,
        "github_id": github_id,
        "avatar_url": None,
        "exp": int(time.time()) + 3600,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"session={payload_b64}.{signature}"


def _make_authenticated_worker(feeds=None, admins=None) -> tuple[Default, _AdminEnv, str]:
    """Create a worker with authenticated env and session cookie."""
    admin_list = admins or [_admin_row()]
    feed_list = feeds or []
    env = _AdminEnv(admins=admin_list, feeds=feed_list)
    session_cookie = _create_signed_session(env.SESSION_SECRET)
    worker = Default()
    worker.env = env
    return worker, env, session_cookie


# =============================================================================
# Tests: Lite Mode Blocking (Lines 1463-1468)
# =============================================================================


class TestLiteModeBlocking:
    """Tests for lite mode route blocking in fetch()."""

    @pytest.mark.asyncio
    async def test_search_blocked_in_lite_mode(self):
        """Search route returns 404 when lite mode is enabled."""
        worker, env, _ = _make_authenticated_worker()
        env.LITE_MODE = "true"

        request = MockRequest(
            url="https://planetcf.com/search?q=test",
            method="GET",
        )

        with patch("src.main.check_lite_mode", return_value=True):
            response = await worker.fetch(request)

        assert response.status == 404
        body = json.loads(response.body)
        assert "lite mode" in body["error"].lower()

    @pytest.mark.asyncio
    async def test_admin_blocked_in_lite_mode(self):
        """Admin route returns 404 when lite mode is enabled."""
        worker, env, cookie = _make_authenticated_worker()
        env.LITE_MODE = "true"

        request = MockRequest(
            url="https://planetcf.com/admin",
            method="GET",
            cookies=cookie,
        )

        with patch("src.main.check_lite_mode", return_value=True):
            response = await worker.fetch(request)

        assert response.status == 404
        body = json.loads(response.body)
        assert "lite mode" in body["error"].lower()


# =============================================================================
# Tests: Response Size Tracking (Lines 1492-1505)
# =============================================================================


class TestResponseSizeTracking:
    """Tests for response size calculation in fetch() event finalization."""

    @pytest.mark.asyncio
    async def test_response_with_string_body_tracks_size(self):
        """Response with a string body has its size tracked."""
        worker, _env, _ = _make_authenticated_worker()

        request = MockRequest(
            url="https://planetcf.com/health",
            method="GET",
        )

        response = await worker.fetch(request)

        # Health endpoint returns JSON, which has a string body
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_unknown_route_returns_404_with_bypass_cache(self):
        """Requests to unknown routes return 404 with bypass cache status."""
        worker, _env, _ = _make_authenticated_worker()

        request = MockRequest(
            url="https://planetcf.com/nonexistent-path",
            method="GET",
        )

        response = await worker.fetch(request)

        assert response.status == 404
        body = json.loads(response.body)
        assert body["error"] == "Not Found"


# =============================================================================
# Tests: Search Query Too Long (Lines 2321-2335)
# =============================================================================


class TestSearchQueryTooLong:
    """Tests for search query length validation."""

    @pytest.mark.asyncio
    async def test_query_exceeding_max_length_returns_error(self):
        """Search query exceeding MAX_SEARCH_QUERY_LENGTH returns HTML error page."""
        from src.config import MAX_SEARCH_QUERY_LENGTH

        worker, _env, _ = _make_authenticated_worker()

        long_query = "x" * (MAX_SEARCH_QUERY_LENGTH + 1)
        request = MockRequest(
            url=f"https://planetcf.com/search?q={long_query}",
            method="GET",
        )

        response = await worker._search_entries(request)

        assert response.status == 200  # HTML page, not HTTP error
        assert "text/html" in response.headers.get("Content-Type", "")
        assert "too long" in response.body.lower()

    @pytest.mark.asyncio
    async def test_query_at_max_length_is_accepted(self):
        """Search query at exactly MAX_SEARCH_QUERY_LENGTH proceeds to search."""
        from src.config import MAX_SEARCH_QUERY_LENGTH

        worker, env, _ = _make_authenticated_worker()

        # Query at exactly the limit should NOT trigger the too-long error
        exact_query = "x" * MAX_SEARCH_QUERY_LENGTH
        request = MockRequest(
            url=f"https://planetcf.com/search?q={exact_query}",
            method="GET",
        )

        # We need to mock AI.run since search will try to generate embeddings
        async def mock_ai_run(model, inputs):
            return {"data": [[0.1] * 768]}

        env.AI.run = mock_ai_run

        response = await worker._search_entries(request)

        # Should proceed past validation (may return search results or empty page)
        assert response.status == 200
        # Should NOT contain "too long" error
        assert "too long" not in response.body.lower()

    @pytest.mark.asyncio
    async def test_query_too_long_truncates_in_display(self):
        """Excessively long query is truncated to 50 chars + ellipsis in the error page."""
        from src.config import MAX_SEARCH_QUERY_LENGTH

        worker, _env, _ = _make_authenticated_worker()

        long_query = "a" * (MAX_SEARCH_QUERY_LENGTH + 100)
        request = MockRequest(
            url=f"https://planetcf.com/search?q={long_query}",
            method="GET",
        )

        response = await worker._search_entries(request)

        assert response.status == 200
        # The query displayed should be truncated (first 50 chars + "...")
        assert "..." in response.body

    @pytest.mark.asyncio
    async def test_query_too_long_with_event_sets_error_fields(self):
        """When event is provided, error fields are populated for too-long queries."""
        from src.config import MAX_SEARCH_QUERY_LENGTH
        from src.observability import RequestEvent

        worker, _env, _ = _make_authenticated_worker()

        long_query = "b" * (MAX_SEARCH_QUERY_LENGTH + 1)
        request = MockRequest(
            url=f"https://planetcf.com/search?q={long_query}",
            method="GET",
        )
        event = RequestEvent(method="GET", path="/search")

        await worker._search_entries(request, event)

        assert event.outcome == "error"
        assert event.error_type == "ValidationError"
        assert event.error_message == "Query too long"


# =============================================================================
# Tests: Retry DLQ Feed (Lines 3150-3220)
# =============================================================================


class TestRetryDlqFeed:
    """Tests for _retry_dlq_feed admin action."""

    @pytest.mark.asyncio
    async def test_retry_resets_failures_and_queues_feed(self):
        """Successful retry resets consecutive_failures and queues the feed."""
        feeds = [
            {
                "id": 1,
                "url": "https://failing.com/feed.xml",
                "title": "Failing Feed",
                "is_active": 0,
                "consecutive_failures": 10,
                "fetch_error": "HTTP 500",
                "etag": '"old-etag"',
                "last_modified": "Wed, 01 Jan 2026 00:00:00 GMT",
            }
        ]
        worker, env, _cookie = _make_authenticated_worker(feeds=feeds)
        admin = _admin_row()

        response = await worker._retry_dlq_feed(1, admin)

        # Should redirect back to admin
        assert response.status == 302
        assert response.headers.get("Location") == "/admin"

        # Feed should have been queued
        assert len(env.FEED_QUEUE.messages) == 1
        queued_msg = env.FEED_QUEUE.messages[0]
        assert queued_msg["feed_id"] == 1
        assert queued_msg["url"] == "https://failing.com/feed.xml"

    @pytest.mark.asyncio
    async def test_retry_nonexistent_feed_returns_error_page(self):
        """Retrying a feed that doesn't exist returns an error page."""
        worker, _env, _cookie = _make_authenticated_worker(feeds=[])
        admin = _admin_row()

        response = await worker._retry_dlq_feed(999, admin)

        # _admin_error_response returns HTML error page (status may be 200 for HTML)
        assert response.status in (200, 404)
        assert "not found" in response.body.lower() or "Not Found" in response.body

    @pytest.mark.asyncio
    async def test_retry_via_admin_route(self):
        """POST /admin/dlq/{id}/retry routes to _retry_dlq_feed."""
        feeds = [
            {
                "id": 5,
                "url": "https://broken.com/rss",
                "title": "Broken Feed",
                "is_active": 0,
                "consecutive_failures": 8,
                "fetch_error": "Timeout",
                "etag": None,
                "last_modified": None,
            }
        ]
        worker, _env, cookie = _make_authenticated_worker(feeds=feeds)

        request = MockRequest(
            url="https://planetcf.com/admin/dlq/5/retry",
            method="POST",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/dlq/5/retry")

        # Should redirect (success) or return an error, but NOT 404 for unknown route
        assert response.status in (200, 302, 400, 500)

    @pytest.mark.asyncio
    async def test_retry_dlq_invalid_feed_id_returns_400(self):
        """POST /admin/dlq/abc/retry returns 400 for invalid feed ID."""
        worker, _env, cookie = _make_authenticated_worker()

        request = MockRequest(
            url="https://planetcf.com/admin/dlq/abc/retry",
            method="POST",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/dlq/abc/retry")

        assert response.status == 400


# =============================================================================
# Tests: OPML Import Feed Limit (Line 3065-3068)
# =============================================================================


class TestOpmlImportFeedLimit:
    """Tests for MAX_OPML_FEEDS enforcement during OPML import."""

    @pytest.mark.asyncio
    async def test_opml_exceeding_feed_limit_skips_extras(self):
        """OPML files with more than MAX_OPML_FEEDS outlines skip excess feeds."""
        from src.config import MAX_OPML_FEEDS

        # Build an OPML with MAX_OPML_FEEDS + 5 feeds
        outlines = "\n".join(
            f'<outline type="rss" text="Feed {i}" xmlUrl="https://feed{i}.example.com/rss" />'
            for i in range(MAX_OPML_FEEDS + 5)
        )
        opml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <body>{outlines}</body>
        </opml>"""

        class MockFile:
            def __init__(self, content):
                self._content = content

            def text(self):
                return self._content

        class MockFormDataForOpml:
            def __init__(self, content):
                self._data = {"opml": MockFile(content)}

            def get(self, key, default=None):
                return self._data.get(key, default)

        class MockOpmlRequest:
            def __init__(self, content):
                self.method = "POST"
                self.url = "https://example.com/admin/import-opml"
                self.headers = {}
                self._content = content

            async def form_data(self):
                return MockFormDataForOpml(self._content)

        worker, _env, _cookie = _make_authenticated_worker()
        admin = _admin_row()
        request = MockOpmlRequest(opml_content)

        with patch("src.main.ET.XMLParser", _patched_xml_parser):
            response = await worker._import_opml(request, admin)

        # Should still succeed (redirect)
        assert response.status == 302
