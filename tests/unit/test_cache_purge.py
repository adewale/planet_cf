# tests/unit/test_cache_purge.py
"""Tests for selective edge cache purging after admin actions.

RED phase: These tests assert that content-modifying admin actions
trigger cache purging. They should fail until the purging logic is
implemented.
"""

from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.conftest import (
    MockRequest,
    admin_row,
    make_authenticated_worker,
)

# ============================================================================
# Constants — must match the production CACHEABLE_PATHS
# ============================================================================

EXPECTED_PURGE_PATHS = ("/", "/titles", "/feed.atom", "/feed.rss")


# ============================================================================
# Helpers
# ============================================================================


def _make_worker_with_purge_spy(feeds=None, admins=None):
    """Create an authenticated worker with a spy on _purge_edge_cache."""
    worker, env, session_cookie = make_authenticated_worker(feeds=feeds, admins=admins)
    worker._purge_edge_cache = AsyncMock()
    return worker, env, session_cookie


# ============================================================================
# Unit tests for _purge_edge_cache method
# ============================================================================


class TestPurgeEdgeCacheMethod:
    """Test the _purge_edge_cache method itself."""

    @pytest.mark.asyncio
    async def test_purge_calls_boundary_function(self):
        """_purge_edge_cache calls purge_edge_cache wrapper with correct args."""
        worker, env, _ = make_authenticated_worker()

        with patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_purge:
            result = await worker._purge_edge_cache()
            assert result is None  # void method
            mock_purge.assert_called_once()
            call_args = mock_purge.call_args
            # Should pass the base URL from PLANET_URL
            assert "https://test.example.com" in str(call_args)
            # Verify the first arg is the base URL string (not a tuple or other type)
            assert isinstance(call_args[0][0], str)
            assert call_args[0][0] == "https://test.example.com"
            # Verify the second arg is the CACHEABLE_PATHS tuple
            assert call_args[0][1] == EXPECTED_PURGE_PATHS

    @pytest.mark.asyncio
    async def test_purge_uses_cacheable_paths(self):
        """_purge_edge_cache purges all CACHEABLE_PATHS."""
        worker, env, _ = make_authenticated_worker()

        with patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_purge:
            await worker._purge_edge_cache()
            call_args = mock_purge.call_args
            # Second argument should be the paths tuple
            paths = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("paths")
            for path in EXPECTED_PURGE_PATHS:
                assert path in paths
            # Verify exact count — no extra paths snuck in
            assert len(paths) == len(EXPECTED_PURGE_PATHS)
            # Verify each path starts with /
            for path in paths:
                assert path.startswith("/"), f"Path must be relative: {path}"

    @pytest.mark.asyncio
    async def test_purge_no_planet_url_is_noop(self):
        """_purge_edge_cache does nothing when PLANET_URL is not set."""
        worker, env, _ = make_authenticated_worker()
        env.PLANET_URL = ""

        with patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_purge:
            result = await worker._purge_edge_cache()
            assert result is None
            mock_purge.assert_not_called()
            assert mock_purge.call_count == 0

    @pytest.mark.asyncio
    async def test_purge_failure_does_not_raise(self):
        """_purge_edge_cache swallows exceptions (best-effort)."""
        worker, env, _ = make_authenticated_worker()

        with patch(
            "src.main.purge_edge_cache",
            new_callable=AsyncMock,
            side_effect=Exception("Cache API unavailable"),
        ):
            # Should not raise — verify method completes successfully
            result = await worker._purge_edge_cache()
            # Method returns None (no error propagation)
            assert result is None


# ============================================================================
# Integration tests: admin actions trigger cache purging
# ============================================================================


