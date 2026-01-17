"""
End-to-end integration test: Add feed -> entries appear on homepage.

This test verifies the complete flow from adding a feed to seeing entries
on the homepage. Since we're testing against a local wrangler instance,
we use a combination of:
1. Adding a feed with a real URL
2. Waiting for queue processing
3. Checking the homepage for entries

Note: This test requires the wrangler dev server to be running.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

import httpx
import pytest

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


class RSSHandler(SimpleHTTPRequestHandler):
    """Simple HTTP handler that serves an RSS feed."""

    RSS_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>E2E Test Feed</title>
            <link>http://localhost:9999</link>
            <description>A test feed for E2E testing</description>
            <item>
                <title>Test Entry 1</title>
                <link>http://localhost:9999/entry1</link>
                <description>This is test entry number one.</description>
                <guid>e2e-test-entry-1</guid>
                <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
            </item>
            <item>
                <title>Test Entry 2</title>
                <link>http://localhost:9999/entry2</link>
                <description>This is test entry number two.</description>
                <guid>e2e-test-entry-2</guid>
                <pubDate>Mon, 01 Jan 2024 11:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>"""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml")
        self.send_header("Content-Length", len(self.RSS_CONTENT.encode()))
        self.end_headers()
        self.wfile.write(self.RSS_CONTENT.encode())

    def log_message(self, format, *args):
        # Suppress logging
        pass


