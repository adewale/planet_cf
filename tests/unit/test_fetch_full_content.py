# tests/unit/test_fetch_full_content.py
"""Unit tests for Default._fetch_full_content in src/main.py."""

from unittest.mock import AsyncMock, patch

import pytest

from src.main import Default
from src.wrappers import HttpResponse

# =============================================================================
# Mock Infrastructure
# =============================================================================


class MockEnv:
    """Mock Cloudflare Workers environment for content fetching tests."""

    def __init__(self):
        self.DB = None
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = None
        self.DEAD_LETTER_QUEUE = None
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"


def _make_html_response(
    html: str,
    status_code: int = 200,
    url: str = "https://example.com/post",
) -> HttpResponse:
    """Create a mock HttpResponse with HTML content."""
    return HttpResponse(
        status_code=status_code,
        text=html,
        headers={"content-type": "text/html"},
        final_url=url,
    )


def _make_worker() -> Default:
    """Create a Default worker with minimal mock env."""
    worker = Default()
    worker.env = MockEnv()
    return worker


# Reusable padding text to ensure content exceeds 500 characters.
_PADDING = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, "
    "quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. "
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu "
    "fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident."
)


def _long_article_html(
    container: str = "article",
    content_marker: str = "main article content",
) -> str:
    """Build an HTML page with a long article body inside the specified container."""
    inner = f"<p>This is the {content_marker} that should be extracted from the page.</p>"
    inner += f"<p>{_PADDING}</p>" * 4  # well over 500 chars
    if container == "article":
        return (
            f"<html><body><nav>Navigation</nav>"
            f"<article>{inner}</article>"
            f"<footer>Footer</footer></body></html>"
        )
    if container == "main":
        return f"<html><body><header>Header</header><main>{inner}</main></body></html>"
    if container == "post-content":
        return (
            f'<html><body><div class="sidebar">Sidebar</div>'
            f'<div class="post-content">{inner}</div></body></html>'
        )
    return f"<html><body>{inner}</body></html>"


# =============================================================================
# Tests: _fetch_full_content
# =============================================================================


class TestFetchFullContent:
    """Tests for Default._fetch_full_content method."""

    @pytest.mark.asyncio
    async def test_extracts_article_tag_content(self):
        """Extracts content from <article> tag when present."""
        html = _long_article_html("article", "main article content")
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(html)
            result = await worker._fetch_full_content("https://example.com/post")

        assert result is not None
        assert "main article content" in result
        # nav/footer are stripped from HTML before extraction
        assert "Navigation" not in result
        assert "Footer" not in result

    @pytest.mark.asyncio
    async def test_falls_back_to_main_tag(self):
        """Falls back to <main> tag when no <article> tag exists."""
        html = _long_article_html("main", "Main content area")
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(html)
            result = await worker._fetch_full_content("https://example.com/post")

        assert result is not None
        assert "Main content area" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_post_content_div(self):
        """Falls back to <div class="post-content"> when no article/main tags."""
        html = _long_article_html("post-content", "Post content in a div")
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(html)
            result = await worker._fetch_full_content("https://example.com/post")

        assert result is not None
        assert "Post content in a div" in result

    @pytest.mark.asyncio
    async def test_returns_none_when_no_content_found(self):
        """Returns None when no recognizable content containers exist."""
        html = '<html><body><div class="random">Short text</div></body></html>'
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(html)
            result = await worker._fetch_full_content("https://example.com/post")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_non_200_response(self):
        """Returns None when HTTP response is not 200."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response("<html>Not Found</html>", status_code=404)
            result = await worker._fetch_full_content("https://example.com/missing")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_ssrf_blocked_url(self):
        """Returns None for URLs blocked by SSRF protection."""
        worker = _make_worker()

        unsafe_urls = [
            "http://localhost/article",
            "http://127.0.0.1/article",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/article",
            "file:///etc/passwd",
        ]

        for url in unsafe_urls:
            result = await worker._fetch_full_content(url)
            assert result is None, f"Expected None for SSRF-blocked URL: {url}"

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_url(self):
        """Returns None for empty or None URL."""
        worker = _make_worker()
        assert await worker._fetch_full_content("") is None
        assert await worker._fetch_full_content(None) is None

    @pytest.mark.asyncio
    async def test_normalizes_relative_urls_in_content(self):
        """Relative URLs in extracted content are converted to absolute URLs."""
        inner = (
            '<p>Article with image <img src="/images/photo.png"> and content.</p>'
            '<p>Link to <a href="/about">about page</a> within the article.</p>'
            f"<p>{_PADDING}</p>" * 3
        )
        html = f"<html><body><article>{inner}</article></body></html>"
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(
                html, url="https://blog.example.com/2026/post"
            )
            result = await worker._fetch_full_content("https://blog.example.com/2026/post")

        assert result is not None
        assert "https://blog.example.com/images/photo.png" in result
        assert "https://blog.example.com/about" in result

    @pytest.mark.asyncio
    async def test_handles_very_large_response(self):
        """Large responses are handled (content extracted from article tag)."""
        large_paragraphs = "".join(
            f"<p>Paragraph {i} with content for large response test.</p>" for i in range(200)
        )
        html = f"<html><body><article>{large_paragraphs}</article></body></html>"
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(html)
            result = await worker._fetch_full_content("https://example.com/long-post")

        assert result is not None
        assert "Paragraph 0" in result

    @pytest.mark.asyncio
    async def test_returns_none_when_content_too_short(self):
        """Returns None when extracted content is 500 characters or fewer."""
        html = "<html><body><article><p>Short.</p></article></body></html>"
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(html)
            result = await worker._fetch_full_content("https://example.com/short")

        assert result is None

    @pytest.mark.asyncio
    async def test_strips_script_and_style_tags(self):
        """Script and style tags are removed before extraction."""
        inner = (
            f"<p>Clean content that should be extracted without scripts.</p><p>{_PADDING}</p>" * 3
        )
        html = (
            "<html><body>"
            "<script>alert('xss')</script>"
            "<style>.hidden { display: none; }</style>"
            f"<article>{inner}</article>"
            "</body></html>"
        )
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(html)
            result = await worker._fetch_full_content("https://example.com/post")

        assert result is not None
        assert "alert" not in result
        assert "display: none" not in result
        assert "Clean content" in result

    @pytest.mark.asyncio
    async def test_returns_none_on_fetch_exception(self):
        """Returns None when safe_http_fetch raises an exception."""
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Connection refused")
            result = await worker._fetch_full_content("https://example.com/post")

        assert result is None

    @pytest.mark.asyncio
    async def test_paragraph_fallback_extracts_paragraphs(self):
        """When no container found, falls back to extracting paragraphs (>= 3)."""
        paragraphs = "".join(f"<p>Paragraph {i}: {_PADDING}</p>" for i in range(6))
        html = f"<html><body>{paragraphs}</body></html>"
        worker = _make_worker()

        with patch("src.main.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = _make_html_response(html)
            result = await worker._fetch_full_content("https://example.com/paragraphs")

        assert result is not None
        assert "Paragraph 0" in result
