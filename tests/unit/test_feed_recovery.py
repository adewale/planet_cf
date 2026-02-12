"""Tests for automatic feed recovery.

The scheduler should periodically attempt to re-enable disabled feeds.
If the underlying issue is fixed, the feed stays active. If not,
normal error handling will re-disable it.
"""

import re
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).parent.parent.parent


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


class TestSchedulerRecoveryCode:
    """Verify the recovery section exists in _run_scheduler."""

    def test_recovery_section_in_scheduler(self):
        """_run_scheduler should contain feed recovery logic."""
        source = (PROJECT_ROOT / "src" / "main.py").read_text()
        assert "feed_recovery_attempt" in source, (
            "Scheduler should log feed_recovery_attempt events"
        )
        assert "is_recovery_attempt" in source, (
            "Recovery messages should have is_recovery_attempt flag"
        )

    def test_recovery_queries_inactive_feeds(self):
        """Recovery section should query WHERE is_active = 0."""
        source = (PROJECT_ROOT / "src" / "main.py").read_text()
        # Find the recovery section
        match = re.search(
            r"Auto-recovery.*?feeds_recovery_attempted",
            source,
            re.DOTALL,
        )
        assert match, "Could not find recovery section in scheduler"
        recovery_code = match.group()
        assert "is_active = 0" in recovery_code, (
            "Recovery should query disabled feeds (is_active = 0)"
        )

    def test_recovery_resets_failures_before_enqueue(self):
        """Recovery should reset consecutive_failures before re-enqueuing."""
        source = (PROJECT_ROOT / "src" / "main.py").read_text()
        match = re.search(
            r"Auto-recovery.*?feeds_recovery_attempted",
            source,
            re.DOTALL,
        )
        assert match, "Could not find recovery section"
        recovery_code = match.group()
        assert "consecutive_failures = 0" in recovery_code
        assert "is_active = 1" in recovery_code


class TestSchedulerEventRecoveryField:
    """Verify SchedulerEvent has recovery tracking."""

    def test_scheduler_event_has_recovery_field(self):
        """SchedulerEvent should track feeds_recovery_attempted."""
        from src.observability import SchedulerEvent

        event = SchedulerEvent()
        assert hasattr(event, "feeds_recovery_attempted")
        assert event.feeds_recovery_attempted == 0
