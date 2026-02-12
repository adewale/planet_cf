# tests/unit/test_no_full_content_fetch.py
"""Verify that full-content fetching has been removed.

Planet CF should use whatever content the feed provides — it should NOT
fetch the original article URL to scrape full-page content. These tests
ensure the feature was cleanly removed and _upsert_entry processes
feed content directly without any outbound HTTP requests.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.main import Default


def _make_mock_env():
    """Create a mock env with DB for _upsert_entry."""
    env = MagicMock()
    stmt = MagicMock()
    stmt.bind.return_value = stmt
    stmt.run = AsyncMock(return_value=MagicMock(results=[]))
    stmt.first = AsyncMock(return_value=None)
    env.DB.prepare.return_value = stmt
    env.SEARCH_INDEX = None
    env.AI = None
    return env


# =============================================================================
# Removal verification: the feature is gone
# =============================================================================


class TestFullContentFetchRemoved:
    """Verify that _fetch_full_content and its config are fully removed."""

    def test_no_fetch_full_content_method(self):
        """Default class should not have _fetch_full_content method."""
        assert not hasattr(Default, "_fetch_full_content")

    def test_no_fetch_full_content_in_upsert_entry(self):
        """_upsert_entry should not reference _fetch_full_content."""
        source = inspect.getsource(Default._upsert_entry)
        assert "_fetch_full_content" not in source

    def test_no_full_content_config_in_upsert_entry(self):
        """_upsert_entry should not reference fetch_full_content config."""
        source = inspect.getsource(Default._upsert_entry)
        assert "fetch_full_content" not in source.lower()

    def test_no_fetch_full_content_config_getter(self):
        """config module should not have get_fetch_full_content_enabled."""
        import src.config as config_module

        assert not hasattr(config_module, "get_fetch_full_content_enabled")

    def test_no_fetch_full_content_config_constant(self):
        """config module should not have DEFAULT_FETCH_FULL_CONTENT_ENABLED."""
        import src.config as config_module

        assert not hasattr(config_module, "DEFAULT_FETCH_FULL_CONTENT_ENABLED")


# =============================================================================
# _upsert_entry still works: content flows straight through to sanitization
# =============================================================================


class TestUpsertEntryWithoutFullContentFetch:
    """Verify _upsert_entry processes content directly without fetching."""

    @pytest.mark.asyncio
    async def test_short_content_not_replaced(self):
        """Short content (< 500 chars) is kept as-is, not replaced by a fetch."""
        worker = Default()
        worker.env = _make_mock_env()

        entry = {
            "id": "https://example.com/post",
            "link": "https://example.com/post",
            "title": "Short Post",
            "summary": "A brief summary.",
            "content": [{"value": "<p>Short content under 500 chars.</p>"}],
        }

        with unittest.mock.patch.object(
            worker, "_sanitize_html", side_effect=lambda x: x
        ) as mock_sanitize:
            await worker._upsert_entry(feed_id=1, entry=entry)

        # Sanitizer receives the original short content directly
        call_arg = mock_sanitize.call_args[0][0]
        assert "Short content under 500 chars" in call_arg

    @pytest.mark.asyncio
    async def test_long_content_passed_through(self):
        """Long content is also passed through directly."""
        worker = Default()
        worker.env = _make_mock_env()

        long_text = "x" * 1000
        entry = {
            "id": "https://example.com/long",
            "link": "https://example.com/long",
            "title": "Long Post",
            "summary": "Summary.",
            "content": [{"value": f"<p>{long_text}</p>"}],
        }

        with unittest.mock.patch.object(
            worker, "_sanitize_html", side_effect=lambda x: x
        ) as mock_sanitize:
            await worker._upsert_entry(feed_id=1, entry=entry)

        call_arg = mock_sanitize.call_args[0][0]
        assert long_text in call_arg

    @pytest.mark.asyncio
    async def test_no_outbound_http_during_upsert(self):
        """_upsert_entry should make zero outbound HTTP calls."""
        worker = Default()
        worker.env = _make_mock_env()

        entry = {
            "id": "https://example.com/post",
            "link": "https://example.com/post",
            "title": "Test Post",
            "content": [{"value": "<p>Brief.</p>"}],
        }

        with unittest.mock.patch("src.main.safe_http_fetch") as mock_fetch:
            await worker._upsert_entry(feed_id=1, entry=entry)

        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_content_still_sanitized(self):
        """Content from feed is still passed through _sanitize_html."""
        worker = Default()
        worker.env = _make_mock_env()

        entry = {
            "id": "https://example.com/xss",
            "link": "https://example.com/xss",
            "title": "XSS Test",
            "content": [{"value": '<p>Safe</p><script>alert("xss")</script>'}],
        }

        with unittest.mock.patch.object(worker, "_sanitize_html", wraps=worker._sanitize_html):
            await worker._upsert_entry(feed_id=1, entry=entry)

    @pytest.mark.asyncio
    async def test_entry_with_no_link_still_works(self):
        """Entries without a link field are processed normally."""
        worker = Default()
        worker.env = _make_mock_env()

        entry = {
            "id": "urn:uuid:some-guid",
            "title": "No Link Post",
            "content": [{"value": "<p>Content without a link.</p>"}],
        }

        # Should not raise
        await worker._upsert_entry(feed_id=1, entry=entry)

    @pytest.mark.asyncio
    async def test_summary_only_entry_uses_summary(self):
        """Entry with only summary (no content) uses summary as content."""
        worker = Default()
        worker.env = _make_mock_env()

        entry = {
            "id": "https://example.com/summary-only",
            "link": "https://example.com/summary-only",
            "title": "Summary Only",
            "summary": "This feed only provides a summary, no full content.",
        }

        with unittest.mock.patch.object(
            worker, "_sanitize_html", side_effect=lambda x: x
        ) as mock_sanitize:
            await worker._upsert_entry(feed_id=1, entry=entry)

        call_arg = mock_sanitize.call_args[0][0]
        assert "only provides a summary" in call_arg


# Need the import for patch.object
import unittest.mock
