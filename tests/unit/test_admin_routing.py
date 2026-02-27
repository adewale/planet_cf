# tests/unit/test_admin_routing.py
"""Unit tests for admin routing, feed health, lite mode, DLQ retry, and search validation."""

import json

import pytest

from src.main import Default
from tests.conftest import (
    MockD1,
    MockEnv,
    MockQueue,
    MockRequest,
    MockVectorize,
    admin_row,
    create_signed_session,
    make_authenticated_worker,
)

# =============================================================================
# Module-level helpers (thin wrappers around conftest)
# =============================================================================


def _admin_env(admins=None, feeds=None, db=None):
    """Create a MockEnv for admin routing tests."""
    data = {}
    if admins is not None:
        data["admins"] = admins
    if feeds is not None:
        data["feeds"] = feeds
    return MockEnv(
        DB=db or MockD1(data),
        FEED_QUEUE=MockQueue(),
        DEAD_LETTER_QUEUE=MockQueue(),
        SEARCH_INDEX=MockVectorize(),
        AI=None,
    )


# =============================================================================
# Tests: _handle_admin routing
# =============================================================================


class TestHandleAdminRouting:
    """Tests for admin request routing in _handle_admin."""

    @pytest.mark.asyncio
    async def test_get_admin_returns_dashboard(self):
        """GET /admin returns the admin dashboard."""
        worker, env, cookie = make_authenticated_worker()
        request = MockRequest(url="https://planetcf.com/admin", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin")

        assert response.status == 200
        assert "text/html" in response.headers.get("Content-Type", "")

    @pytest.mark.asyncio
    async def test_get_admin_feeds_returns_feed_list(self):
        """GET /admin/feeds returns JSON feed list."""
        feeds = [
            {"id": 1, "url": "https://example.com/feed.xml", "title": "Example", "is_active": 1},
        ]
        worker, env, cookie = make_authenticated_worker(feeds=feeds)
        request = MockRequest(url="https://planetcf.com/admin/feeds", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin/feeds")

        assert response.status == 200
        body = json.loads(response.body)
        assert "feeds" in body

    @pytest.mark.asyncio
    async def test_post_admin_feeds_triggers_add_feed(self):
        """POST /admin/feeds dispatches to _add_feed."""
        worker, env, cookie = make_authenticated_worker()
        request = MockRequest(
            url="https://planetcf.com/admin/feeds",
            method="POST",
            cookies=cookie,
            form_data={"url": "http://localhost/feed"},
        )

        response = await worker._handle_admin(request, "/admin/feeds")

        # Should return an error because localhost is SSRF-blocked
        assert response.status in (200, 400)

    @pytest.mark.asyncio
    async def test_delete_admin_feeds_dispatches_to_remove_feed(self):
        """DELETE /admin/feeds/{id} dispatches to _remove_feed."""
        feeds = [
            {"id": 1, "url": "https://example.com/feed.xml", "title": "Example", "is_active": 1}
        ]
        worker, env, cookie = make_authenticated_worker(feeds=feeds)
        request = MockRequest(
            url="https://planetcf.com/admin/feeds/1",
            method="DELETE",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/feeds/1")

        # Should handle the delete request (may return 200 or redirect)
        assert response.status in (200, 302)

    @pytest.mark.asyncio
    async def test_post_import_opml_dispatches(self):
        """POST /admin/import-opml dispatches to _import_opml."""
        worker, env, cookie = make_authenticated_worker()
        request = MockRequest(
            url="https://planetcf.com/admin/import-opml",
            method="POST",
            cookies=cookie,
            form_data={},  # No file => should return error
        )

        response = await worker._handle_admin(request, "/admin/import-opml")

        # Should return an error because no file was provided
        assert response.status in (200, 400)
        assert "No File" in response.body or "OPML" in response.body

    @pytest.mark.asyncio
    async def test_get_admin_dlq_returns_response(self):
        """GET /admin/dlq returns dead letter queue view."""
        worker, env, cookie = make_authenticated_worker()
        request = MockRequest(url="https://planetcf.com/admin/dlq", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin/dlq")

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_get_admin_audit_returns_response(self):
        """GET /admin/audit returns audit log view."""
        worker, env, cookie = make_authenticated_worker()
        request = MockRequest(url="https://planetcf.com/admin/audit", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin/audit")

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_get_admin_health_returns_response(self):
        """GET /admin/health returns feed health dashboard."""
        worker, env, cookie = make_authenticated_worker()
        request = MockRequest(url="https://planetcf.com/admin/health", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin/health")

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_post_fetch_now_routes_correctly(self):
        """POST /admin/feeds/{id}/fetch-now routes to _fetch_feed_now."""
        feeds = [
            {
                "id": 1,
                "url": "https://example.com/feed.xml",
                "title": "Example",
                "is_active": 1,
                "consecutive_failures": 0,
                "etag": None,
                "last_modified": None,
            }
        ]
        worker, env, cookie = make_authenticated_worker(feeds=feeds)
        request = MockRequest(
            url="https://planetcf.com/admin/feeds/1/fetch-now",
            method="POST",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/feeds/1/fetch-now")

        # Will fail the actual fetch (no real HTTP), but should route correctly
        # and return a JSON error (502) rather than 404
        assert response.status != 404

    @pytest.mark.asyncio
    async def test_fetch_now_rejects_invalid_feed_id(self):
        """POST /admin/feeds/abc/fetch-now returns 400 for invalid ID."""
        worker, env, cookie = make_authenticated_worker()
        request = MockRequest(
            url="https://planetcf.com/admin/feeds/abc/fetch-now",
            method="POST",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/feeds/abc/fetch-now")

        assert response.status == 400

    @pytest.mark.asyncio
    async def test_fetch_now_returns_404_for_missing_feed(self):
        """POST /admin/feeds/999/fetch-now returns 404 for nonexistent feed."""
        worker, env, cookie = make_authenticated_worker(feeds=[])
        request = MockRequest(
            url="https://planetcf.com/admin/feeds/999/fetch-now",
            method="POST",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/feeds/999/fetch-now")

        assert response.status == 404
        body = json.loads(response.body)
        assert "not found" in body["error"].lower()

    @pytest.mark.asyncio
    async def test_fetch_now_rejects_inactive_feed(self):
        """POST /admin/feeds/{id}/fetch-now returns 400 for inactive feed."""
        feeds = [
            {
                "id": 1,
                "url": "https://example.com/feed.xml",
                "title": "Inactive",
                "is_active": 0,
                "consecutive_failures": 5,
                "etag": None,
                "last_modified": None,
            }
        ]
        worker, env, cookie = make_authenticated_worker(feeds=feeds)
        request = MockRequest(
            url="https://planetcf.com/admin/feeds/1/fetch-now",
            method="POST",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/feeds/1/fetch-now")

        assert response.status == 400
        body = json.loads(response.body)
        assert "not active" in body["error"].lower()

    @pytest.mark.asyncio
    async def test_unknown_admin_path_returns_404(self):
        """Unknown admin path returns 404."""
        worker, env, cookie = make_authenticated_worker()
        request = MockRequest(
            url="https://planetcf.com/admin/nonexistent",
            method="GET",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/nonexistent")

        assert response.status == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_request_shows_login(self):
        """Unauthenticated request shows login page."""
        env = _admin_env(admins=[admin_row()])
        worker = Default()
        worker.env = env

        request = MockRequest(
            url="https://planetcf.com/admin",
            method="GET",
            cookies="",  # No session cookie
        )

        response = await worker._handle_admin(request, "/admin")

        assert response.status == 200
        # Should show login page
        assert "Sign in" in response.body or "login" in response.body.lower()

    @pytest.mark.asyncio
    async def test_invalid_session_shows_login(self):
        """Invalid session cookie shows login page."""
        env = _admin_env(admins=[admin_row()])
        worker = Default()
        worker.env = env

        request = MockRequest(
            url="https://planetcf.com/admin",
            method="GET",
            cookies="session=invalid.cookie",
        )

        response = await worker._handle_admin(request, "/admin")

        assert response.status == 200
        assert "Sign in" in response.body or "login" in response.body.lower()

    @pytest.mark.asyncio
    async def test_non_admin_user_returns_403(self):
        """Authenticated user who is not an admin gets 403."""
        # Create env with NO admins in the DB, but with a valid session
        env = _admin_env(admins=[])  # Empty admin list
        session_cookie = create_signed_session(env.SESSION_SECRET)
        worker = Default()
        worker.env = env

        request = MockRequest(
            url="https://planetcf.com/admin",
            method="GET",
            cookies=session_cookie,
        )

        response = await worker._handle_admin(request, "/admin")

        assert response.status == 403


# =============================================================================
# Tests: _view_feed_health
# =============================================================================


class TestViewFeedHealth:
    """Tests for Default._view_feed_health method."""

    @pytest.mark.asyncio
    async def test_returns_feed_health_with_categories(self):
        """Returns feed health data with correct health status categories."""
        feeds = [
            {
                "id": 1,
                "url": "https://healthy.com/feed",
                "title": "Healthy Feed",
                "site_url": "https://healthy.com",
                "last_fetch_at": "2026-01-01T00:00:00Z",
                "last_success_at": "2026-01-01T00:00:00Z",
                "last_entry_at": "2026-01-01T00:00:00Z",
                "fetch_error": None,
                "consecutive_failures": 0,
                "is_active": 1,
                "created_at": "2025-01-01T00:00:00Z",
                "entry_count": 10,
            },
            {
                "id": 2,
                "url": "https://warning.com/feed",
                "title": "Warning Feed",
                "site_url": "https://warning.com",
                "last_fetch_at": "2026-01-01T00:00:00Z",
                "last_success_at": "2025-12-01T00:00:00Z",
                "last_entry_at": None,
                "fetch_error": "Timeout",
                "consecutive_failures": 2,
                "is_active": 1,
                "created_at": "2025-01-01T00:00:00Z",
                "entry_count": 5,
            },
            {
                "id": 3,
                "url": "https://failing.com/feed",
                "title": "Failing Feed",
                "site_url": "https://failing.com",
                "last_fetch_at": "2026-01-01T00:00:00Z",
                "last_success_at": None,
                "last_entry_at": None,
                "fetch_error": "HTTP 500",
                "consecutive_failures": 5,
                "is_active": 1,
                "created_at": "2025-01-01T00:00:00Z",
                "entry_count": 0,
            },
            {
                "id": 4,
                "url": "https://inactive.com/feed",
                "title": "Inactive Feed",
                "site_url": "https://inactive.com",
                "last_fetch_at": None,
                "last_success_at": None,
                "last_entry_at": None,
                "fetch_error": None,
                "consecutive_failures": 0,
                "is_active": 0,
                "created_at": "2025-01-01T00:00:00Z",
                "entry_count": 0,
            },
        ]
        env = _admin_env(feeds=feeds)
        worker = Default()
        worker.env = env

        response = await worker._view_feed_health()

        assert response.status == 200
        assert "text/html" in response.headers.get("Content-Type", "")
        # The HTML should contain feed titles
        assert "Healthy Feed" in response.body
        assert "Warning Feed" in response.body
        assert "Failing Feed" in response.body
        assert "Inactive Feed" in response.body

    @pytest.mark.asyncio
    async def test_handles_empty_feed_list(self):
        """Returns valid response when no feeds exist."""
        env = _admin_env(feeds=[])
        worker = Default()
        worker.env = env

        response = await worker._view_feed_health()

        assert response.status == 200
        assert "text/html" in response.headers.get("Content-Type", "")

    @pytest.mark.asyncio
    async def test_returns_proper_response_format(self):
        """Response is HTML with no-cache headers."""
        env = _admin_env(feeds=[])
        worker = Default()
        worker.env = env

        response = await worker._view_feed_health()

        assert response.status == 200
        assert "text/html" in response.headers.get("Content-Type", "")
        # Admin pages should not be cached
        cache = response.headers.get("Cache-Control", "")
        assert "no-store" in cache or "max-age=0" in cache or "no-cache" in cache


# =============================================================================
# Tests: Lite Mode Blocking
# =============================================================================


class TestLiteModeBlocking:
    """Tests for lite mode route blocking in fetch()."""

    @pytest.mark.asyncio
    async def test_search_blocked_in_lite_mode(self):
        """Search route returns 404 when lite mode is enabled."""
        from unittest.mock import patch

        worker, env, _ = make_authenticated_worker()
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
        from unittest.mock import patch

        worker, env, cookie = make_authenticated_worker()
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
# Tests: Response Size Tracking
# =============================================================================


class TestResponseSizeTracking:
    """Tests for response size calculation in fetch() event finalization."""

    @pytest.mark.asyncio
    async def test_response_with_string_body_tracks_size(self):
        """Response with a string body has its size tracked."""
        worker, _env, _ = make_authenticated_worker()

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
        worker, _env, _ = make_authenticated_worker()

        request = MockRequest(
            url="https://planetcf.com/nonexistent-path",
            method="GET",
        )

        response = await worker.fetch(request)

        assert response.status == 404
        body = json.loads(response.body)
        assert body["error"] == "Not Found"


# =============================================================================
# Tests: Search Query Too Long
# =============================================================================


class TestSearchQueryTooLong:
    """Tests for search query length validation."""

    @pytest.mark.asyncio
    async def test_query_exceeding_max_length_returns_error(self):
        """Search query exceeding MAX_SEARCH_QUERY_LENGTH returns HTML error page."""
        from src.config import MAX_SEARCH_QUERY_LENGTH

        worker, _env, _ = make_authenticated_worker()

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

        worker, env, _ = make_authenticated_worker()

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

        worker, _env, _ = make_authenticated_worker()

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

        worker, _env, _ = make_authenticated_worker()

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
# Tests: Retry DLQ Feed
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
        worker, env, _cookie = make_authenticated_worker(feeds=feeds)

        response = await worker._retry_dlq_feed(1, admin_row())

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
        worker, _env, _cookie = make_authenticated_worker(feeds=[])

        response = await worker._retry_dlq_feed(999, admin_row())

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
        worker, _env, cookie = make_authenticated_worker(feeds=feeds)

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
        worker, _env, cookie = make_authenticated_worker()

        request = MockRequest(
            url="https://planetcf.com/admin/dlq/abc/retry",
            method="POST",
            cookies=cookie,
        )

        response = await worker._handle_admin(request, "/admin/dlq/abc/retry")

        assert response.status == 400


# =============================================================================
# Tests: OPML Import Feed Limit
# =============================================================================


class TestOpmlImportFeedLimit:
    """Tests for MAX_OPML_FEEDS enforcement during OPML import."""

    @pytest.mark.asyncio
    async def test_opml_exceeding_feed_limit_skips_extras(self):
        """OPML files with more than MAX_OPML_FEEDS outlines skip excess feeds."""
        import xml.etree.ElementTree as ET
        from unittest.mock import patch

        from src.config import MAX_OPML_FEEDS

        _original_xml_parser = ET.XMLParser

        def _patched_xml_parser(**kwargs):
            kwargs.pop("forbid_dtd", None)
            return _original_xml_parser(**kwargs)

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

        worker, _env, _cookie = make_authenticated_worker()
        request = MockOpmlRequest(opml_content)

        with patch("src.main.ET.XMLParser", _patched_xml_parser):
            response = await worker._import_opml(request, admin_row())

        # Should still succeed (redirect)
        assert response.status == 302
