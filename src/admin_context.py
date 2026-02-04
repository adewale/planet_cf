# src/admin_context.py
"""Admin action context manager for standardized admin operation handling.

This module provides the AdminActionWrapper class that encapsulates the
repetitive pattern used in admin operations:
- Create admin event with deployment context
- Wrap operation in Timer
- Handle success/error outcomes
- Emit event in finally block

Usage:
    async with AdminActionWrapper(
        worker=self,
        admin=admin,
        action="add_feed",
        target_type="feed"
    ) as ctx:
        # Perform the operation
        ctx.set_target_id(feed_id)
        await do_something()
        ctx.log_action(admin_id, "add_feed", "feed", feed_id, {"url": url})
        ctx.set_success()
        return some_response

    # Event is automatically emitted with timing
"""

from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from observability import AdminActionEvent, Timer, emit_event
from utils import truncate_error as _truncate_error


@dataclass
class AdminActionContext:
    """Context object for admin action operations.

    Provides methods to update the admin event and track operation state.
    """

    event: AdminActionEvent
    timer: Timer
    _log_action_callback: Callable[..., Coroutine[Any, Any, None]] | None = None
    _success: bool = False

    def set_target_id(self, target_id: int | None) -> None:
        """Set the target ID on the admin event."""
        self.event.target_id = target_id

    def set_success(self) -> None:
        """Mark the operation as successful."""
        self._success = True
        self.event.outcome = "success"

    def set_error(
        self,
        error_type: str,
        error_message: str,
    ) -> None:
        """Set error information on the admin event."""
        self.event.outcome = "error"
        self.event.error_type = error_type
        self.event.error_message = _truncate_error(error_message)

    def set_error_from_exception(self, exc: Exception) -> None:
        """Set error information from an exception."""
        self.set_error(type(exc).__name__, str(exc))

    # OPML import fields
    def set_import_metrics(
        self,
        file_size: int | None = None,
        feeds_parsed: int | None = None,
        feeds_added: int | None = None,
        feeds_skipped: int | None = None,
        errors: int | None = None,
    ) -> None:
        """Set OPML import metrics on the admin event."""
        if file_size is not None:
            self.event.import_file_size = file_size
        if feeds_parsed is not None:
            self.event.import_feeds_parsed = feeds_parsed
        if feeds_added is not None:
            self.event.import_feeds_added = feeds_added
        if feeds_skipped is not None:
            self.event.import_feeds_skipped = feeds_skipped
        if errors is not None:
            self.event.import_errors = errors

    # Reindex fields
    def set_reindex_metrics(
        self,
        entries_total: int | None = None,
        entries_indexed: int | None = None,
        entries_failed: int | None = None,
    ) -> None:
        """Set reindex metrics on the admin event."""
        if entries_total is not None:
            self.event.reindex_entries_total = entries_total
        if entries_indexed is not None:
            self.event.reindex_entries_indexed = entries_indexed
        if entries_failed is not None:
            self.event.reindex_entries_failed = entries_failed

    # DLQ fields
    def set_dlq_metrics(
        self,
        feed_id: int | None = None,
        original_error: str | None = None,
        action: str | None = None,
    ) -> None:
        """Set DLQ metrics on the admin event."""
        if feed_id is not None:
            self.event.dlq_feed_id = feed_id
        if original_error is not None:
            self.event.dlq_original_error = original_error[:200]
        if action is not None:
            self.event.dlq_action = action

    async def log_action(
        self,
        admin_id: int | None,
        action: str | None,
        target_type: str | None,
        target_id: int | None,
        details: dict[str, Any] | None,
    ) -> None:
        """Log the admin action to the audit log.

        This is a convenience method that calls the worker's _log_admin_action.
        """
        if self._log_action_callback:
            await self._log_action_callback(admin_id, action, target_type, target_id, details)


def create_admin_event(
    admin: dict[str, Any],
    action: str,
    target_type: str,
    deployment: dict[str, str],
) -> AdminActionEvent:
    """Create an AdminActionEvent with common fields populated.

    Args:
        admin: Admin user dict with github_username and id
        action: The action being performed (e.g., "add_feed", "remove_feed")
        target_type: The type of target (e.g., "feed", "search_index")
        deployment: Deployment context with worker_version and deployment_environment

    Returns:
        AdminActionEvent with common fields populated
    """
    return AdminActionEvent(
        admin_username=admin.get("github_username", ""),
        admin_id=admin.get("id", 0),
        action=action,
        target_type=target_type,
        worker_version=deployment.get("worker_version", ""),
        deployment_environment=deployment.get("deployment_environment", ""),
    )


@asynccontextmanager
async def admin_action_context(
    admin: dict[str, Any],
    action: str,
    target_type: str,
    deployment: dict[str, str],
    log_action_callback: Callable[..., Coroutine[Any, Any, None]] | None = None,
) -> AsyncGenerator[AdminActionContext, None]:
    """Context manager for admin action operations.

    Handles the common pattern of:
    1. Creating an admin event
    2. Timing the operation
    3. Handling success/error outcomes
    4. Emitting the event

    Args:
        admin: Admin user dict with github_username and id
        action: The action being performed
        target_type: The type of target
        deployment: Deployment context
        log_action_callback: Optional callback to log admin actions

    Yields:
        AdminActionContext for the operation

    Example:
        async with admin_action_context(admin, "add_feed", "feed", deployment) as ctx:
            ctx.set_target_id(feed_id)
            # ... perform operation ...
            await ctx.log_action(admin_id, "add_feed", "feed", feed_id, details)
            ctx.set_success()
            return response
    """
    event = create_admin_event(admin, action, target_type, deployment)
    timer = Timer()
    ctx = AdminActionContext(
        event=event,
        timer=timer,
        _log_action_callback=log_action_callback,
    )

    timer.__enter__()
    try:
        yield ctx
    except Exception as e:
        ctx.set_error_from_exception(e)
        raise
    finally:
        timer.__exit__(None, None, None)
        event.wall_time_ms = timer.elapsed_ms
        # Also set reindex_total_ms if this is a reindex action
        if action == "reindex":
            event.reindex_total_ms = timer.elapsed_ms
        emit_event(event)
