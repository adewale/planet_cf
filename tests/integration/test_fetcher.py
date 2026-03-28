# tests/integration/test_fetcher.py
"""Integration tests for the feed fetcher (queue consumer) functionality."""

import logging

import httpx
import pytest
import respx
from httpx import Response

from tests.conftest import MockD1, MockEnv, MockQueue


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_processes_valid_feed(mock_env):
    """Fetcher should parse feed and store entries."""
    # Mock the feed response
    feed_xml = """<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <link>https://example.com</link>
            <item>
                <title>Test Post</title>
                <link>https://example.com/post/1</link>
                <description>Test content</description>
                <guid>post-1</guid>
            </item>
        </channel>
    </rss>"""

    respx.get("https://example.com/feed.xml").mock(return_value=Response(200, content=feed_xml))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {
        "feed_id": 1,
        "url": "https://example.com/feed.xml",
    }

    # Process the feed
    result = await worker._process_single_feed(job)

    assert result["status"] == "ok"


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_respects_304_not_modified(mock_env):
    """Fetcher should skip processing when feed returns 304."""
    respx.get("https://example.com/feed.xml").mock(return_value=Response(304))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {
        "feed_id": 1,
        "url": "https://example.com/feed.xml",
        "etag": '"abc123"',
    }

    result = await worker._process_single_feed(job)

    assert result["status"] == "not_modified"


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_handles_timeout(mock_env):
    """Fetcher should handle timeout gracefully."""

    respx.get("https://slow.example.com/feed.xml").mock(
        side_effect=httpx.TimeoutException("Connection timed out")
    )

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {
        "feed_id": 1,
        "url": "https://slow.example.com/feed.xml",
    }

    # Should raise timeout exception
    with pytest.raises(httpx.TimeoutException):
        await worker._process_single_feed(job)


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_handles_404(mock_env):
    """Fetcher should handle 404 responses."""
    respx.get("https://example.com/missing.xml").mock(
        return_value=Response(404, content="Not Found")
    )

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {
        "feed_id": 1,
        "url": "https://example.com/missing.xml",
    }

    # Should raise ValueError with HTTP error message (after safe_http_fetch change)
    with pytest.raises(ValueError, match="HTTP error 404"):
        await worker._process_single_feed(job)


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_sends_conditional_headers(mock_env):
    """Fetcher should send If-None-Match and If-Modified-Since headers."""
    respx.get("https://example.com/feed.xml").mock(return_value=Response(304))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {
        "feed_id": 1,
        "url": "https://example.com/feed.xml",
        "etag": '"abc123"',
        "last_modified": "Sat, 01 Jan 2026 00:00:00 GMT",
    }

    await worker._process_single_feed(job)

    # Check that conditional headers were sent
    request = respx.calls[0].request
    assert request.headers.get("if-none-match") == '"abc123"'
    assert request.headers.get("if-modified-since") == "Sat, 01 Jan 2026 00:00:00 GMT"


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_sends_user_agent(mock_env):
    """Fetcher should send proper User-Agent header."""
    respx.get("https://example.com/feed.xml").mock(return_value=Response(304))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {
        "feed_id": 1,
        "url": "https://example.com/feed.xml",
    }

    await worker._process_single_feed(job)

    request = respx.calls[0].request
    assert "PlanetCF" in request.headers.get("user-agent", "")


@pytest.mark.asyncio
async def test_fetcher_rejects_unsafe_urls(mock_env):
    """Fetcher should reject URLs that fail SSRF validation."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    # Test various unsafe URLs
    unsafe_jobs = [
        {"feed_id": 1, "url": "http://localhost/feed"},
        {"feed_id": 1, "url": "http://127.0.0.1/feed"},
        {"feed_id": 1, "url": "http://169.254.169.254/latest/meta-data/"},
        {"feed_id": 1, "url": "http://10.0.0.1/feed"},
        {"feed_id": 1, "url": "file:///etc/passwd"},
    ]

    for job in unsafe_jobs:
        with pytest.raises(ValueError, match="SSRF"):
            await worker._process_single_feed(job)


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_parses_atom_feed(mock_env):
    """Fetcher should parse Atom feeds correctly."""
    atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Test Blog</title>
        <link href="https://example.com"/>
        <id>https://example.com/</id>
        <updated>2026-01-01T12:00:00Z</updated>
        <entry>
            <title>Test Post</title>
            <link href="https://example.com/post/1"/>
            <id>https://example.com/post/1</id>
            <updated>2026-01-01T12:00:00Z</updated>
            <content type="html">&lt;p&gt;Content&lt;/p&gt;</content>
        </entry>
    </feed>"""

    respx.get("https://example.com/feed.atom").mock(return_value=Response(200, content=atom_xml))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {
        "feed_id": 1,
        "url": "https://example.com/feed.atom",
    }

    result = await worker._process_single_feed(job)
    assert result["status"] == "ok"


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_handles_malformed_feed(mock_env):
    """Fetcher should handle malformed feed gracefully."""
    respx.get("https://example.com/bad.xml").mock(
        return_value=Response(200, content="<not valid xml")
    )

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {
        "feed_id": 1,
        "url": "https://example.com/bad.xml",
    }

    # Should raise ValueError for parse error
    with pytest.raises(ValueError, match="parse error"):
        await worker._process_single_feed(job)


