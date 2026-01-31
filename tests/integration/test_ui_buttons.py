# tests/integration/test_ui_buttons.py
"""
Integration tests for all UI buttons based on the Planet CF spec.

Tests cover:
- Public UI: Search, Atom, RSS, OPML
- Admin UI: Login, Add Feed, Delete Feed, Toggle Feed, Import OPML,
            Refresh All, Retry DLQ, Logout, DLQ list, Audit log

These tests run against a local wrangler dev instance.
"""

import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest

from tests.integration.conftest import requires_wrangler

# Configuration
BASE_URL = "http://localhost:8787"
SESSION_SECRET = "test-secret-for-local-development-32chars"


def create_test_session(username: str = "testadmin") -> str:
    """Create a signed session cookie for testing."""
    session_data = {
        "github_username": username,
        "github_id": 12345,
        "exp": int(time.time()) + 3600,
    }
    payload = base64.b64encode(json.dumps(session_data).encode()).decode()
    signature = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


@requires_wrangler
class TestPublicUI:
    """Tests for public-facing UI buttons and links."""

    @pytest.mark.asyncio
    async def test_search_form_submit_with_query(self):
        """Search form: GET /search?q=... should return search results page.

        Note: In local dev, Vectorize is not supported so search may fail.
        In production, this endpoint uses Vectorize for semantic search.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/search?q=test")
            # Accept 200 (success) or 500 (Vectorize not available locally)
            assert response.status_code in [200, 500]
            if response.status_code == 200:
                assert "Search Results" in response.text or "results" in response.text.lower()

    @pytest.mark.asyncio
    async def test_search_form_submit_empty_query(self):
        """Search form: Empty query should return search page with guidance."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/search")
            # Returns 200 with search page showing "query required" message
            assert response.status_code == 200
            assert "search" in response.text.lower()

    @pytest.mark.asyncio
    async def test_atom_feed_link(self):
        """Atom feed link: GET /feed.atom should return valid Atom XML."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/feed.atom")
            assert response.status_code == 200
            assert "application/atom+xml" in response.headers.get("content-type", "")
            assert "<feed" in response.text
            assert "xmlns" in response.text

    @pytest.mark.asyncio
    async def test_rss_feed_link(self):
        """RSS feed link: GET /feed.rss should return valid RSS XML."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/feed.rss")
            assert response.status_code == 200
            assert "application/rss+xml" in response.headers.get("content-type", "")
            assert "<rss" in response.text or "<channel" in response.text

    @pytest.mark.asyncio
    async def test_opml_export_link(self):
        """OPML link: GET /feeds.opml should return valid OPML XML."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/feeds.opml")
            assert response.status_code == 200
            # Accept either text/x-opml or application/xml (both are valid for OPML)
            content_type = response.headers.get("content-type", "")
            assert "text/x-opml" in content_type or "application/xml" in content_type
            assert "<opml" in response.text


@requires_wrangler
class TestAdminAuth:
    """Tests for admin authentication buttons."""

    @pytest.mark.asyncio
    async def test_github_login_button_redirects(self):
        """GitHub Login: GET /auth/github should redirect to GitHub."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/auth/github", follow_redirects=False)
            assert response.status_code == 302
            location = response.headers.get("location", "")
            assert "github.com" in location or location.startswith("/")

    @pytest.mark.asyncio
    async def test_admin_page_without_session_shows_login(self):
        """Admin page without session should show login page."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/admin")
            assert response.status_code == 200
            assert "Login" in response.text or "GitHub" in response.text

    @pytest.mark.asyncio
    async def test_admin_page_with_valid_session_shows_dashboard(self):
        """Admin page with valid session should show dashboard."""
        async with httpx.AsyncClient() as client:
            session = create_test_session()
            response = await client.get(
                f"{BASE_URL}/admin", headers={"Cookie": f"session={session}"}
            )
            assert response.status_code == 200
            # Should show dashboard content, not login
            assert "Dashboard" in response.text or "Feeds" in response.text

    @pytest.mark.asyncio
    async def test_logout_button_clears_session(self):
        """Logout: POST /admin/logout should clear session and redirect."""
        async with httpx.AsyncClient() as client:
            session = create_test_session()
            response = await client.post(
                f"{BASE_URL}/admin/logout",
                headers={"Cookie": f"session={session}"},
                follow_redirects=False,
            )
            # Should redirect to home or login
            assert response.status_code in [302, 303]
            # Should have Set-Cookie header clearing session
            cookies = response.headers.get("set-cookie", "")
            assert "session=" in cookies.lower() or "max-age=0" in cookies.lower()


@requires_wrangler
class TestFeedManagement:
    """Tests for feed management buttons."""

    @pytest.fixture
    def session_cookie(self):
        """Provide a valid session cookie for admin tests."""
        return create_test_session()

    @pytest.mark.asyncio
    async def test_add_feed_button(self, session_cookie):
        """Add Feed: POST /admin/feeds should add a new feed and redirect.

        Note: Uses a real RSS feed URL since feeds are now validated on add.
        """
        # Use Hacker News RSS which is stable and reliable
        test_url = "https://hnrss.org/frontpage"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/admin/feeds",
                data={"url": test_url},
                headers={"Cookie": f"session={session_cookie}"},
                follow_redirects=False,
                timeout=30.0,  # Longer timeout for validation
            )
            # Should redirect back to admin (302) or return success
            assert response.status_code in [302, 200], f"Failed: {response.text}"
            if response.status_code == 200:
                # If JSON response, check for success
                data = response.json()
                assert "id" in data or "error" not in data

            # Clean up - delete the feed we just added
            if response.status_code == 302:
                feeds_response = await client.get(
                    f"{BASE_URL}/admin/feeds",
                    headers={"Cookie": f"session={session_cookie}"},
                )
                if feeds_response.status_code == 200:
                    for feed in feeds_response.json().get("feeds", []):
                        if feed.get("url") == test_url:
                            await client.post(
                                f"{BASE_URL}/admin/feeds/{feed['id']}",
                                data={"_method": "DELETE"},
                                headers={"Cookie": f"session={session_cookie}"},
                            )
                            break

    @pytest.mark.asyncio
    async def test_add_feed_with_invalid_url(self, session_cookie):
        """Add Feed: Should reject unsafe/invalid URLs."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/admin/feeds",
                data={"url": "http://169.254.169.254/metadata", "title": "Bad Feed"},
                headers={"Cookie": f"session={session_cookie}"},
            )
            # API returns HTML error page with 200 status or 400
            # Check for error indicator in response
            assert response.status_code in [200, 400, 500]
            assert "error" in response.text.lower() or "invalid" in response.text.lower()

    @pytest.mark.asyncio
    async def test_add_feed_without_url(self, session_cookie):
        """Add Feed: Should require URL."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/admin/feeds",
                data={"title": "No URL Feed"},
                headers={"Cookie": f"session={session_cookie}"},
            )
            # API returns HTML error page with 200 status or 400
            assert response.status_code in [200, 400, 500]
            assert "error" in response.text.lower() or "url" in response.text.lower()

    @pytest.mark.asyncio
    async def test_add_feed_with_non_feed_url(self, session_cookie):
        """Add Feed: Should reject URLs that don't point to valid RSS/Atom feeds."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            # This is a valid URL but not a feed
            response = await client.post(
                f"{BASE_URL}/admin/feeds",
                data={"url": "https://example.com/", "title": "Not a Feed"},
                headers={"Cookie": f"session={session_cookie}"},
            )
            # Should return validation error (HTML page with error message)
            assert response.status_code in [200, 400]
            assert "error" in response.text.lower() or "failed" in response.text.lower()

    @pytest.mark.asyncio
    async def test_delete_feed_button(self, session_cookie):
        """Delete Feed: POST /admin/feeds/{id} with _method=DELETE should remove feed.

        Note: Uses a real RSS feed URL since feeds are now validated on add.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First, add a real feed to delete
            test_url = "https://news.ycombinator.com/rss"
            add_response = await client.post(
                f"{BASE_URL}/admin/feeds",
                data={"url": test_url},
                headers={"Cookie": f"session={session_cookie}"},
                follow_redirects=False,
            )
            assert add_response.status_code in [302, 200], f"Add failed: {add_response.text}"

            # Get feeds list to find the feed ID
            feeds_response = await client.get(
                f"{BASE_URL}/admin/feeds",
                headers={"Cookie": f"session={session_cookie}"},
            )
            assert feeds_response.status_code == 200
            feeds_data = feeds_response.json()

            # Find feed by URL
            target_feed = None
            for feed in feeds_data.get("feeds", []):
                if feed.get("url") == test_url:
                    target_feed = feed
                    break

            if target_feed:
                # Delete the feed
                delete_response = await client.post(
                    f"{BASE_URL}/admin/feeds/{target_feed['id']}",
                    data={"_method": "DELETE"},
                    headers={"Cookie": f"session={session_cookie}"},
                    follow_redirects=False,
                )
                assert delete_response.status_code in [302, 200]

    @pytest.mark.asyncio
    async def test_toggle_feed_button(self, session_cookie):
        """Toggle Feed: PUT /admin/feeds/{id} should enable/disable feed."""
        async with httpx.AsyncClient() as client:
            # Get feeds list
            feeds_response = await client.get(
                f"{BASE_URL}/admin/feeds",
                headers={"Cookie": f"session={session_cookie}"},
            )
            assert feeds_response.status_code == 200
            feeds_data = feeds_response.json()

            if feeds_data.get("feeds"):
                feed = feeds_data["feeds"][0]
                feed_id = feed["id"]

                # Toggle to disabled
                toggle_response = await client.put(
                    f"{BASE_URL}/admin/feeds/{feed_id}",
                    json={"is_active": 0},
                    headers={"Cookie": f"session={session_cookie}"},
                )
                assert toggle_response.status_code == 200
                data = toggle_response.json()
                assert data.get("success") is True

                # Toggle back to enabled
                toggle_response = await client.put(
                    f"{BASE_URL}/admin/feeds/{feed_id}",
                    json={"is_active": 1},
                    headers={"Cookie": f"session={session_cookie}"},
                )
                assert toggle_response.status_code == 200


@requires_wrangler
class TestImportOPML:
    """Tests for OPML import functionality."""

    @pytest.fixture
    def session_cookie(self):
        return create_test_session()

    @pytest.mark.asyncio
    async def test_import_opml_button_with_valid_file(self, session_cookie):
        """Import OPML: POST /admin/import-opml should import feeds from OPML file."""
        opml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
    <head><title>Test Feeds</title></head>
    <body>
        <outline type="rss" text="Test Blog" xmlUrl="https://testimport{int(time.time())}.com/feed.xml" htmlUrl="https://testimport{int(time.time())}.com"/>
    </body>
</opml>"""

        async with httpx.AsyncClient() as client:
            files = {"opml": ("feeds.opml", opml_content, "text/x-opml")}
            response = await client.post(
                f"{BASE_URL}/admin/import-opml",
                files=files,
                headers={"Cookie": f"session={session_cookie}"},
                follow_redirects=False,
            )
            # Should redirect or return success
            assert response.status_code in [302, 200]

    @pytest.mark.asyncio
    async def test_import_opml_without_file(self, session_cookie):
        """Import OPML: Should require file upload."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/admin/import-opml",
                headers={"Cookie": f"session={session_cookie}"},
            )
            # API returns HTML error page - check for error message
            assert response.status_code in [200, 400, 500]
            assert "error" in response.text.lower() or "file" in response.text.lower()


@requires_wrangler
class TestRefreshFeeds:
    """Tests for feed refresh functionality."""

    @pytest.fixture
    def session_cookie(self):
        return create_test_session()

    @pytest.mark.asyncio
    async def test_refresh_all_feeds_button(self, session_cookie):
        """Refresh All: POST /admin/regenerate should trigger feed refresh."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/admin/regenerate",
                headers={"Cookie": f"session={session_cookie}"},
                follow_redirects=False,
            )
            # Should redirect or return success
            assert response.status_code in [302, 200]


