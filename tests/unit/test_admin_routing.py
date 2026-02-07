# tests/unit/test_admin_routing.py
"""Unit tests for _handle_admin routing and _view_feed_health in src/main.py."""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock

import pytest

from src.main import Default
from tests.conftest import MockD1

# =============================================================================
# Mock Infrastructure
# =============================================================================


class MockRequest:
    """Mock HTTP request for admin routing tests."""

    def __init__(
        self,
        url: str = "https://planetcf.com/admin",
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
        return MockFormData(self._form_data)

    async def json(self):
        return self._json_data


class MockFormData:
    """Mock form data object."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockEnv:
    """Mock environment for admin routing tests."""

    def __init__(self, db=None, admins=None, feeds=None):
        data = {}
        if admins is not None:
            data["admins"] = admins
        if feeds is not None:
            data["feeds"] = feeds
        self.DB = db or MockD1(data)
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = MockQueue()
        self.DEAD_LETTER_QUEUE = MockQueue()
        self.PLANET_NAME = "Test Planet"
        self.PLANET_URL = "https://test.example.com"
        self.PLANET_DESCRIPTION = "Test description"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"


class MockQueue:
    """Mock Cloudflare Queue."""

    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)

    async def sendBatch(self, messages):
        for msg in messages:
            self.messages.append(msg.get("body", msg))


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


def _make_authenticated_worker(feeds=None, admins=None) -> tuple[Default, MockEnv, str]:
    """Create a worker with authenticated env and session cookie."""
    admin_list = admins or [_admin_row()]
    feed_list = feeds or []
    env = MockEnv(admins=admin_list, feeds=feed_list)
    session_cookie = _create_signed_session(env.SESSION_SECRET)
    worker = Default()
    worker.env = env
    return worker, env, session_cookie


# =============================================================================
# Tests: _handle_admin routing
# =============================================================================


class TestHandleAdminRouting:
    """Tests for admin request routing in _handle_admin."""

    @pytest.mark.asyncio
    async def test_get_admin_returns_dashboard(self):
        """GET /admin returns the admin dashboard."""
        worker, env, cookie = _make_authenticated_worker()
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
        worker, env, cookie = _make_authenticated_worker(feeds=feeds)
        request = MockRequest(url="https://planetcf.com/admin/feeds", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin/feeds")

        assert response.status == 200
        body = json.loads(response.body)
        assert "feeds" in body

    @pytest.mark.asyncio
    async def test_post_admin_feeds_triggers_add_feed(self):
        """POST /admin/feeds dispatches to _add_feed."""
        worker, env, cookie = _make_authenticated_worker()
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
        worker, env, cookie = _make_authenticated_worker(feeds=feeds)
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
        worker, env, cookie = _make_authenticated_worker()
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
        worker, env, cookie = _make_authenticated_worker()
        request = MockRequest(url="https://planetcf.com/admin/dlq", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin/dlq")

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_get_admin_audit_returns_response(self):
        """GET /admin/audit returns audit log view."""
        worker, env, cookie = _make_authenticated_worker()
        request = MockRequest(url="https://planetcf.com/admin/audit", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin/audit")

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_get_admin_health_returns_response(self):
        """GET /admin/health returns feed health dashboard."""
        worker, env, cookie = _make_authenticated_worker()
        request = MockRequest(url="https://planetcf.com/admin/health", method="GET", cookies=cookie)

        response = await worker._handle_admin(request, "/admin/health")

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_unknown_admin_path_returns_404(self):
        """Unknown admin path returns 404."""
        worker, env, cookie = _make_authenticated_worker()
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
        env = MockEnv(admins=[_admin_row()])
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
        env = MockEnv(admins=[_admin_row()])
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
        env = MockEnv(admins=[])  # Empty admin list
        session_cookie = _create_signed_session(env.SESSION_SECRET)
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
        env = MockEnv(feeds=feeds)
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
        env = MockEnv(feeds=[])
        worker = Default()
        worker.env = env

        response = await worker._view_feed_health()

        assert response.status == 200
        assert "text/html" in response.headers.get("Content-Type", "")

    @pytest.mark.asyncio
    async def test_returns_proper_response_format(self):
        """Response is HTML with no-cache headers."""
        env = MockEnv(feeds=[])
        worker = Default()
        worker.env = env

        response = await worker._view_feed_health()

        assert response.status == 200
        assert "text/html" in response.headers.get("Content-Type", "")
        # Admin pages should not be cached
        cache = response.headers.get("Cache-Control", "")
        assert "no-store" in cache or "max-age=0" in cache or "no-cache" in cache
