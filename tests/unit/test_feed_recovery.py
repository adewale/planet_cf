"""Tests for automatic feed recovery.

The scheduler should periodically attempt to re-enable disabled feeds.
If the underlying issue is fixed, the feed stays active. If not,
normal error handling will re-disable it.
"""

from unittest.mock import MagicMock

from tests.conftest import MockEnv, MockQueue
from tests.mocks.sqlite_d1 import SQLiteD1


class TestFeedRecoveryConfig:
    """Verify recovery config constants and getters exist."""

    def test_recovery_constants_exist(self):
        """Config module should define recovery constants."""
        import src.config as config

        assert hasattr(config, "DEFAULT_FEED_RECOVERY_ENABLED")
        assert hasattr(config, "DEFAULT_FEED_RECOVERY_LIMIT")
        assert config.DEFAULT_FEED_RECOVERY_ENABLED is True
        assert config.DEFAULT_FEED_RECOVERY_LIMIT == 2

    def test_recovery_in_config_registry(self):
        """feed_recovery_limit should be in the config registry."""
        from src.config import _INT_CONFIG_REGISTRY

        assert "feed_recovery_limit" in _INT_CONFIG_REGISTRY

    def test_get_feed_recovery_enabled_default(self):
        """get_feed_recovery_enabled returns True by default."""
        from src.config import get_feed_recovery_enabled

        env = MagicMock(spec=[])  # No attributes
        assert get_feed_recovery_enabled(env) is True

    def test_get_feed_recovery_enabled_false(self):
        """get_feed_recovery_enabled returns False when env var is 'false'."""
        from src.config import get_feed_recovery_enabled

        env = MagicMock()
        env.FEED_RECOVERY_ENABLED = "false"
        assert get_feed_recovery_enabled(env) is False

    def test_get_feed_recovery_enabled_zero(self):
        """get_feed_recovery_enabled returns False when env var is '0'."""
        from src.config import get_feed_recovery_enabled

        env = MagicMock()
        env.FEED_RECOVERY_ENABLED = "0"
        assert get_feed_recovery_enabled(env) is False

    def test_get_feed_recovery_limit_default(self):
        """get_feed_recovery_limit returns 2 by default."""
        from src.config import get_feed_recovery_limit

        env = MagicMock(spec=[])
        assert get_feed_recovery_limit(env) == 2


class TestSchedulerRecovery:
    """_run_scheduler re-enables and re-enqueues disabled feeds, on a real SQLite schema."""

    async def test_recovery_reenables_and_enqueues_up_to_the_limit(self):
        """Up to FEED_RECOVERY_LIMIT (default 2) disabled feeds are reset and re-enqueued.

        The rest stay disabled with their failure state intact, and active feeds
        are enqueued as normal fetches.
        """
        from src.main import PlanetCF

        db = SQLiteD1.from_migrations()
        active_id = db.insert("feeds", url="https://active.example/feed", is_active=1)
        seeded_failures = {
            db.insert(
                "feeds",
                url=f"https://disabled{n}.example/feed",
                is_active=0,
                consecutive_failures=10 + n,
                fetch_error=f"HTTP 50{n}",
                updated_at=f"2026-01-0{n} 00:00:00",
            ): 10 + n
            for n in (1, 2, 3)
        }
        disabled_ids = set(seeded_failures)
        queue = MockQueue()
        worker = PlanetCF()
        worker.env = MockEnv(
            DB=db,
            FEED_QUEUE=queue,
            DEAD_LETTER_QUEUE=MockQueue(),
            SEARCH_INDEX=None,
            AI=None,
            PLANET_URL="",  # no cache pre-warm requests
        )

        result = await worker._run_scheduler()

        normal = [m for m in queue.messages if not m.get("is_recovery_attempt")]
        recovery = [m for m in queue.messages if m.get("is_recovery_attempt") is True]
        assert [m["feed_id"] for m in normal] == [active_id]
        recovered_ids = {m["feed_id"] for m in recovery}
        assert len(recovered_ids) == 2
        assert recovered_ids < disabled_ids
        assert result["enqueued"] == 3

        rows = {r["id"]: r for r in db.rows("SELECT * FROM feeds")}
        for feed_id in recovered_ids:
            assert rows[feed_id]["is_active"] == 1
            assert rows[feed_id]["consecutive_failures"] == 0
            assert rows[feed_id]["fetch_error"] is None
        (still_disabled,) = disabled_ids - recovered_ids
        assert rows[still_disabled]["is_active"] == 0
        assert rows[still_disabled]["consecutive_failures"] == seeded_failures[still_disabled]
        assert rows[still_disabled]["fetch_error"] is not None


class TestSchedulerEventRecoveryField:
    """Verify SchedulerEvent has recovery tracking."""

    def test_scheduler_event_has_recovery_field(self):
        """SchedulerEvent should track feeds_recovery_attempted."""
        from src.observability import SchedulerEvent

        event = SchedulerEvent()
        assert hasattr(event, "feeds_recovery_attempted")
        assert event.feeds_recovery_attempted == 0