class TestAdminActionsPurgeCache:
    """Verify that content-modifying admin actions call _purge_edge_cache."""

    @pytest.mark.asyncio
    async def test_add_feed_purges_cache(self):
        """Adding a feed triggers cache purge."""
        worker, env, session_cookie = _make_worker_with_purge_spy(
            feeds=[],
            admins=[admin_row()],
        )

        # Mock the feed validation to succeed
        worker._validate_feed_url = AsyncMock(
            return_value={
                "valid": True,
                "title": "New Feed",
                "site_url": "https://new.example.com",
                "entry_count": 5,
            }
        )

        request = MockRequest(
            url="https://test.example.com/admin/feeds",
            method="POST",
            cookies=session_cookie,
            form_data={"url": "https://new.example.com/feed.xml"},
        )
        response = await worker.fetch(request)

        assert response.status in (200, 302)
        assert response is not None
        worker._purge_edge_cache.assert_awaited_once()
        # Purge called exactly once, not multiple times per action
        assert worker._purge_edge_cache.await_count == 1
        # Feed validation should have been called with the submitted URL
        worker._validate_feed_url.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_feed_purges_cache(self):
        """Removing a feed triggers cache purge."""
        feeds = [
            {
                "id": 1,
                "url": "https://example.com/feed.xml",
                "title": "Test",
                "is_active": 1,
                "site_url": "https://example.com",
            }
        ]
        worker, env, session_cookie = _make_worker_with_purge_spy(
            feeds=feeds,
            admins=[admin_row()],
        )

        request = MockRequest(
            url="https://test.example.com/admin/feeds/1",
            method="DELETE",
            cookies=session_cookie,
        )
        response = await worker.fetch(request)

        assert response.status in (200, 302)
        assert response is not None
        worker._purge_edge_cache.assert_awaited_once()
        assert worker._purge_edge_cache.await_count == 1

    @pytest.mark.asyncio
    async def test_regenerate_purges_cache(self):
        """Regenerate triggers cache purge."""
        worker, env, session_cookie = _make_worker_with_purge_spy(
            admins=[admin_row()],
        )
        # Prevent actual scheduler run
        worker._run_scheduler = AsyncMock()

        request = MockRequest(
            url="https://test.example.com/admin/regenerate",
            method="POST",
            cookies=session_cookie,
        )
        response = await worker.fetch(request)

        assert response.status in (200, 302)
        assert response is not None
        worker._purge_edge_cache.assert_awaited_once()
        assert worker._purge_edge_cache.await_count == 1
        # Verify scheduler was also invoked (regenerate triggers both)
        worker._run_scheduler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_import_opml_purges_cache(self):
        """OPML import triggers cache purge."""
        worker, env, session_cookie = _make_worker_with_purge_spy(
            admins=[admin_row()],
        )
        # Mock the feed validation
        worker._validate_feed_url = AsyncMock(
            return_value={
                "valid": True,
                "title": "Imported",
                "site_url": "https://imported.example.com",
                "entry_count": 3,
            }
        )

        opml_content = """<?xml version="1.0"?>
        <opml version="2.0">
          <body>
            <outline type="rss" xmlUrl="https://imported.example.com/feed.xml"
                     title="Imported Feed" htmlUrl="https://imported.example.com"/>
          </body>
        </opml>"""

        request = MockRequest(
            url="https://test.example.com/admin/import-opml",
            method="POST",
            cookies=session_cookie,
            form_data={"opml": opml_content},
        )
        response = await worker.fetch(request)

        assert response.status in (200, 302)
        assert response is not None
        worker._purge_edge_cache.assert_awaited_once()
        assert worker._purge_edge_cache.await_count == 1

    @pytest.mark.asyncio
    async def test_fetch_now_purges_cache(self):
        """Synchronous feed fetch triggers cache purge."""
        feeds = [
            {
                "id": 1,
                "url": "https://example.com/feed.xml",
                "title": "Test",
                "is_active": 1,
                "site_url": "https://example.com",
                "etag": None,
                "last_modified": None,
            }
        ]
        worker, env, session_cookie = _make_worker_with_purge_spy(
            feeds=feeds,
            admins=[admin_row()],
        )
        # Mock the actual feed processing
        worker._process_single_feed = AsyncMock(
            return_value={"status": "ok", "entries_added": 2, "entries_found": 5}
        )

        request = MockRequest(
            url="https://test.example.com/admin/feeds/1/fetch-now",
            method="POST",
            cookies=session_cookie,
        )
        response = await worker.fetch(request)

        assert response.status == 200
        assert response is not None
        worker._purge_edge_cache.assert_awaited_once()
        assert worker._purge_edge_cache.await_count == 1
        # Verify the feed processing mock was called with feed ID 1
        worker._process_single_feed.assert_awaited_once()


class TestNonMutatingActionsSkipPurge:
    """Verify that read-only admin actions do NOT trigger cache purging."""

    @pytest.mark.asyncio
    async def test_view_dashboard_no_purge(self):
        """Viewing the admin dashboard does not purge cache."""
        worker, env, session_cookie = _make_worker_with_purge_spy(
            admins=[admin_row()],
        )

        request = MockRequest(
            url="https://test.example.com/admin",
            method="GET",
            cookies=session_cookie,
        )
        response = await worker.fetch(request)

        assert response.status == 200
        assert response is not None
        worker._purge_edge_cache.assert_not_awaited()
        assert worker._purge_edge_cache.await_count == 0

    @pytest.mark.asyncio
    async def test_list_feeds_no_purge(self):
        """Listing feeds does not purge cache."""
        worker, env, session_cookie = _make_worker_with_purge_spy(
            admins=[admin_row()],
        )

        request = MockRequest(
            url="https://test.example.com/admin/feeds",
            method="GET",
            cookies=session_cookie,
        )
        response = await worker.fetch(request)

        assert response.status == 200
        assert response is not None
        worker._purge_edge_cache.assert_not_awaited()
        assert worker._purge_edge_cache.await_count == 0

    @pytest.mark.asyncio
    async def test_view_dlq_no_purge(self):
        """Viewing DLQ does not purge cache."""
        worker, env, session_cookie = _make_worker_with_purge_spy(
            admins=[admin_row()],
        )

        request = MockRequest(
            url="https://test.example.com/admin/dlq",
            method="GET",
            cookies=session_cookie,
        )
        response = await worker.fetch(request)

        assert response.status == 200
        assert response is not None
        worker._purge_edge_cache.assert_not_awaited()
        assert worker._purge_edge_cache.await_count == 0