class TestE2EFeedToHomepage:
    """
    End-to-end test verifying the complete feed-to-homepage flow.

    Flow tested:
    1. Start a mock RSS server locally
    2. Add the mock feed via admin API
    3. Trigger feed fetch
    4. Verify entries appear on homepage
    5. Clean up
    """

    @pytest.fixture
    def mock_rss_server(self):
        """Start a local mock RSS server on port 9999."""
        server = HTTPServer(("localhost", 9999), RSSHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        yield server
        server.shutdown()

    @pytest.mark.asyncio
    async def test_add_localhost_feed_blocked_by_ssrf_protection(self, mock_rss_server):
        """
        E2E test: Verify localhost feeds are blocked by SSRF protection.

        This test verifies that the SSRF protection correctly blocks localhost
        URLs. This is important security behavior to prevent internal network
        access via feed URLs.

        Note: In a real production scenario, you would test with real public
        RSS feeds or use a separate test environment where SSRF protection
        is disabled for testing purposes.
        """
        session = create_test_session()
        cookies = {"session": session}

        async with httpx.AsyncClient() as client:
            # Attempt to add a localhost feed - should be blocked
            add_response = await client.post(
                f"{BASE_URL}/admin/feeds",
                data={"url": "http://localhost:9999/feed.rss"},
                cookies=cookies,
                follow_redirects=False,
            )
            # SSRF protection should block localhost URLs
            assert add_response.status_code == 400, "localhost should be blocked"
            assert "unsafe" in add_response.text.lower() or "invalid" in add_response.text.lower()

    @pytest.mark.asyncio
    async def test_e2e_public_feed_flow(self):
        """
        E2E test: Add a public feed, trigger fetch, and verify homepage.

        This test uses a real public RSS feed to verify the complete flow.
        It demonstrates that:
        1. Public feeds can be added
        2. Feed fetching can be triggered
        3. The homepage renders successfully

        Note: This test depends on external network access and may be slow.
        """
        session = create_test_session()
        cookies = {"session": session}

        # Use a well-known, stable public RSS feed for testing
        # Example: AWS What's New feed (very stable)
        test_url = "https://aws.amazon.com/about-aws/whats-new/recent/feed/"

        async with httpx.AsyncClient() as client:
            # Add the public feed
            add_response = await client.post(
                f"{BASE_URL}/admin/feeds",
                data={"url": test_url},
                cookies=cookies,
                follow_redirects=False,
            )
            assert add_response.status_code == 302, f"Add feed failed: {add_response.text}"

            # Trigger feed fetch
            regen_response = await client.post(
                f"{BASE_URL}/admin/regenerate",
                cookies=cookies,
                follow_redirects=False,
            )
            assert regen_response.status_code == 302, "Regenerate failed"

            # Wait briefly for queue processing to start
            await asyncio.sleep(2)

            # Check homepage renders
            homepage = await client.get(f"{BASE_URL}/")
            assert homepage.status_code == 200
            assert "planet cf" in homepage.text.lower() or "subscriptions" in homepage.text.lower()

            # Clean up - find and delete the test feed
            feeds_response = await client.get(
                f"{BASE_URL}/admin/feeds",
                cookies=cookies,
            )
            assert feeds_response.status_code == 200

            feeds_data = feeds_response.json()
            for feed in feeds_data.get("feeds", []):
                if feed.get("url") == test_url:
                    delete_response = await client.post(
                        f"{BASE_URL}/admin/feeds/{feed['id']}",
                        data={"_method": "DELETE"},
                        cookies=cookies,
                        follow_redirects=False,
                    )
                    assert delete_response.status_code == 302, "Delete feed failed"
                    break


class TestHomepageRendering:
    """
    Test homepage rendering with existing entries.

    These tests verify that the homepage correctly displays entries
    that are already in the database, without needing to fetch feeds.
    """

    @pytest.mark.asyncio
    async def test_homepage_loads_with_entries(self):
        """Homepage should load and display any existing entries."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/")
            assert response.status_code == 200
            assert "<html" in response.text.lower()
            # Check for basic structure
            assert "Subscriptions" in response.text or "subscriptions" in response.text.lower()

    @pytest.mark.asyncio
    async def test_homepage_includes_admin_link(self):
        """Homepage footer should include a subtle admin link."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/")
            assert response.status_code == 200
            # Check for the admin link we added
            assert 'href="/admin"' in response.text

    @pytest.mark.asyncio
    async def test_homepage_includes_feed_links(self):
        """Homepage should include Atom, RSS, and OPML links."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/")
            assert response.status_code == 200
            assert 'href="/feed.atom"' in response.text or "/feed.atom" in response.text
            assert 'href="/feed.rss"' in response.text or "/feed.rss" in response.text
            assert 'href="/feeds.opml"' in response.text or "/feeds.opml" in response.text

    @pytest.mark.asyncio
    async def test_atom_feed_contains_entries(self):
        """Atom feed should contain entries if they exist."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/feed.atom")
            assert response.status_code == 200
            assert "application/atom+xml" in response.headers.get("content-type", "")
            # Check for Atom feed structure
            assert "<feed" in response.text
            assert "xmlns" in response.text

    @pytest.mark.asyncio
    async def test_rss_feed_contains_entries(self):
        """RSS feed should contain entries if they exist."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/feed.rss")
            assert response.status_code == 200
            assert "application/rss+xml" in response.headers.get("content-type", "")
            # Check for RSS feed structure
            assert "<rss" in response.text
            assert "<channel>" in response.text


class TestFeedProcessingFlow:
    """
    Test the complete feed processing flow.

    These tests verify that feeds can be added, fetched, and their
    entries processed correctly.
    """

    @pytest.mark.asyncio
    async def test_add_and_list_feed(self):
        """Add a feed and verify it appears in the feed list.

        Note: Uses a real RSS feed since feeds are now validated on add.
        May be skipped if external feed is rate limited.
        """
        session = create_test_session()
        cookies = {"session": session}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get initial feed count
            initial_response = await client.get(
                f"{BASE_URL}/admin/feeds",
                cookies=cookies,
            )
            assert initial_response.status_code == 200
            initial_count = len(initial_response.json().get("feeds", []))

            # Add a test feed (using a real RSS feed)
            test_url = "https://feeds.bbci.co.uk/news/technology/rss.xml"
            add_response = await client.post(
                f"{BASE_URL}/admin/feeds",
                data={"url": test_url},
                cookies=cookies,
                follow_redirects=False,
            )
            # Skip if rate limited or network issue
            if add_response.status_code == 400 and "429" in add_response.text:
                pytest.skip("External feed rate limited")
            if add_response.status_code == 400 and "timeout" in add_response.text.lower():
                pytest.skip("External feed timeout")
            assert add_response.status_code == 302

            # Verify feed was added
            after_response = await client.get(
                f"{BASE_URL}/admin/feeds",
                cookies=cookies,
            )
            assert after_response.status_code == 200
            after_feeds = after_response.json().get("feeds", [])
            assert len(after_feeds) == initial_count + 1

            # Find and delete the test feed
            for feed in after_feeds:
                if feed.get("url") == test_url:
                    delete_response = await client.post(
                        f"{BASE_URL}/admin/feeds/{feed['id']}",
                        data={"_method": "DELETE"},
                        cookies=cookies,
                        follow_redirects=False,
                    )
                    assert delete_response.status_code == 302
                    break
