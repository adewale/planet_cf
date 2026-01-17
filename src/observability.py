# src/observability.py
"""Wide event logging for Workers Observability.

Following the principles from Workers Observability and the "Logging Sucks"
philosophy of wide events: one comprehensive event per unit of work.

KEY PRINCIPLE: One event per unit of work, not one event per function call.
- HTTP request → RequestEvent (absorbs search, generation, OAuth fields)
- Queue message → FeedFetchEvent (absorbs indexing aggregates)
- Cron invocation → SchedulerEvent (absorbs retention cleanup)
- Admin action → AdminActionEvent (absorbs OPML import, DLQ ops, reindex)

Usage:
    event = RequestEvent(method="GET", path="/search")
    # ... populate route-specific fields during operation ...
    emit_event(event)
"""

import json
import random
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


def generate_request_id() -> str:
    """Generate a unique request ID for tracing."""
    return secrets.token_hex(8)


# =============================================================================
# RequestEvent: One event per HTTP request
# Absorbs: PageServeEvent, SearchEvent, GenerationEvent
# =============================================================================


@dataclass
class RequestEvent:
    """Canonical log line for HTTP requests.

    Emitted once per fetch() invocation. Contains base request/response fields
    plus route-specific fields (search_*, generation_*, oauth_*) that are null
    for non-applicable routes.
    """

    # Identity
    event_type: str = field(default="request", init=False)
    request_id: str = ""
    timestamp: str = ""

    # Request context
    method: str = ""
    path: str = ""
    route: str = ""  # Pattern: "/", "/search", "/admin/feeds/:id"
    user_agent: str = ""
    referer: str = ""

    # Response
    status_code: int = 200
    response_size_bytes: int = 0
    wall_time_ms: float = 0
    cache_status: str = ""  # "hit" | "miss" | "bypass"
    content_type: str = ""  # "html" | "atom" | "rss" | "search" | "admin" | "static"

    # === Search fields (null for non-search routes) ===
    search_query: str | None = None
    search_query_length: int | None = None
    search_embedding_ms: float | None = None
    search_vectorize_ms: float | None = None
    search_d1_ms: float | None = None
    search_results_total: int | None = None
    search_semantic_matches: int | None = None
    search_keyword_matches: int | None = None
    search_exact_title_matches: int | None = None
    search_title_in_query_matches: int | None = None
    search_query_in_title_matches: int | None = None

    # === Generation fields (null for non-generation routes) ===
    generation_d1_ms: float | None = None
    generation_render_ms: float | None = None
    generation_entries_total: int | None = None
    generation_feeds_healthy: int | None = None
    generation_trigger: str | None = None  # "http"

    # === OAuth fields (null for non-OAuth routes) ===
    oauth_stage: str | None = None  # "redirect" | "callback"
    oauth_provider: str | None = None
    oauth_success: bool | None = None
    oauth_username: str | None = None

    # Outcome
    outcome: str = "success"
    error_type: str | None = None
    error_message: str | None = None

    # Context / Deployment
    worker_version: str = ""  # Set from DEPLOYMENT_VERSION env var
    deployment_environment: str = ""  # Set from DEPLOYMENT_ENVIRONMENT env var

    def __post_init__(self) -> None:
        """Initialize timestamp and request_id if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not self.request_id:
            self.request_id = generate_request_id()


# =============================================================================
# FeedFetchEvent: One event per queue message
# Absorbs: IndexingEvent (as aggregated fields)
# =============================================================================


@dataclass
class FeedFetchEvent:
    """Canonical log line for feed fetch operations.

    Emitted once per queue message. Contains all feed fetch context plus
    aggregated indexing stats (sum of all entry indexing within this fetch).
    """

    # Identity
    event_type: str = field(default="feed_fetch", init=False)
    request_id: str = ""
    queue_message_id: str = ""
    timestamp: str = ""

    # Feed context
    feed_id: int = 0
    feed_url: str = ""
    feed_domain: str = ""
    feed_title: str | None = None
    feed_consecutive_failures: int = 0

    # HTTP fetch
    http_latency_ms: float = 0
    http_status: int | None = None
    http_cached: bool = False
    http_redirected: bool = False
    response_size_bytes: int = 0
    etag_present: bool = False
    last_modified_present: bool = False

    # Parsing
    entries_found: int = 0
    entries_added: int = 0
    parse_errors: int = 0

    # === Indexing aggregate (was separate IndexingEvent) ===
    indexing_attempted: int = 0
    indexing_succeeded: int = 0
    indexing_failed: int = 0
    indexing_total_ms: float = 0
    indexing_embedding_ms: float = 0
    indexing_upsert_ms: float = 0
    indexing_text_truncated: int = 0  # Count of truncated entries

    # Overall timing
    wall_time_ms: float = 0

    # Outcome
    outcome: str = "success"
    error_type: str | None = None
    error_message: str | None = None
    error_retriable: bool | None = None

    # Context / Deployment
    worker_version: str = ""  # Set from DEPLOYMENT_VERSION env var
    deployment_environment: str = ""  # Set from DEPLOYMENT_ENVIRONMENT env var
    queue_attempt: int = 1

    # Cross-boundary correlation
    # Links scheduler -> queue -> feed fetch for tracing feed lifecycle
    correlation_id: str = ""  # Propagated from scheduler through queue

    def __post_init__(self) -> None:
        """Initialize timestamp, request_id, and feed_domain if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not self.request_id:
            self.request_id = generate_request_id()
        if self.feed_url and not self.feed_domain:
            try:
                self.feed_domain = urlparse(self.feed_url).netloc
            except Exception:
                self.feed_domain = ""