# =============================================================================
# Lite mode / missing bindings tests
# =============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_no_ai_binding_inserts_entry_without_error():
    """Feed processing with AI=None should insert entries and not log errors.

    This is the exact path that caused the planet-python AttributeError:
    queue processes a feed, inserts an entry, tries to index it for search,
    and AI is None. The fix should skip indexing silently.
    """
    feed_xml = """<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <link>https://example.com</link>
            <item>
                <title>Test Post</title>
                <link>https://example.com/post/1</link>
                <description>Test content</description>
                <guid>post-1</guid>
            </item>
        </channel>
    </rss>"""

    respx.get("https://example.com/feed.xml").mock(return_value=Response(200, content=feed_xml))

    from src.main import PlanetCF

    # Lite mode env: no AI, no SEARCH_INDEX
    env = MockEnv(
        DB=MockD1(
            {
                "feeds": [
                    {
                        "id": 1,
                        "url": "https://example.com/feed.xml",
                        "title": "Test Feed",
                        "is_active": 1,
                        "site_url": "https://example.com",
                        "consecutive_failures": 0,
                        "last_success_at": "2026-01-01T00:00:00Z",
                    }
                ]
            }
        ),
        FEED_QUEUE=MockQueue(),
        DEAD_LETTER_QUEUE=MockQueue(),
        SEARCH_INDEX=None,
        AI=None,
    )
    env.INSTANCE_MODE = "lite"

    worker = PlanetCF()
    worker.env = env

    job = {"feed_id": 1, "url": "https://example.com/feed.xml"}

    # Capture log output to verify no error-level logs
    logger = logging.getLogger("src.main")
    with pytest.raises(Exception) if False else _no_error_logs(logger):
        result = await worker._process_single_feed(job)

    assert result["status"] == "ok"


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_caps_entries_to_retention_limit(mock_env):
    """Feeds with more entries than RETENTION_MAX_ENTRIES_PER_FEED should be capped.

    This prevents CPU exhaustion from feeds like pythonbytes.fm (474 entries).
    The retention limit is the max we'll keep, so processing more is wasteful.
    """
    # Build a feed with 200 entries
    items = "\n".join(
        f"""<item>
            <title>Post {i}</title>
            <link>https://example.com/post/{i}</link>
            <guid>post-{i}</guid>
        </item>"""
        for i in range(200)
    )
    feed_xml = f"""<?xml version="1.0"?>
    <rss version="2.0">
        <channel><title>Big Feed</title><link>https://example.com</link>
        {items}
        </channel>
    </rss>"""

    respx.get("https://example.com/big-feed.xml").mock(return_value=Response(200, content=feed_xml))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env
    # Set retention limit to 50 entries
    mock_env.RETENTION_MAX_ENTRIES_PER_FEED = "50"

    job = {"feed_id": 1, "url": "https://example.com/big-feed.xml"}
    result = await worker._process_single_feed(job)

    assert result["status"] == "ok"
    # entries_found should reflect the full feed
    assert result["entries_found"] == 200
    # entries_added should be at most the retention limit (50), not all 200
    assert result["entries_added"] <= 50


@pytest.mark.asyncio
@respx.mock
async def test_fetcher_no_bindings_skips_indexing_entirely():
    """When AI/SEARCH_INDEX are None, indexing should not be attempted at all.

    Previous behavior: called _index_entry_for_search per entry, which returned
    NotConfigured immediately but still incurred function call overhead for
    hundreds of entries. Now the check happens once at the loop level.
    """
    feed_xml = """<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <link>https://example.com</link>
            <item>
                <title>Post 1</title>
                <link>https://example.com/1</link>
                <guid>p1</guid>
            </item>
            <item>
                <title>Post 2</title>
                <link>https://example.com/2</link>
                <guid>p2</guid>
            </item>
        </channel>
    </rss>"""

    respx.get("https://example.com/feed.xml").mock(return_value=Response(200, content=feed_xml))

    from unittest.mock import AsyncMock
    from unittest.mock import patch as mock_patch

    from src.main import PlanetCF

    env = MockEnv(
        DB=MockD1(
            {
                "feeds": [
                    {
                        "id": 1,
                        "url": "https://example.com/feed.xml",
                        "title": "Test",
                        "is_active": 1,
                        "site_url": "https://example.com",
                        "consecutive_failures": 0,
                        "last_success_at": "2026-01-01T00:00:00Z",
                    }
                ]
            }
        ),
        FEED_QUEUE=MockQueue(),
        DEAD_LETTER_QUEUE=MockQueue(),
        SEARCH_INDEX=None,
        AI=None,
    )

    worker = PlanetCF()
    worker.env = env

    # Spy on _index_entry_for_search to verify it's never called
    with mock_patch.object(worker, "_index_entry_for_search", new_callable=AsyncMock) as mock_index:
        result = await worker._process_single_feed(
            {"feed_id": 1, "url": "https://example.com/feed.xml"}
        )

    assert result["status"] == "ok"
    # _index_entry_for_search should NOT have been called at all
    mock_index.assert_not_called()


class _no_error_logs:
    """Context manager that fails if any ERROR-level log is emitted."""

    def __init__(self, logger):
        self.logger = logger
        self.errors = []

    def __enter__(self):
        self._handler = _ErrorCapture(self.errors)
        self.logger.addHandler(self._handler)
        return self

    def __exit__(self, *exc_info):
        self.logger.removeHandler(self._handler)
        if self.errors:
            raise AssertionError(f"Unexpected error log(s): {self.errors}")


class _ErrorCapture(logging.Handler):
    """Logging handler that captures ERROR+ records."""

    def __init__(self, errors):
        super().__init__(level=logging.ERROR)
        self.errors = errors

    def emit(self, record):
        self.errors.append(record.getMessage())
