# tests/unit/test_feed_error.py
"""Unit tests for _record_feed_error and _update_feed_url in src/main.py."""

import json

import pytest

from src.main import Default
from tests.conftest import MockD1Statement

# =============================================================================
# Mock Infrastructure
# =============================================================================


class TrackingD1Statement(MockD1Statement):
    """Extends MockD1Statement with SQL and bound_args tracking."""

    def __init__(self, results: list[dict] | None = None, sql: str = ""):
        super().__init__(results or [], sql)
        self.bound_args: list = []

    def bind(self, *args) -> "TrackingD1Statement":
        self.bound_args = list(args)
        self._bound_args = args
        return self


class TrackingD1:
    """Mock D1 database that tracks all prepared statements."""

    def __init__(self, default_results: list[dict] | None = None):
        self._default_results = default_results or []
        self.statements: list[TrackingD1Statement] = []

    def prepare(self, sql: str) -> TrackingD1Statement:
        stmt = TrackingD1Statement(self._default_results, sql)
        stmt.sql = sql
        self.statements.append(stmt)
        return stmt


class MockEnv:
    """Mock Cloudflare Workers environment for feed error tests."""

    def __init__(self, db: TrackingD1 | None = None):
        self.DB = db or TrackingD1()
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = None
        self.DEAD_LETTER_QUEUE = None
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"


def _make_worker(
    consecutive_failures: int = 0,
    is_active: int = 1,
    threshold: str | None = None,
) -> tuple[Default, TrackingD1]:
    """Create a Default worker with mock env for feed error tests.

    Returns the worker and the tracking D1 for assertions.
    """
    # The UPDATE ... RETURNING consecutive_failures, is_active
    # simulates what D1 returns after the update
    new_failures = consecutive_failures + 1
    deactivate_threshold = (
        int(threshold) if threshold else 10
    )  # DEFAULT_FEED_AUTO_DEACTIVATE_THRESHOLD
    new_is_active = 0 if new_failures >= deactivate_threshold else is_active

    db = TrackingD1([{"consecutive_failures": new_failures, "is_active": new_is_active}])
    env = MockEnv(db=db)
    if threshold is not None:
        env.FEED_AUTO_DEACTIVATE_THRESHOLD = threshold

    worker = Default()
    worker.env = env
    return worker, db


# =============================================================================
# Tests: _record_feed_error
# =============================================================================


class TestRecordFeedError:
    """Tests for Default._record_feed_error method."""

    @pytest.mark.asyncio
    async def test_error_recorded_with_failure_increment(self):
        """Feed error is recorded and consecutive_failures is incremented."""
        worker, db = _make_worker(consecutive_failures=2)

        await worker._record_feed_error(42, "Connection timeout")

        # Verify UPDATE was executed
        assert len(db.statements) >= 1
        update_stmt = db.statements[0]
        assert "UPDATE feeds" in update_stmt.sql
        assert "consecutive_failures = consecutive_failures + 1" in update_stmt.sql

        # Verify the error message is in bound args (truncated to 500 chars)
        assert "Connection timeout" in update_stmt.bound_args
        # Verify feed_id is in bound args
        assert 42 in update_stmt.bound_args

    @pytest.mark.asyncio
    async def test_feed_auto_deactivated_at_threshold(self):
        """Feed is auto-deactivated when consecutive_failures reaches threshold."""
        # Feed already has 9 failures, threshold is 10 (default)
        # After this error, consecutive_failures = 10 >= 10, so is_active -> 0
        worker, db = _make_worker(consecutive_failures=9, threshold="10")

        await worker._record_feed_error(42, "Server error")

        # The SQL should contain the CASE statement for auto-deactivation
        update_stmt = db.statements[0]
        assert "CASE WHEN consecutive_failures + 1 >=" in update_stmt.sql
        assert "THEN 0" in update_stmt.sql

    @pytest.mark.asyncio
    async def test_feed_not_deactivated_below_threshold(self):
        """Feed is NOT deactivated when consecutive_failures is below threshold."""
        # Feed has 2 failures, threshold is 10
        # After this error, consecutive_failures = 3 < 10
        worker, db = _make_worker(consecutive_failures=2, threshold="10")

        await worker._record_feed_error(42, "Temporary error")

        # The UPDATE was executed
        assert len(db.statements) >= 1
        update_stmt = db.statements[0]
        assert "UPDATE feeds" in update_stmt.sql

    @pytest.mark.asyncio
    async def test_error_message_stored(self):
        """The error message is stored in fetch_error field."""
        worker, db = _make_worker()

        await worker._record_feed_error(42, "HTTP error 503")

        update_stmt = db.statements[0]
        assert "fetch_error = ?" in update_stmt.sql
        assert "HTTP error 503" in update_stmt.bound_args

    @pytest.mark.asyncio
    async def test_long_error_message_truncated(self):
        """Error messages longer than 500 chars are truncated."""
        worker, db = _make_worker()

        long_error = "x" * 1000
        await worker._record_feed_error(42, long_error)

        update_stmt = db.statements[0]
        # The bound error message should be truncated to 500 chars
        error_arg = update_stmt.bound_args[0]
        assert len(error_arg) == 500

    @pytest.mark.asyncio
    async def test_threshold_passed_to_query(self):
        """The auto-deactivation threshold is passed as bind parameter."""
        worker, db = _make_worker(threshold="5")

        await worker._record_feed_error(42, "Error")

        update_stmt = db.statements[0]
        # The threshold should be in the bound args
        assert 5 in update_stmt.bound_args

    @pytest.mark.asyncio
    async def test_custom_threshold_from_env(self):
        """Uses custom threshold from environment variable."""
        worker, db = _make_worker(consecutive_failures=4, threshold="5")

        await worker._record_feed_error(42, "Error")

        update_stmt = db.statements[0]
        # Threshold 5 should be in bound args
        assert 5 in update_stmt.bound_args