# =============================================================================
# SchedulerEvent: One event per cron invocation
# Absorbs: Retention cleanup
# =============================================================================


@dataclass
class SchedulerEvent:
    """Canonical log line for cron execution.

    Emitted once per scheduled() call. Includes both feed scheduling
    and retention cleanup phases.
    """

    # Identity
    event_type: str = field(default="scheduler", init=False)
    request_id: str = ""
    timestamp: str = ""

    # === Scheduler phase ===
    scheduler_d1_ms: float = 0
    scheduler_queue_ms: float = 0
    feeds_queried: int = 0
    feeds_active: int = 0
    feeds_enqueued: int = 0

    # === Retention phase (absorbed) ===
    retention_d1_ms: float = 0
    retention_vectorize_ms: float = 0
    retention_entries_scanned: int = 0
    retention_entries_deleted: int = 0
    retention_vectors_deleted: int = 0
    retention_errors: int = 0
    retention_days: int = 0
    retention_max_per_feed: int = 0

    # Overall
    wall_time_ms: float = 0

    # Outcome
    outcome: str = "success"
    error_type: str | None = None
    error_message: str | None = None

    # Context / Deployment
    worker_version: str = ""  # Set from DEPLOYMENT_VERSION env var
    deployment_environment: str = ""  # Set from DEPLOYMENT_ENVIRONMENT env var

    # Cross-boundary correlation
    # This correlation_id is passed to all feed queue messages for tracing
    correlation_id: str = ""  # Generated per scheduler run, propagated to feeds

    def __post_init__(self) -> None:
        """Initialize timestamp, request_id, and correlation_id if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not self.request_id:
            self.request_id = generate_request_id()
        if not self.correlation_id:
            self.correlation_id = generate_request_id()  # Auto-generate for scheduler


# =============================================================================
# AdminActionEvent: One event per admin operation
# Absorbs: OPML import, DLQ ops, reindex
# =============================================================================


@dataclass
class AdminActionEvent:
    """Canonical log line for admin operations.

    Emitted once per admin action. Includes action-specific fields
    for OPML import, reindex, and DLQ operations.
    """

    # Identity
    event_type: str = field(default="admin_action", init=False)
    request_id: str = ""
    timestamp: str = ""

    # Admin context
    admin_username: str = ""
    admin_id: int = 0
    action: str = ""  # "add_feed" | "remove_feed" | "toggle_feed" |
    #                   "import_opml" | "retry_dlq" | "reindex"

    # Target
    target_type: str | None = None  # "feed" | "feeds" | "entry" | "search_index"
    target_id: int | None = None

    # === OPML import fields ===
    import_file_size: int | None = None
    import_feeds_parsed: int | None = None
    import_feeds_added: int | None = None
    import_feeds_skipped: int | None = None
    import_errors: int | None = None

    # === Reindex fields ===
    reindex_entries_total: int | None = None
    reindex_entries_indexed: int | None = None
    reindex_entries_failed: int | None = None
    reindex_total_ms: float | None = None

    # === DLQ fields ===
    dlq_feed_id: int | None = None
    dlq_original_error: str | None = None
    dlq_action: str | None = None  # "retry" | "discard"

    # Timing
    wall_time_ms: float = 0

    # Outcome
    outcome: str = "success"
    error_type: str | None = None
    error_message: str | None = None

    # Context / Deployment
    worker_version: str = ""  # Set from DEPLOYMENT_VERSION env var
    deployment_environment: str = ""  # Set from DEPLOYMENT_ENVIRONMENT env var

    def __post_init__(self) -> None:
        """Initialize timestamp and request_id if not provided."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not self.request_id:
            self.request_id = generate_request_id()