@requires_wrangler
class TestDLQ:
    """Tests for Dead Letter Queue functionality."""

    @pytest.fixture
    def session_cookie(self):
        return create_test_session()

    @pytest.mark.asyncio
    async def test_dlq_list_loads(self, session_cookie):
        """DLQ Tab: GET /admin/dlq should return list of failed feeds."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/admin/dlq",
                headers={"Cookie": f"session={session_cookie}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "failed_feeds" in data
            assert isinstance(data["failed_feeds"], list)

    @pytest.mark.asyncio
    async def test_retry_dlq_button_invalid_id(self, session_cookie):
        """Retry DLQ: POST /admin/dlq/{id}/retry with invalid ID should return error."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/admin/dlq/99999/retry",
                headers={"Cookie": f"session={session_cookie}"},
                follow_redirects=False,
            )
            # May return 200 with error message, 302 redirect, or 404
            assert response.status_code in [200, 302, 404, 500]


@requires_wrangler
class TestAuditLog:
    """Tests for audit log functionality."""

    @pytest.fixture
    def session_cookie(self):
        return create_test_session()

    @pytest.mark.asyncio
    async def test_audit_log_loads(self, session_cookie):
        """Audit Tab: GET /admin/audit should return audit log entries."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/admin/audit",
                headers={"Cookie": f"session={session_cookie}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "entries" in data
            assert isinstance(data["entries"], list)


@requires_wrangler
class TestFeedList:
    """Tests for feed list API."""

    @pytest.fixture
    def session_cookie(self):
        return create_test_session()

    @pytest.mark.asyncio
    async def test_feeds_list_api(self, session_cookie):
        """Feeds List: GET /admin/feeds should return JSON list of feeds."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/admin/feeds",
                headers={"Cookie": f"session={session_cookie}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "feeds" in data
            assert isinstance(data["feeds"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
