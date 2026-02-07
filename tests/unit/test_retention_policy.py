# tests/unit/test_retention_policy.py
"""Unit tests for _apply_retention_policy in src/main.py."""

from dataclasses import dataclass

import pytest

from src.main import Default

# =============================================================================
# Mock infrastructure for retention policy tests
# =============================================================================


@dataclass
class MockD1Result:
    """Mock D1 query result."""

    results: list[dict]
    success: bool = True


class MockD1Statement:
    """Mock D1 prepared statement that captures SQL and bound parameters."""

    def __init__(self, results: list[dict] | None = None):
        self._results = results or []
        self.sql = ""
        self.bound_args: list = []

    def bind(self, *args) -> "MockD1Statement":
        self.bound_args = list(args)
        return self

    async def all(self) -> MockD1Result:
        return MockD1Result(results=self._results)

    async def first(self) -> dict | None:
        return self._results[0] if self._results else None

    async def run(self) -> MockD1Result:
        return MockD1Result(results=[])


class MockD1ForRetention:
    """Mock D1 database that returns specific results per query pattern."""

    def __init__(
        self,
        entries_to_delete: list[dict] | None = None,
    ):
        self._entries_to_delete = entries_to_delete or []
        self.statements: list[MockD1Statement] = []

    def prepare(self, sql: str) -> MockD1Statement:
        sql_lower = sql.lower()
        if "select id from entries_to_delete" in sql_lower or "ranked_entries" in sql_lower:
            stmt = MockD1Statement(self._entries_to_delete)
        else:
            stmt = MockD1Statement([])
        stmt.sql = sql
        self.statements.append(stmt)
        return stmt


class MockVectorize:
    """Mock Vectorize index for retention tests."""

    def __init__(self):
        self.deleted_ids: list[list[str]] = []

    async def deleteByIds(self, ids: list[str]) -> None:
        self.deleted_ids.append(ids)


class MockRetentionEnv:
    """Mock environment for retention policy tests."""

    def __init__(
        self,
        entries_to_delete: list[dict] | None = None,
        search_index: MockVectorize | None = None,
        retention_days: str | None = None,
        max_entries_per_feed: str | None = None,
    ):
        self.DB = MockD1ForRetention(entries_to_delete)
        self.SEARCH_INDEX = search_index
        self.AI = None
        self.FEED_QUEUE = None
        self.DEAD_LETTER_QUEUE = None
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"
        if retention_days is not None:
            self.RETENTION_DAYS = retention_days
        if max_entries_per_feed is not None:
            self.RETENTION_MAX_ENTRIES_PER_FEED = max_entries_per_feed


# =============================================================================
# Retention Policy Tests
# =============================================================================


class TestApplyRetentionPolicy:
    """Tests for Default._apply_retention_policy."""

    @pytest.mark.asyncio
    async def test_entries_older_than_retention_targeted(self):
        """Entries older than retention days are identified for deletion."""
        old_entries = [
            {"id": 1},
            {"id": 2},
            {"id": 3},
        ]
        vectorize = MockVectorize()
        env = MockRetentionEnv(entries_to_delete=old_entries, search_index=vectorize)

        worker = Default()
        worker.env = env

        stats = await worker._apply_retention_policy()

        assert stats["entries_scanned"] == 3
        assert stats["entries_deleted"] == 3
        assert stats["vectors_deleted"] == 3
        # Verify the cutoff date was passed via bind params
        select_stmt = env.DB.statements[0]
        assert len(select_stmt.bound_args) == 2  # max_per_feed, cutoff_date

    @pytest.mark.asyncio
    async def test_empty_database_no_deletions(self):
        """Handles empty database gracefully with no deletions."""
        env = MockRetentionEnv(entries_to_delete=[])

        worker = Default()
        worker.env = env

        stats = await worker._apply_retention_policy()

        assert stats["entries_scanned"] == 0
        assert stats["entries_deleted"] == 0
        assert stats["vectors_deleted"] == 0
        assert stats["errors"] == 0

    @pytest.mark.asyncio
    async def test_uses_correct_retention_days_from_config(self):
        """Uses retention_days from env config."""
        env = MockRetentionEnv(
            entries_to_delete=[],
            retention_days="30",
            max_entries_per_feed="25",
        )

        worker = Default()
        worker.env = env

        stats = await worker._apply_retention_policy()

        assert stats["retention_days"] == 30
        assert stats["max_per_feed"] == 25

    @pytest.mark.asyncio
    async def test_uses_default_retention_days(self):
        """Uses default retention days when not configured."""
        from src.config import DEFAULT_MAX_ENTRIES_PER_FEED, DEFAULT_RETENTION_DAYS

        env = MockRetentionEnv(entries_to_delete=[])

        worker = Default()
        worker.env = env

        stats = await worker._apply_retention_policy()

        assert stats["retention_days"] == DEFAULT_RETENTION_DAYS
        assert stats["max_per_feed"] == DEFAULT_MAX_ENTRIES_PER_FEED

    @pytest.mark.asyncio
    async def test_vectorize_delete_error_handled_gracefully(self):
        """Vectorize errors are caught and don't prevent D1 deletion."""

        class FailingVectorize:
            async def deleteByIds(self, ids):
                raise RuntimeError("Vectorize unavailable")

        old_entries = [{"id": 10}, {"id": 20}]
        env = MockRetentionEnv(
            entries_to_delete=old_entries,
            search_index=FailingVectorize(),
        )

        worker = Default()
        worker.env = env

        stats = await worker._apply_retention_policy()

        # Entries should still be deleted from D1 despite vectorize failure
        assert stats["entries_deleted"] == 2
        assert stats["errors"] == 1
        assert stats["vectors_deleted"] == 0

    @pytest.mark.asyncio
    async def test_no_search_index_skips_vectorize(self):
        """When SEARCH_INDEX is None, vector deletion is skipped."""
        old_entries = [{"id": 1}]
        env = MockRetentionEnv(entries_to_delete=old_entries, search_index=None)

        worker = Default()
        worker.env = env

        stats = await worker._apply_retention_policy()

        assert stats["entries_deleted"] == 1
        assert stats["vectors_deleted"] == 0
