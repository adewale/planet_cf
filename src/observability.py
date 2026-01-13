# src/observability.py
"""
Wide event logging for Workers Observability.

Following the principles from Workers Observability and the "Logging Sucks"
philosophy of wide events: one comprehensive event per operation with high
cardinality and high dimensionality.

Usage:
    event = FeedFetchEvent(feed_id=1, feed_url="https://example.com/feed")
    # ... populate event fields during operation ...
    emit_event(event)
"""

import json
import random
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


def generate_request_id() -> str:
    """Generate a unique request ID for tracing."""
    return secrets.token_hex(8)


@dataclass
class FeedFetchEvent:
    """
    Canonical log line for feed fetch operations.

    Emitted once per feed fetch attempt by the queue handler.
    Contains all context needed for debugging feed issues.
    """

    # Identifiers (high cardinality)
    event_type: str = field(default="feed_fetch", init=False)
    feed_id: int = 0
    feed_url: str = ""
    request_id: str = ""
    queue_message_id: str = ""

    # Timing
    timestamp: str = ""
    wall_time_ms: float = 0
    http_latency_ms: float = 0

    # Feed metadata
    feed_title: str | None = None
    feed_domain: str = ""
    feed_consecutive_failures: int = 0

    # HTTP details
    http_status: int | None = None
    http_cached: bool = False
    http_redirected: bool = False
    response_size_bytes: int = 0
    etag_present: bool = False
    last_modified_present: bool = False

    # Parsing results
    entries_found: int = 0
    entries_added: int = 0
    parse_errors: int = 0

    # Outcome
    outcome: str = "success"  # "success" | "error"
    error_type: str | None = None
    error_message: str | None = None
    error_retriable: bool | None = None

    # Context
    worker_version: str = "1.0.0"
    queue_attempt: int = 1

    def __post_init__(self) -> None:
        """Set derived fields after initialization."""
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
        if not self.request_id:
            self.request_id = generate_request_id()
        if self.feed_url and not self.feed_domain:
            try:
                self.feed_domain = urlparse(self.feed_url).netloc
            except Exception:
                self.feed_domain = ""


@dataclass
class GenerationEvent:
    """
    Canonical log line for HTML/feed generation.

    Emitted once per content generation operation.
    """

    event_type: str = field(default="html_generation", init=False)
    request_id: str = ""
    timestamp: str = ""

    # Timing breakdown
    wall_time_ms: float = 0
    d1_query_time_ms: float = 0
    template_render_time_ms: float = 0

    # Content stats
    feeds_active: int = 0
    feeds_healthy: int = 0
    entries_total: int = 0
    html_size_bytes: int = 0

    # Outcome
    outcome: str = "success"
    error_type: str | None = None
    error_message: str | None = None

    # Trigger
    trigger: str = "http"  # "http" | "cron" | "admin_manual"
    triggered_by: str | None = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
        if not self.request_id:
            self.request_id = generate_request_id()


@dataclass
class PageServeEvent:
    """
    Canonical log line for page serving.

    Emitted for each HTTP request.
    """

    event_type: str = field(default="page_serve", init=False)
    request_id: str = ""
    timestamp: str = ""

    # Request details
    method: str = ""
    path: str = ""
    user_agent: str = ""
    referer: str = ""
    country: str | None = None
    colo: str | None = None

    # Response
    status_code: int = 200
    response_size_bytes: int = 0
    cache_status: str = "miss"  # "hit" | "miss" | "bypass"

    # Timing
    wall_time_ms: float = 0

    # Content type served
    content_type: str = ""  # "html" | "atom" | "rss" | "opml" | "search" | "static" | "admin"

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
        if not self.request_id:
            self.request_id = generate_request_id()


def should_sample(
    event: dict[str, Any],
    debug_feed_ids: list[str] | None = None,
    sample_rate: float = 0.10,
) -> bool:
    """
    Tail sampling strategy for high-traffic deployments.

    Always keep:
    - Errors (100%)
    - Slow operations (above p95 thresholds)
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
    if event_type == "html_generation" and wall_time_ms > 30000:  # >30s
        return True
    if event_type == "page_serve" and wall_time_ms > 1000:  # >1s
        return True

    # Always keep specific feeds (for debugging)
    if debug_feed_ids and str(event.get("feed_id")) in debug_feed_ids:
        return True

    # Sample successful, fast operations
    return random.random() < sample_rate


def emit_event(
    event: FeedFetchEvent | GenerationEvent | PageServeEvent | dict[str, Any],
    debug_feed_ids: list[str] | None = None,
    sample_rate: float = 0.10,
    force: bool = False,
) -> bool:
    """
    Emit an event with optional tail sampling.

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


class Timer:
    """Context manager for timing operations."""

    def __init__(self) -> None:
        self.start_time: float = 0
        self.end_time: float = 0
        self.elapsed_ms: float = 0

    def __enter__(self) -> "Timer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.end_time = time.perf_counter()
        self.elapsed_ms = (self.end_time - self.start_time) * 1000

    def elapsed(self) -> float:
        """Return elapsed time in milliseconds."""
        if self.end_time:
            return self.elapsed_ms
        return (time.perf_counter() - self.start_time) * 1000