# =============================================================================
# Tests: _update_feed_url
# =============================================================================


class TestUpdateFeedUrl:
    """Tests for Default._update_feed_url method."""

    @pytest.mark.asyncio
    async def test_url_updated_on_permanent_redirect(self):
        """Feed URL is updated in database on permanent redirect."""
        db = TrackingD1([{"url": "https://old.example.com/feed.xml"}])
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env

        await worker._update_feed_url(
            42,
            "https://new.example.com/feed.xml",
            old_url="https://old.example.com/feed.xml",
        )

        # Find the UPDATE statement
        update_stmts = [s for s in db.statements if "UPDATE feeds" in s.sql and "url = ?" in s.sql]
        assert len(update_stmts) == 1
        assert "https://new.example.com/feed.xml" in update_stmts[0].bound_args
        assert 42 in update_stmts[0].bound_args

    @pytest.mark.asyncio
    async def test_audit_log_entry_created(self):
        """An audit log entry is created when URL is updated."""
        db = TrackingD1([{"url": "https://old.example.com/feed.xml"}])
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env

        await worker._update_feed_url(
            42,
            "https://new.example.com/feed.xml",
            old_url="https://old.example.com/feed.xml",
        )

        # Find the INSERT INTO audit_log statement
        audit_stmts = [s for s in db.statements if "INSERT INTO audit_log" in s.sql]
        assert len(audit_stmts) == 1
        audit_stmt = audit_stmts[0]
        # Verify the action is "url_updated"
        assert "url_updated" in audit_stmt.bound_args
        # Verify feed is the target type
        assert "feed" in audit_stmt.bound_args
        # Verify feed_id is the target
        assert 42 in audit_stmt.bound_args

    @pytest.mark.asyncio
    async def test_old_url_preserved_in_audit_log(self):
        """The old URL is preserved in the audit log details."""
        db = TrackingD1([{"url": "https://old.example.com/feed.xml"}])
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env

        await worker._update_feed_url(
            42,
            "https://new.example.com/feed.xml",
            old_url="https://old.example.com/feed.xml",
        )

        # Find the audit log INSERT
        audit_stmts = [s for s in db.statements if "INSERT INTO audit_log" in s.sql]
        assert len(audit_stmts) == 1

        # The details should be a JSON string containing old and new URLs
        details_json = audit_stmts[0].bound_args[-1]
        details = json.loads(details_json)
        assert details["old_url"] == "https://old.example.com/feed.xml"
        assert details["new_url"] == "https://new.example.com/feed.xml"

    @pytest.mark.asyncio
    async def test_old_url_fetched_when_not_provided(self):
        """When old_url is not provided, it's fetched from the database."""
        db = TrackingD1([{"url": "https://old.example.com/feed.xml"}])
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env

        await worker._update_feed_url(42, "https://new.example.com/feed.xml")

        # First statement should be the SELECT to get old URL
        select_stmts = [s for s in db.statements if "SELECT url FROM feeds" in s.sql]
        assert len(select_stmts) == 1

    @pytest.mark.asyncio
    async def test_uses_system_admin_id_for_auto_updates(self):
        """Auto URL updates (not triggered by admin) use admin_id=0."""
        db = TrackingD1([])
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env

        await worker._update_feed_url(
            42,
            "https://new.example.com/feed.xml",
            old_url="https://old.example.com/feed.xml",
        )

        # The audit log should use admin_id=0 (system user)
        audit_stmts = [s for s in db.statements if "INSERT INTO audit_log" in s.sql]
        assert len(audit_stmts) == 1
        assert audit_stmts[0].bound_args[0] == 0  # admin_id
