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
# Tests for description fallback (fixes for jilles.me and boristane.com feeds)
# =============================================================================


class MockD1WithCapture:
    """Mock D1 that captures INSERT statements for verification."""

    def __init__(self):
        self.inserts: list[dict] = []
        self._data = {"feeds": [], "entries": [], "admins": []}
        self._next_id = 1

    def prepare(self, sql: str):
        return MockD1StatementWithCapture(sql, self)


class MockD1StatementWithCapture:
    """Mock D1 statement that captures bound parameters."""

    def __init__(self, sql: str, db: MockD1WithCapture):
        self._sql = sql
        self._db = db
        self._bound_args: list = []

    def bind(self, *args):
        self._bound_args = list(args)
        return self

    async def all(self):
        from tests.conftest import MockD1Result

        return MockD1Result(results=[])

    async def first(self):
        # For INSERT ... RETURNING id, return a fake id
        if "INSERT INTO entries" in self._sql and "RETURNING" in self._sql:
            # Capture the insert
            entry_id = self._db._next_id
            self._db._next_id += 1
            self._db.inserts.append(
                {
                    "sql": self._sql,
                    "args": self._bound_args,
                    # Map positional args to entry fields based on SQL column order
                    # INSERT INTO entries (feed_id, guid, url, title, author, content, summary, ...)
                    "id": entry_id,
                    "feed_id": self._bound_args[0] if len(self._bound_args) > 0 else None,
                    "guid": self._bound_args[1] if len(self._bound_args) > 1 else None,
                    "url": self._bound_args[2] if len(self._bound_args) > 2 else None,
                    "title": self._bound_args[3] if len(self._bound_args) > 3 else None,
                    "author": self._bound_args[4] if len(self._bound_args) > 4 else None,
                    "content": self._bound_args[5] if len(self._bound_args) > 5 else None,
                    "summary": self._bound_args[6] if len(self._bound_args) > 6 else None,
                    "published_at": self._bound_args[7] if len(self._bound_args) > 7 else None,
                }
            )
            return {"id": entry_id}
        return None

    async def run(self):
        from tests.conftest import MockD1Result

        return MockD1Result(results=[])


@pytest.fixture
def mock_env_with_capture():
    """Create a mock environment that captures DB inserts."""
    from tests.conftest import MockAI, MockEnv, MockQueue, MockVectorize

    db = MockD1WithCapture()
    return MockEnv(
        DB=db,
        FEED_QUEUE=MockQueue(),
        DEAD_LETTER_QUEUE=MockQueue(),
        SEARCH_INDEX=MockVectorize(),
        AI=MockAI(),
    ), db


@pytest.mark.asyncio
@respx.mock
async def test_rss_description_only_extracts_content(mock_env_with_capture):
    """RSS feed with only <description> (no <content:encoded>) should extract content.

    This tests the fix for feeds like jilles.me that may only have description.
    """
    mock_env, db = mock_env_with_capture

    # Content needs to be > 500 chars to avoid triggering full content fetch
    long_content = "This is the full post content from description tag. " * 15  # ~780 chars

    # RSS feed with ONLY <description>, no <content:encoded> or <summary>
    feed_xml = f"""<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <link>https://example.com</link>
            <item>
                <title>Test Post</title>
                <link>https://example.com/post/1</link>
                <description>{long_content}</description>
                <guid>post-1</guid>
                <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>"""

    respx.get("https://example.com/feed.xml").mock(return_value=Response(200, content=feed_xml))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {"feed_id": 1, "url": "https://example.com/feed.xml"}
    result = await worker._process_single_feed(job)

    assert result["status"] == "ok"
    assert len(db.inserts) == 1

    entry = db.inserts[0]
    # Content should be extracted from <description>
    assert "This is the full post content from description tag" in entry["content"]
    assert len(entry["content"]) > 500  # Should have the full long content
    # Summary should be truncated to 500 chars with "..."
    assert len(entry["summary"]) <= 500
    assert entry["summary"].endswith("...")


@pytest.mark.asyncio
@respx.mock
async def test_rss_prefers_summary_over_description(mock_env_with_capture):
    """RSS feed with both <summary> and <description> should prefer summary.

    feedparser typically maps RSS <description> to both summary and description,
    so this tests the priority order.
    """
    mock_env, db = mock_env_with_capture

    # Content needs to be > 500 chars to avoid triggering full content fetch
    long_content = "Content from description field in RSS feed. " * 15  # ~675 chars

    # Note: feedparser maps RSS <description> to entry.summary, so in practice
    # both will be populated. This test verifies the fallback order.
    feed_xml = f"""<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <title>Test Feed</title>
            <link>https://example.com</link>
            <item>
                <title>Test Post</title>
                <link>https://example.com/post/1</link>
                <description>{long_content}</description>
                <guid>post-1</guid>
            </item>
        </channel>
    </rss>"""

    respx.get("https://example.com/feed.xml").mock(return_value=Response(200, content=feed_xml))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {"feed_id": 1, "url": "https://example.com/feed.xml"}
    result = await worker._process_single_feed(job)

    assert result["status"] == "ok"
    assert len(db.inserts) == 1

    entry = db.inserts[0]
    # Content should be populated (feedparser maps description to summary)
    assert entry["content"] is not None
    assert "Content from description field in RSS feed" in entry["content"]
    assert len(entry["content"]) > 500


@pytest.mark.asyncio
@respx.mock
async def test_atom_summary_only_extracts_content(mock_env_with_capture):
    """Atom feed with only <summary> (no <content>) should extract content.

    This tests feeds that only provide summary, not full content.
    """
    mock_env, db = mock_env_with_capture

    # Content needs to be > 500 chars to avoid triggering full content fetch
    long_summary = "This is a summary without full content element. " * 15  # ~720 chars

    atom_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
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
            <summary>{long_summary}</summary>
        </entry>
    </feed>"""

    respx.get("https://example.com/feed.atom").mock(return_value=Response(200, content=atom_xml))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {"feed_id": 1, "url": "https://example.com/feed.atom"}
    result = await worker._process_single_feed(job)

    assert result["status"] == "ok"
    assert len(db.inserts) == 1

    entry = db.inserts[0]
    # Content should be extracted from <summary>
    assert "This is a summary without full content element" in entry["content"]
    assert len(entry["content"]) > 500
    # Summary should be truncated
    assert len(entry["summary"]) <= 500


@pytest.mark.asyncio
@respx.mock
async def test_atom_content_preferred_over_summary(mock_env_with_capture):
    """Atom feed with both <content> and <summary> should prefer content."""
    mock_env, db = mock_env_with_capture

    # Content needs to be > 500 chars to avoid triggering full content fetch
    long_content = "Full content is much longer and more detailed than summary. " * 12  # ~720 chars

    atom_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
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
            <summary>Short summary text for preview</summary>
            <content type="html">&lt;p&gt;{long_content}&lt;/p&gt;</content>
        </entry>
    </feed>"""

    respx.get("https://example.com/feed.atom").mock(return_value=Response(200, content=atom_xml))

    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    job = {"feed_id": 1, "url": "https://example.com/feed.atom"}
    result = await worker._process_single_feed(job)

    assert result["status"] == "ok"
    assert len(db.inserts) == 1

    entry = db.inserts[0]
    # Content should be from <content>, not <summary>
    assert "Full content is much longer" in entry["content"]
    # Summary should be from <summary>
    assert entry["summary"] == "Short summary text for preview"
