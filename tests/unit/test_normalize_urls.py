# tests/unit/test_normalize_urls.py
"""Unit tests for Default._normalize_urls in src/main.py."""

from src.main import Default

# =============================================================================
# Mock Infrastructure
# =============================================================================


class MockEnv:
    """Minimal mock environment for _normalize_urls tests."""

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


def _make_worker() -> Default:
    """Create a Default worker with minimal mock env."""
    worker = Default()
    worker.env = MockEnv()
    return worker


# =============================================================================
# Tests: _normalize_urls
# =============================================================================


class TestNormalizeUrls:
    """Tests for Default._normalize_urls method."""

    def test_relative_href_made_absolute(self):
        """Relative href paths are converted to absolute URLs."""
        worker = _make_worker()

        content = '<a href="/about">About</a>'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'href="https://example.com/about"' in result

    def test_relative_src_made_absolute(self):
        """Relative src paths are converted to absolute URLs."""
        worker = _make_worker()

        content = '<img src="/images/photo.png">'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'src="https://example.com/images/photo.png"' in result

    def test_already_absolute_urls_unchanged(self):
        """Already-absolute URLs are left unchanged."""
        worker = _make_worker()

        content = '<a href="https://other.com/page">Link</a>'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'href="https://other.com/page"' in result

    def test_http_absolute_urls_unchanged(self):
        """HTTP absolute URLs are left unchanged."""
        worker = _make_worker()

        content = '<img src="http://cdn.example.com/image.jpg">'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'src="http://cdn.example.com/image.jpg"' in result

    def test_protocol_relative_urls_unchanged(self):
        """Protocol-relative URLs (//...) are left unchanged."""
        worker = _make_worker()

        content = '<script src="//cdn.example.com/script.js"></script>'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'src="//cdn.example.com/script.js"' in result

    def test_data_urls_unchanged(self):
        """Data URLs are left unchanged."""
        worker = _make_worker()

        content = '<img src="data:image/png;base64,abc123">'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'src="data:image/png;base64,abc123"' in result

    def test_mailto_urls_unchanged(self):
        """Mailto URLs are left unchanged."""
        worker = _make_worker()

        content = '<a href="mailto:user@example.com">Email</a>'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'href="mailto:user@example.com"' in result

    def test_fragment_urls_unchanged(self):
        """Fragment-only URLs (#...) are left unchanged."""
        worker = _make_worker()

        content = '<a href="#section">Jump</a>'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'href="#section"' in result

    def test_relative_path_resolved(self):
        """Relative paths (without leading /) are resolved against the base path."""
        worker = _make_worker()

        content = '<img src="image.jpg">'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'src="https://example.com/blog/image.jpg"' in result

    def test_multiple_attributes_normalized(self):
        """Multiple href and src attributes are all normalized."""
        worker = _make_worker()

        content = '<a href="/page1">Link 1</a> <img src="/img.png"> <a href="/page2">Link 2</a>'
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert 'href="https://example.com/page1"' in result
        assert 'src="https://example.com/img.png"' in result
        assert 'href="https://example.com/page2"' in result

    def test_single_quoted_attributes(self):
        """Single-quoted attributes are handled."""
        worker = _make_worker()

        content = "<a href='/about'>About</a>"
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert "href='https://example.com/about'" in result

    def test_no_attributes_unchanged(self):
        """Content without href/src attributes is unchanged."""
        worker = _make_worker()

        content = "<p>Just text content</p>"
        result = worker._normalize_urls(content, "https://example.com/blog/post")

        assert result == "<p>Just text content</p>"

    def test_empty_content_unchanged(self):
        """Empty content is returned unchanged."""
        worker = _make_worker()

        result = worker._normalize_urls("", "https://example.com/blog/post")

        assert result == ""

    def test_base_url_with_path(self):
        """Base URL path is used correctly for relative resolution."""
        worker = _make_worker()

        content = '<img src="photo.jpg">'
        result = worker._normalize_urls(content, "https://example.com/2026/01/article")

        assert 'src="https://example.com/2026/01/photo.jpg"' in result

    def test_absolute_path_ignores_base_path(self):
        """Absolute paths (/foo) use only the origin, not the base path."""
        worker = _make_worker()

        content = '<a href="/global-page">'
        result = worker._normalize_urls(content, "https://example.com/blog/deep/path/article")

        assert 'href="https://example.com/global-page"' in result
