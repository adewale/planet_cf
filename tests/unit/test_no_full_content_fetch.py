# tests/unit/test_no_full_content_fetch.py
"""Verify that full-content fetching has been removed.

Planet CF should use whatever content the feed provides — it should NOT
fetch the original article URL to scrape full-page content. These tests
ensure the feature was cleanly removed and _upsert_entry processes
feed content directly without any outbound HTTP requests.
"""

import unittest.mock
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.main import Default
from tests.conftest import TrackingD1


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
        # Also verify no variant naming like fetch_content or _get_full_content
        assert not hasattr(Default, "fetch_content")
        assert not hasattr(Default, "_get_full_content")

    @pytest.mark.asyncio
    async def test_upsert_entry_does_not_call_fetch_full_content(self):
        """_upsert_entry should not call any _fetch_full_content method."""
        worker = Default()
        worker.env = _make_mock_env()

        entry = {
            "id": "https://example.com/post",
            "link": "https://example.com/post",
            "title": "Test Post",
            "content": [{"value": "<p>Short.</p>"}],
        }

        # If _fetch_full_content existed and were called, this would fail
        with unittest.mock.patch.object(worker, "_sanitize_html", side_effect=lambda x: x):
            await worker._upsert_entry(feed_id=1, entry=entry)

        # Verify there is no _fetch_full_content method at all
        assert not hasattr(worker, "_fetch_full_content")
        # The worker should still have _sanitize_html (content processing without fetching)
        assert hasattr(worker, "_sanitize_html")
        # And _upsert_entry itself should exist
        assert hasattr(worker, "_upsert_entry")

    def test_no_fetch_full_content_config_getter(self):
        """config module should not have get_fetch_full_content_enabled."""
        import src.config as config_module

        assert not hasattr(config_module, "get_fetch_full_content_enabled")
        # The config module should still have legitimate config getters
        assert hasattr(config_module, "get_config_value")
        assert hasattr(config_module, "get_planet_config")

    def test_no_fetch_full_content_config_constant(self):
        """config module should not have DEFAULT_FETCH_FULL_CONTENT_ENABLED."""
        import src.config as config_module

        assert not hasattr(config_module, "DEFAULT_FETCH_FULL_CONTENT_ENABLED")
        # No FETCH_FULL_CONTENT anywhere in the module's public names
        public_names = [n for n in dir(config_module) if not n.startswith("_")]
        assert not any("FETCH_FULL_CONTENT" in name for name in public_names)


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
        mock_sanitize.assert_called_once()
        call_arg = mock_sanitize.call_args[0][0]
        assert "Short content under 500 chars" in call_arg
        # The content came from the entry's content field, not from a fetch
        assert "<p>" in call_arg

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

        mock_sanitize.assert_called_once()
        call_arg = mock_sanitize.call_args[0][0]
        assert long_text in call_arg
        # Content was passed through in full, not truncated by a fetch replacement
        assert len(call_arg) >= 1000

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
        # The entry was processed (no exception raised), confirming no fetch needed
        assert not hasattr(worker, "_fetch_full_content")
        # safe_http_fetch was available but never invoked
        assert mock_fetch.call_count == 0

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

        with unittest.mock.patch.object(
            worker, "_sanitize_html", wraps=worker._sanitize_html
        ) as mock_sanitize:
            await worker._upsert_entry(feed_id=1, entry=entry)

        # Sanitizer was called with the XSS content
        mock_sanitize.assert_called_once()
        call_arg = mock_sanitize.call_args[0][0]
        assert "alert" in call_arg or "Safe" in call_arg

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
        # The entry was processed without needing a link for fetching
        assert "link" not in entry
        # No fetch method exists to try to fetch the missing link
        assert not hasattr(worker, "_fetch_full_content")

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

        mock_sanitize.assert_called_once()
        call_arg = mock_sanitize.call_args[0][0]
        assert "only provides a summary" in call_arg
        # The summary text was used directly, not fetched from the link
        assert "content" not in entry  # entry had no content field


# =============================================================================
# Upsert refreshes url and summary on conflict
# =============================================================================


