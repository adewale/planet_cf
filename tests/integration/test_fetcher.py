# tests/integration/test_fetcher.py
"""Integration tests for the feed fetcher (queue consumer) functionality."""

import httpx
import pytest
import respx
from httpx import Response


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
    import httpx

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

    # Should raise HTTPStatusError
    with pytest.raises(httpx.HTTPStatusError):
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