# =============================================================================
# Tail Sampling
# =============================================================================


def should_sample(
    event: dict[str, Any],
    debug_feed_ids: list[str] | None = None,
    sample_rate: float = 0.10,
) -> bool:
    """Tail sampling strategy for high-traffic deployments.

    Always keep:
    - Errors (100%)
    - Slow operations (above p95 thresholds)
    - Zero-result searches
    - Specific feeds being debugged

    Sample:
    - Successful, fast operations (default 10%)

    Args:
        event: The event dict to evaluate
        debug_feed_ids: List of feed IDs to always keep
        sample_rate: Sampling rate for successful fast operations (default 10%)

    Returns:
        True if this event should be emitted, False to drop

    """
    # Always keep errors
    if event.get("outcome") == "error":
        return True

    # Always keep slow operations (thresholds based on p95 expectations)
    wall_time_ms = event.get("wall_time_ms", 0)
    event_type = event.get("event_type", "")

    if event_type == "feed_fetch" and wall_time_ms > 10000:  # >10s
        return True
    if event_type == "request" and wall_time_ms > 1000:  # >1s for HTTP
        return True
    if event_type == "scheduler" and wall_time_ms > 60000:  # >60s for cron
        return True
    if event_type == "admin_action" and wall_time_ms > 30000:  # >30s for admin
        return True

    # Always keep zero-result searches (important for understanding user needs)
    if event_type == "request" and event.get("search_results_total") == 0:
        return True

    # Always keep specific feeds (for debugging)
    if debug_feed_ids and str(event.get("feed_id")) in debug_feed_ids:
        return True

    # Sample successful, fast operations
    return random.random() < sample_rate


def emit_event(
    event: (RequestEvent | FeedFetchEvent | SchedulerEvent | AdminActionEvent | dict[str, Any]),
    debug_feed_ids: list[str] | None = None,
    sample_rate: float = 0.10,
    force: bool = False,
) -> bool:
    """Emit an event with optional tail sampling.

    Args:
        event: The event to emit (dataclass or dict)
        debug_feed_ids: List of feed IDs to always keep
        sample_rate: Sampling rate for successful fast operations
        force: If True, skip sampling and always emit

    Returns:
        True if event was emitted, False if dropped by sampling

    """
    event_dict = event if isinstance(event, dict) else asdict(event)

    if force or should_sample(event_dict, debug_feed_ids, sample_rate):
        print(json.dumps(event_dict))
        return True
    return False


# =============================================================================
# Timer Utility
# =============================================================================


class Timer:
    """Context manager for timing operations."""

    def __init__(self) -> None:
        """Initialize timer with zero values."""
        self.start_time: float = 0
        self.end_time: float = 0
        self.elapsed_ms: float = 0

    def __enter__(self) -> "Timer":
        """Start timing when entering context."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Stop timing when exiting context."""
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000

    def elapsed(self) -> float:
        """Return elapsed time in milliseconds."""
        if self.end_time:
            return self.elapsed_ms
        return (time.perf_counter() - self.start_time) * 1000