# ============================================================================
# Boundary-layer tests for purge_edge_cache wrapper
# ============================================================================


class TestPurgeEdgeCacheBoundary:
    """Test the purge_edge_cache boundary-layer function in wrappers.py."""

    @pytest.mark.asyncio
    async def test_purge_in_test_env_is_noop(self):
        """In test env (no Pyodide), purge_edge_cache succeeds silently."""
        from wrappers import purge_edge_cache

        # Should not raise
        result = await purge_edge_cache("https://test.example.com", EXPECTED_PURGE_PATHS)
        assert result == 0  # 0 paths purged in test env
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_purge_returns_count(self):
        """purge_edge_cache returns the number of paths purged."""
        from wrappers import purge_edge_cache

        result = await purge_edge_cache("https://test.example.com", ("/", "/titles"))
        # In test env, returns 0 (no actual cache to purge)
        assert isinstance(result, int)
        assert result >= 0
        assert result <= 2  # Can't purge more paths than requested


# ============================================================================
# Property-Based Tests (Hypothesis)
# ============================================================================

# Strategy: valid base URLs
base_urls = st.from_regex(r"https://[a-z][a-z0-9\-]{1,20}\.[a-z]{2,6}", fullmatch=True)

# Strategy: path tuples (1-10 paths, each starting with /)
path_elements = st.from_regex(r"/[a-z][a-z0-9\.\-]{0,20}", fullmatch=True)
path_tuples = st.lists(path_elements, min_size=1, max_size=10).map(tuple)


class TestPurgeEdgeCacheProperties:
    """Property-based tests for purge_edge_cache invariants."""

    @given(base_url=base_urls, paths=path_tuples)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_purge_never_raises_in_test_env(self, base_url, paths):
        """purge_edge_cache never raises for any valid URL/path combination."""
        from wrappers import purge_edge_cache

        result = await purge_edge_cache(base_url, paths)
        assert result == 0  # Test env always returns 0
        assert isinstance(result, int)

    @given(base_url=base_urls, paths=path_tuples)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_purge_return_bounded_by_path_count(self, base_url, paths):
        """Purge count can never exceed the number of paths requested."""
        from wrappers import purge_edge_cache

        result = await purge_edge_cache(base_url, paths)
        assert isinstance(result, int)
        assert 0 <= result <= len(paths)

    @given(base_url=base_urls)
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_purge_empty_paths_returns_zero(self, base_url):
        """Purging with no paths always returns 0."""
        from wrappers import purge_edge_cache

        result = await purge_edge_cache(base_url, ())
        assert result == 0
        assert isinstance(result, int)

    @given(data=st.data())
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_purge_idempotent(self, data):
        """Calling purge twice with the same args gives the same result."""
        from wrappers import purge_edge_cache

        base_url = data.draw(base_urls)
        paths = data.draw(path_tuples)

        result1 = await purge_edge_cache(base_url, paths)
        result2 = await purge_edge_cache(base_url, paths)
        assert result1 == result2
        assert isinstance(result1, int)
        assert isinstance(result2, int)

    @pytest.mark.asyncio
    async def test_cacheable_paths_constant_matches_prewarm(self):
        """CACHEABLE_PATHS must match the paths pre-warmed by cron.

        This is a structural invariant: if the prewarm set and the purge
        set diverge, we'll either purge paths that are never cached or
        miss purging paths that are.
        """
        from src.main import CACHEABLE_PATHS

        # These are the paths pre-warmed in scheduled() — kept in sync
        # by this test. If someone changes one, this test forces them to
        # update the other.
        PREWARM_PATHS = ("/", "/titles", "/feed.atom", "/feed.rss")
        assert set(CACHEABLE_PATHS) == set(PREWARM_PATHS)
        # Verify exact count — no silent additions or removals
        assert len(CACHEABLE_PATHS) == len(PREWARM_PATHS)
        # Verify the test constant matches too
        assert set(CACHEABLE_PATHS) == set(EXPECTED_PURGE_PATHS)

    @given(
        base_url=st.just(""),
        paths=path_tuples,
    )
    @settings(max_examples=20, deadline=None)
    @pytest.mark.asyncio
    async def test_purge_method_skips_empty_base_url(self, base_url, paths):
        """_purge_edge_cache is a no-op when PLANET_URL is empty."""
        worker, env, _ = make_authenticated_worker()
        env.PLANET_URL = base_url

        with patch("src.main.purge_edge_cache", new_callable=AsyncMock) as mock_purge:
            await worker._purge_edge_cache()
            mock_purge.assert_not_called()