class TestUpsertRefreshesPermalink:
    """Verify _upsert_entry updates url and summary when GUID matches.

    Per RFC 4287 / RSS 2.0 the GUID is the canonical stable identifier.
    When the same GUID reappears with a different link (e.g. the site
    changed its URL structure), the aggregator should update the stored
    permalink rather than leaving a stale one.
    """

    @pytest.mark.asyncio
    async def test_upsert_updates_url_on_conflict(self):
        """On a GUID conflict the separate UPDATE refreshes url/title (H1).

        H1 changed the INSERT to ON CONFLICT DO NOTHING; the existing-row refresh
        now happens in a separate UPDATE that fires when the INSERT inserts no
        row. Simulate that: the INSERT returns no id (conflict), the UPDATE
        returns a row (content changed).
        """
        worker = Default()
        db = TrackingD1(
            results_by_sql=[
                ("INSERT INTO entries", []),  # conflict → DO NOTHING, no row
                ("UPDATE entries", [{"id": 1, "published_at": "2026-01-01T00:00:00Z"}]),
            ]
        )
        worker.env = MagicMock()
        worker.env.DB = db
        worker.env.SEARCH_INDEX = None
        worker.env.AI = None

        entry = {
            "id": "urn:uuid:stable-guid-123",
            "link": "https://example.com/new-permalink/post",
            "title": "My Post",
            "content": [{"value": "<p>Content</p>"}],
            "summary": "Updated summary",
        }

        with unittest.mock.patch.object(worker, "_sanitize_html", side_effect=lambda x: x):
            result = await worker._upsert_entry(feed_id=1, entry=entry)

        # The INSERT is DO NOTHING (no excluded.* refresh); the UPDATE does the refresh.
        insert_stmt = next(s for s in db.statements if "INSERT INTO entries" in s.sql)
        assert "ON CONFLICT(feed_id, guid) DO NOTHING" in insert_stmt.sql

        update_stmt = next(s for s in db.statements if "UPDATE entries" in s.sql)
        assert "url = ?" in update_stmt.sql
        assert "title = ?" in update_stmt.sql
        # The new URL and title must be bound to the UPDATE.
        assert "https://example.com/new-permalink/post" in update_stmt.bound_args
        assert "My Post" in update_stmt.bound_args
        # A content change is reported, not a brand-new entry.
        assert result["is_new"] is False
        assert result["content_changed"] is True

    @pytest.mark.asyncio
    async def test_upsert_updates_summary_on_conflict(self):
        """On a GUID conflict the separate UPDATE refreshes summary/content (H1)."""
        worker = Default()
        db = TrackingD1(
            results_by_sql=[
                ("INSERT INTO entries", []),  # conflict
                ("UPDATE entries", [{"id": 1, "published_at": "2026-01-01T00:00:00Z"}]),
            ]
        )
        worker.env = MagicMock()
        worker.env.DB = db
        worker.env.SEARCH_INDEX = None
        worker.env.AI = None

        entry = {
            "id": "urn:uuid:stable-guid-456",
            "link": "https://example.com/post",
            "title": "My Post",
            "summary": "A new summary after the author revised it",
            "content": [{"value": "<p>Content</p>"}],
        }

        with unittest.mock.patch.object(worker, "_sanitize_html", side_effect=lambda x: x):
            await worker._upsert_entry(feed_id=1, entry=entry)

        update_stmt = next(s for s in db.statements if "UPDATE entries" in s.sql)
        assert "summary = ?" in update_stmt.sql
        assert "A new summary after the author revised it" in update_stmt.bound_args
        # The UPDATE also refreshes title and content.
        assert "title = ?" in update_stmt.sql
        assert "content = ?" in update_stmt.sql


class TestUpsertInsertVsUpdateSemantics:
    """H1: distinguish genuine INSERTs from UPDATEs and from unchanged re-sees."""

    @pytest.mark.asyncio
    async def test_genuine_insert_is_new(self):
        """A real INSERT (RETURNING id from DO NOTHING) reports is_new and its date."""
        worker = Default()
        db = TrackingD1(
            results_by_sql=[("INSERT INTO entries", [{"id": 7}])],
        )
        worker.env = MagicMock()
        worker.env.DB = db
        worker.env.SEARCH_INDEX = None
        worker.env.AI = None

        entry = {
            "id": "guid-new",
            "link": "https://example.com/p",
            "title": "Fresh",
            "content": [{"value": "<p>x</p>"}],
            "published_parsed": (2026, 6, 1, 0, 0, 0),
        }
        with unittest.mock.patch.object(worker, "_sanitize_html", side_effect=lambda x: x):
            result = await worker._upsert_entry(feed_id=1, entry=entry)

        assert result["is_new"] is True
        assert result["entry_id"] == 7
        # published_at is canonicalized and surfaced for last_entry_at aggregation.
        assert result["published_at"] == "2026-06-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_unchanged_reseen_entry_is_not_new_and_not_indexed(self):
        """H1: re-seeing an unchanged entry yields no insert, no change, no entry_id.

        Both the INSERT (conflict → no row) and the change-guarded UPDATE (no row)
        return nothing, so the entry is neither counted nor re-embedded.
        """
        worker = Default()
        db = TrackingD1(
            results_by_sql=[
                ("INSERT INTO entries", []),  # conflict
                ("UPDATE entries", []),  # content unchanged → WHERE guard yields no row
            ],
        )
        worker.env = MagicMock()
        worker.env.DB = db
        # Search bindings present so we can prove indexing is skipped on no change.
        worker.env.SEARCH_INDEX = MagicMock()
        worker.env.AI = MagicMock()
        index_mock = AsyncMock()

        entry = {
            "id": "guid-existing",
            "link": "https://example.com/p",
            "title": "Same",
            "content": [{"value": "<p>same</p>"}],
        }
        with (
            unittest.mock.patch.object(worker, "_sanitize_html", side_effect=lambda x: x),
            unittest.mock.patch.object(worker, "_index_entry_for_search", index_mock),
        ):
            result = await worker._upsert_entry(feed_id=1, entry=entry)

        assert result["is_new"] is False
        assert result["content_changed"] is False
        assert result["entry_id"] is None
        assert result["published_at"] is None
        # No re-embedding for an unchanged entry (the hourly-cost bug).
        index_mock.assert_not_called()
