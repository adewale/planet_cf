# tests/unit/test_admin_context.py
"""Tests for the admin action context manager."""

import pytest

from src.admin_context import (
    AdminActionContext,
    _truncate_error,
    admin_action_context,
    create_admin_event,
)
from src.observability import AdminActionEvent, Timer


class TestTruncateError:
    """Tests for error message truncation."""

    def test_short_message_unchanged(self):
        """Short messages are returned unchanged."""
        result = _truncate_error("Short error")
        assert result == "Short error"

    def test_long_message_truncated(self):
        """Long messages are truncated with ellipsis."""
        long_message = "A" * 250
        result = _truncate_error(long_message, max_length=200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_exception_converted_to_string(self):
        """Exception objects are converted to strings."""
        exc = ValueError("Test error")
        result = _truncate_error(exc)
        assert result == "Test error"


class TestCreateAdminEvent:
    """Tests for admin event creation."""

    def test_creates_event_with_admin_info(self):
        """Creates event with admin username and ID."""
        admin = {"github_username": "testuser", "id": 42}
        deployment = {"worker_version": "v1", "deployment_environment": "test"}

        event = create_admin_event(admin, "add_feed", "feed", deployment)

        assert event.admin_username == "testuser"
        assert event.admin_id == 42
        assert event.action == "add_feed"
        assert event.target_type == "feed"
        assert event.worker_version == "v1"
        assert event.deployment_environment == "test"

    def test_handles_missing_admin_fields(self):
        """Handles missing fields in admin dict gracefully."""
        admin = {}
        deployment = {}

        event = create_admin_event(admin, "remove_feed", "feed", deployment)

        assert event.admin_username == ""
        assert event.admin_id == 0
        assert event.action == "remove_feed"


class TestAdminActionContext:
    """Tests for AdminActionContext dataclass."""

    def test_set_target_id(self):
        """set_target_id updates event target_id."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        ctx.set_target_id(123)

        assert event.target_id == 123

    def test_set_success(self):
        """set_success marks operation successful."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        ctx.set_success()

        assert ctx._success is True
        assert event.outcome == "success"

    def test_set_error(self):
        """set_error updates event error fields."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        ctx.set_error("ValidationError", "Invalid input")

        assert event.outcome == "error"
        assert event.error_type == "ValidationError"
        assert event.error_message == "Invalid input"

    def test_set_error_truncates_long_message(self):
        """set_error truncates long error messages."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        long_message = "A" * 300
        ctx.set_error("TestError", long_message)

        assert len(event.error_message) == 200
        assert event.error_message.endswith("...")

    def test_set_error_from_exception(self):
        """set_error_from_exception extracts type and message."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        exc = ValueError("Something went wrong")
        ctx.set_error_from_exception(exc)

        assert event.error_type == "ValueError"
        assert event.error_message == "Something went wrong"

    def test_set_import_metrics(self):
        """set_import_metrics updates OPML import fields."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        ctx.set_import_metrics(
            file_size=1000,
            feeds_parsed=20,
            feeds_added=18,
            feeds_skipped=2,
            errors=1,
        )

        assert event.import_file_size == 1000
        assert event.import_feeds_parsed == 20
        assert event.import_feeds_added == 18
        assert event.import_feeds_skipped == 2
        assert event.import_errors == 1

    def test_set_import_metrics_partial(self):
        """set_import_metrics handles partial updates."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        ctx.set_import_metrics(feeds_added=5)

        assert event.import_feeds_added == 5
        assert event.import_file_size is None

    def test_set_reindex_metrics(self):
        """set_reindex_metrics updates reindex fields."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        ctx.set_reindex_metrics(
            entries_total=100,
            entries_indexed=98,
            entries_failed=2,
        )

        assert event.reindex_entries_total == 100
        assert event.reindex_entries_indexed == 98
        assert event.reindex_entries_failed == 2

    def test_set_dlq_metrics(self):
        """set_dlq_metrics updates DLQ fields."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        ctx.set_dlq_metrics(
            feed_id=42,
            original_error="Connection timeout",
            action="retry",
        )

        assert event.dlq_feed_id == 42
        assert event.dlq_original_error == "Connection timeout"
        assert event.dlq_action == "retry"

    def test_set_dlq_metrics_truncates_error(self):
        """set_dlq_metrics truncates long error messages."""
        event = AdminActionEvent()
        timer = Timer()
        ctx = AdminActionContext(event=event, timer=timer)

        long_error = "E" * 300
        ctx.set_dlq_metrics(original_error=long_error)

        assert len(event.dlq_original_error) == 200


class TestAdminActionContextManager:
    """Tests for admin_action_context async context manager."""

    @pytest.mark.asyncio
    async def test_successful_operation(self):
        """Context manager handles successful operation."""
        admin = {"github_username": "test", "id": 1}
        deployment = {"worker_version": "v1", "deployment_environment": "test"}

        async with admin_action_context(admin, "add_feed", "feed", deployment) as ctx:
            ctx.set_target_id(123)
            ctx.set_success()

        assert ctx.event.outcome == "success"
        assert ctx.event.wall_time_ms > 0

    @pytest.mark.asyncio
    async def test_exception_sets_error(self):
        """Context manager sets error on exception."""
        admin = {"github_username": "test", "id": 1}
        deployment = {}

        with pytest.raises(ValueError):
            async with admin_action_context(admin, "add_feed", "feed", deployment) as ctx:
                raise ValueError("Test error")

        assert ctx.event.outcome == "error"
        assert ctx.event.error_type == "ValueError"
        assert ctx.event.error_message == "Test error"

    @pytest.mark.asyncio
    async def test_timing_measurement(self):
        """Context manager measures wall time."""
        import asyncio

        admin = {"github_username": "test", "id": 1}
        deployment = {}

        async with admin_action_context(admin, "test_action", "test", deployment) as ctx:
            await asyncio.sleep(0.01)  # 10ms
            ctx.set_success()

        assert ctx.event.wall_time_ms >= 10

    @pytest.mark.asyncio
    async def test_reindex_sets_total_ms(self):
        """Reindex action also sets reindex_total_ms."""
        admin = {"github_username": "test", "id": 1}
        deployment = {}

        async with admin_action_context(admin, "reindex", "search_index", deployment) as ctx:
            ctx.set_success()

        assert ctx.event.reindex_total_ms == ctx.event.wall_time_ms

    @pytest.mark.asyncio
    async def test_log_action_callback(self):
        """Context manager calls log action callback."""
        admin = {"github_username": "test", "id": 1}
        deployment = {}
        logged_args = []

        async def mock_log_action(*args):
            logged_args.append(args)

        async with admin_action_context(
            admin,
            "add_feed",
            "feed",
            deployment,
            log_action_callback=mock_log_action,
        ) as ctx:
            await ctx.log_action(1, "add_feed", "feed", 123, {"url": "http://test.com"})
            ctx.set_success()

        assert len(logged_args) == 1
        assert logged_args[0] == (1, "add_feed", "feed", 123, {"url": "http://test.com"})

    @pytest.mark.asyncio
    async def test_log_action_no_callback(self):
        """log_action handles missing callback gracefully."""
        admin = {"github_username": "test", "id": 1}
        deployment = {}

        async with admin_action_context(admin, "add_feed", "feed", deployment) as ctx:
            # Should not raise
            await ctx.log_action(1, "add_feed", "feed", 123, {})
            ctx.set_success()
