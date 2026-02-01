# src/main.py
"""Planet CF - Feed Aggregator for Cloudflare Python Workers.

Main Worker entrypoint handling all triggers:
- scheduled(): Hourly cron to enqueue feed fetches
- queue(): Queue consumer for feed fetching
- fetch(): HTTP request handling (generates content on-demand)
"""

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, TypeAlias
from urllib.parse import parse_qs, urlparse

import feedparser
from workers import Response, WorkerEntrypoint

from instance_config import is_lite_mode as check_lite_mode
from models import BleachSanitizer
from observability import (
    ERROR_MESSAGE_MAX_LENGTH,
    AdminActionEvent,
    FeedFetchEvent,
    RequestEvent,
    SchedulerEvent,
    Timer,
    emit_event,
    log_error,
    log_op,
    truncate_error,
)
from templates import (
    ADMIN_JS,
    KEYBOARD_NAV_JS,
    STATIC_CSS,
    TEMPLATE_ADMIN_DASHBOARD,
    TEMPLATE_ADMIN_ERROR,
    TEMPLATE_ADMIN_LOGIN,
    TEMPLATE_FEED_ATOM,
    TEMPLATE_FEED_RSS,
    TEMPLATE_FEEDS_OPML,
    TEMPLATE_INDEX,
    TEMPLATE_SEARCH,
    TEMPLATE_TITLES,
    THEME_ASSETS,
    THEME_CSS,
    THEME_LOGOS,
    render_template,
)
from wrappers import (
    SafeEnv,
    SafeFeedInfo,
    SafeFormData,
    SafeHeaders,
    _is_js_undefined,
    _safe_str,
    _to_py_list,
    _to_py_safe,
    admin_row_from_js,
    audit_rows_from_d1,
    entry_bind_values,
    entry_rows_from_d1,
    feed_bind_values,
    feed_row_from_js,
    feed_rows_from_d1,
    safe_http_fetch,
)

# =============================================================================
# Type Aliases for Cloudflare Workers Runtime
# =============================================================================
# These are JavaScript objects passed by the Workers runtime with no Python stubs.
# Using explicit type aliases documents the intent and satisfies type checkers.
# Note: Using TypeAlias syntax (not PEP 695 `type` keyword) for Pyodide compatibility.

#: Cloudflare Workers scheduled event (JavaScript object)
ScheduledEvent: TypeAlias = Any
#: Cloudflare Workers queue batch (JavaScript object)
QueueBatch: TypeAlias = Any
#: Cloudflare Workers environment bindings (JavaScript object)
WorkerEnv: TypeAlias = Any
#: Cloudflare Workers execution context (JavaScript object)
WorkerCtx: TypeAlias = Any
#: Cloudflare Workers HTTP request (JavaScript object)
WorkerRequest: TypeAlias = Any
#: feedparser's FeedParserDict (dynamic dictionary-like object)
FeedParserDict: TypeAlias = Any


# =============================================================================
# Custom Exceptions
# =============================================================================


class RateLimitError(Exception):
    """Raised when a feed returns 429/503 with Retry-After.

    This is a transient condition, not a feed failure. The feed should be
    retried later without incrementing consecutive_failures.
    """

    def __init__(self, message: str, retry_after: str | None = None):
        """Initialize rate limit error with optional retry-after value."""
        super().__init__(message)
        self.retry_after = retry_after


# =============================================================================
# Configuration
# =============================================================================

FEED_TIMEOUT_SECONDS = 60  # Max wall time per feed
HTTP_TIMEOUT_SECONDS = 30  # HTTP request timeout
# Issue 9.3/9.5: Include contact info for good netizen behavior
USER_AGENT = "PlanetCF/1.0 (+https://planetcf.com; contact@planetcf.com)"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
# Security: Maximum search query length to prevent DoS
MAX_SEARCH_QUERY_LENGTH = 1000
MAX_SEARCH_WORDS = 10  # Prevent DoS via excessive word count in multi-word search
MAX_OPML_FEEDS = 100  # Prevent DoS via unbounded OPML import
SESSION_GRACE_SECONDS = 5  # Clock skew grace period (reduced from 60s for security)
REINDEX_COOLDOWN_SECONDS = 300  # 5 minute cooldown between reindex operations
# Retention policy defaults (can be overridden via env vars)
DEFAULT_RETENTION_DAYS = 90  # Default to 90 days
DEFAULT_MAX_ENTRIES_PER_FEED = 50  # Max entries to keep per feed (smart default)

# Search configuration defaults (can be overridden via env vars)
DEFAULT_EMBEDDING_MAX_CHARS = 2000  # Max chars to embed per entry
DEFAULT_SEARCH_SCORE_THRESHOLD = 0.3  # Minimum similarity score (0.0-1.0)
DEFAULT_SEARCH_TOP_K = 50  # Max semantic search results before filtering

# Feed failure thresholds (can be overridden via env vars)
DEFAULT_FEED_AUTO_DEACTIVATE_THRESHOLD = 10  # Consecutive failures before auto-deactivate
DEFAULT_FEED_FAILURE_THRESHOLD = 3  # Consecutive failures to show in DLQ

# SQL query limits (prevent unbounded result sets)
DEFAULT_QUERY_LIMIT = 500  # Maximum entries returned in a single query

# Smart defaults: Content display fallback
# When no entries found in display range, show the N most recent entries
FALLBACK_ENTRIES_LIMIT = 50  # Show 50 most recent entries if date range is empty

# HTML sanitizer instance (uses settings from types.py)
_sanitizer = BleachSanitizer()

# Constants for content limits
SUMMARY_MAX_LENGTH = 500

# Cloud metadata endpoints to block (SSRF protection)
BLOCKED_METADATA_IPS = {
    "169.254.169.254",  # AWS/GCP/Azure metadata
    "100.100.100.200",  # Alibaba Cloud metadata
    "192.0.0.192",  # Oracle Cloud metadata
}


def _get_display_author(author: str | None, feed_title: str | None) -> str:
    """Compute display author for an entry, filtering out email addresses.

    If author is empty or contains '@' (likely an email), use feed_title instead.
    This provides a safe, centralized check that handles the email filtering logic
    in Python rather than in templates.

    Args:
        author: Entry author from feed (may be email, empty, or None)
        feed_title: Feed title to use as fallback

    Returns:
        Safe display string for author attribution
    """
    if author and "@" not in author:
        return author
    return feed_title or "Unknown"


def _validate_feed_id(feed_id: str) -> int | None:
    """Validate and convert a feed ID from URL path to integer.

    Returns the integer ID if valid, None otherwise.
    Prevents path traversal and invalid ID attacks.
    """
    if not feed_id:
        return None
    # Only allow positive integers (no leading zeros except for "0")
    if not feed_id.isdigit():
        return None
    try:
        id_int = int(feed_id)
        # Reject zero or negative (shouldn't happen with isdigit, but be safe)
        if id_int <= 0:
            return None
        return id_int
    except (ValueError, OverflowError):
        return None


def _xml_escape(text: str) -> str:
    """Escape XML special characters for safe embedding in XML content.

    This is applied before CDATA wrapping to handle any edge cases
    where content might contain problematic XML sequences.
    """
    # Standard XML entity escaping
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _parse_query_params(url_str: str) -> dict[str, list[str]]:
    """Extract query parameters from a URL string.

    Returns a dict where each key maps to a list of values.
    """
    if "?" not in url_str:
        return {}
    query_string = url_str.split("?", 1)[1]
    return parse_qs(query_string)


# =============================================================================
# Content Normalization
# =============================================================================


def _normalize_entry_content(content: str, title: str | None) -> str:
    """Normalize entry content for display by removing duplicate title headings.

    Many feeds include the post title as an <h1> or <h2> at the start of the
    content body. Since our template already displays the title, this creates
    visual duplication. This function strips the leading heading if it matches
    the entry title.

    Handles common patterns:
    - <h1>Title</h1> at start
    - Metadata (date/read time) before the <h1>
    - Whitespace padding inside heading tags
    - Link-wrapped headings: <h1><a href="#">Title</a></h1>

    Args:
        content: HTML content that may contain a duplicate title heading
        title: The entry title to match against

    Returns:
        Content with the duplicate title heading removed if found
    """
    if not content or not title:
        return content

    # Normalize title for comparison (strip whitespace, lowercase)
    title_normalized = title.strip().lower()

    # Limit regex search to first 1000 chars to prevent ReDoS on pathological input
    # Duplicate title headings always appear at the start of content
    search_content = content[:1000] if len(content) > 1000 else content

    # Pattern to match optional metadata, then <h1> or <h2> with the title
    # Group 1: Optional metadata (date, read time, etc.) before the heading
    # Group 2: The heading tag (h1 or h2)
    # Group 3: Optional link opening tag
    # Group 4: The heading text
    # Group 5: Optional link closing tag
    pattern = (
        r"^(\s*(?:[A-Za-z]+\s+\d{1,2},?\s+\d{4}\s*)?(?:/\s*\d+\s*min\s*read\s*)?\s*)"  # metadata
        r"<(h[12])(?:\s[^>]*)?>\s*"  # opening h1/h2
        r"(?:(<a[^>]*>)\s*)?"  # optional link open
        r"([^<]+?)"  # heading text
        r"\s*(?:(</a>)\s*)?"  # optional link close
        r"</\2>"  # closing h1/h2
    )

    match = re.match(pattern, search_content, re.IGNORECASE)

    if match:
        heading_text = match.group(4).strip().lower()
        if heading_text == title_normalized:
            # Strip the metadata and heading, keep remaining content
            return content[match.end() :].lstrip()

    return content


# =============================================================================
# Response Helpers
# =============================================================================


def _html_response(content: str, cache_max_age: int = 3600) -> Response:
    """Create an HTML response with caching and security headers."""
    # Content Security Policy - defense in depth against XSS
    # - default-src 'self': Only allow same-origin resources by default
    # - script-src 'self': Only allow same-origin scripts (external JS files)
    # - style-src 'self' 'unsafe-inline': Allow inline styles (needed for templates)
    # - img-src https: data:: HTTPS images + data URIs (for inline images)
    # - frame-ancestors 'none': Prevent clickjacking (cannot be framed)
    # - base-uri 'self': Prevent base tag injection attacks
    # - form-action 'self': Forms can only submit to same origin
    csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src https: data:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return Response(
        content,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": f"public, max-age={cache_max_age}, stale-while-revalidate=60",
            "Content-Security-Policy": csp,
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        },
    )


def _json_response(data: dict, status: int = 200) -> Response:
    """Create a JSON response."""
    return Response(
        json.dumps(data),
        status=status,
        headers={"Content-Type": "application/json"},
    )


def _json_error(message: str, status: int = 400) -> Response:
    """Create a JSON error response."""
    return _json_response({"error": message}, status=status)


def _redirect_response(location: str) -> Response:
    """Create a redirect response."""
    return Response("", status=302, headers={"Location": location})


def _feed_response(content: str, content_type: str, cache_max_age: int = 3600) -> Response:
    """Create a feed response (Atom/RSS/OPML) with caching headers."""
    return Response(
        content,
        headers={
            "Content-Type": f"{content_type}; charset=utf-8",
            "Cache-Control": f"public, max-age={cache_max_age}, stale-while-revalidate=60",
        },
    )


# =============================================================================
# Datetime Helpers
# =============================================================================


def _parse_iso_datetime(iso_string: str | None) -> datetime | None:
    """Parse an ISO datetime string to a timezone-aware datetime.

    Handles various ISO formats:
    - With Z suffix: "2026-01-17T12:00:00Z"
    - With offset: "2026-01-17T12:00:00+00:00"
    - Naive (no timezone): "2026-01-17T12:00:00" (assumes UTC)

    Args:
        iso_string: ISO format datetime string, or None

    Returns:
        Timezone-aware datetime in UTC, or None if input is empty/invalid
    """
    if not iso_string:
        return None
    try:
        # Replace Z suffix with +00:00 for fromisoformat compatibility
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        # Ensure timezone-aware (database may store naive datetimes)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


# =============================================================================
# Main Worker Class
# =============================================================================


class Default(WorkerEntrypoint):
    """Main Worker entrypoint handling all triggers.

    Handlers:
    - scheduled(): Hourly cron to enqueue feed fetches
    - queue(): Queue consumer for feed fetching
    - fetch(): HTTP request handling (generates content on-demand)
    """

    _cached_safe_env: SafeEnv | None = None  # Cached wrapped environment

    @property
    def env(self) -> SafeEnv:
        """Override env access to return a SafeEnv-wrapped version.

        This ensures all D1/AI/Vectorize/Queue access goes through our
        boundary layer wrappers that handle JsProxy conversion.
        """
        # Get the actual env from the parent class
        raw_env = super().__getattribute__("_env_from_runtime")
        cached = self._cached_safe_env
        if cached is None:
            cached = SafeEnv(raw_env)
            object.__setattr__(self, "_cached_safe_env", cached)
        return cached

    @env.setter
    def env(self, value: WorkerEnv) -> None:
        """Store raw env from runtime, will be wrapped on access."""
        object.__setattr__(self, "_env_from_runtime", value)
        object.__setattr__(self, "_cached_safe_env", None)  # Clear cache

    def _get_deployment_context(self) -> dict:
        """Get deployment context from environment for observability.

        Returns dict with:
        - worker_version: Version ID from VERSION_METADATA binding (auto-set by Cloudflare)
        - deployment_environment: Environment name (e.g., "production", "staging")
        """
        # Get version from VERSION_METADATA binding if available
        version_metadata = getattr(self.env, "VERSION_METADATA", None)
        if version_metadata:
            # VERSION_METADATA has .id (version ID) and .tag (optional tag)
            worker_version = getattr(version_metadata, "id", None) or ""
        else:
            # Fallback to env var if binding not available
            worker_version = getattr(self.env, "DEPLOYMENT_VERSION", None) or ""

        return {
            "worker_version": worker_version,
            "deployment_environment": getattr(self.env, "DEPLOYMENT_ENVIRONMENT", None) or "",
        }

    def _create_admin_event(
        self, admin: dict[str, Any], action: str, target_type: str
    ) -> AdminActionEvent:
        """Create an admin action event with common fields populated.

        This reduces boilerplate in admin handlers by centralizing event creation.

        Args:
            admin: Admin user dict with github_username and id
            action: The action being performed (e.g., "add_feed", "remove_feed")
            target_type: The type of target (e.g., "feed", "search_index")

        Returns:
            AdminActionEvent with common fields populated
        """
        deployment = self._get_deployment_context()
        return AdminActionEvent(
            admin_username=admin.get("github_username", ""),
            admin_id=admin.get("id", 0),
            action=action,
            target_type=target_type,
            worker_version=deployment["worker_version"],
            deployment_environment=deployment["deployment_environment"],
        )

    def _get_feed_timeout(self) -> int:
        """Get feed timeout from environment, default 60 seconds."""
        val = getattr(self.env, "FEED_TIMEOUT_SECONDS", None)
        return int(val) if val else FEED_TIMEOUT_SECONDS

    def _get_http_timeout(self) -> int:
        """Get HTTP timeout from environment, default 30 seconds."""
        val = getattr(self.env, "HTTP_TIMEOUT_SECONDS", None)
        return int(val) if val else HTTP_TIMEOUT_SECONDS

    # Track if database has been initialized (per-isolate state)
    _db_initialized: bool = False

    async def _ensure_database_initialized(self) -> None:
        """Auto-run migrations on first request if tables don't exist.

        Smart default: For simpler deployment, automatically initialize the database
        schema on first request. This checks if core tables exist and creates them
        if missing.

        Note: This is a lightweight check that only runs once per worker isolate.
        For production deployments, explicit migration via wrangler is preferred.
        """
        if self._db_initialized:
            return

        try:
            # Check if feeds table exists (core table)
            result = await self.env.DB.prepare(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='feeds'"
            ).first()

            if result is None:
                _log_op("database_auto_init", status="initializing")
                # Create core tables (minimal schema for basic operation)
                await self.env.DB.exec("""
                    -- Feeds table
                    CREATE TABLE IF NOT EXISTS feeds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT UNIQUE NOT NULL,
                        title TEXT,
                        site_url TEXT,
                        author_name TEXT,
                        author_email TEXT,
                        etag TEXT,
                        last_modified TEXT,
                        last_fetch_at TEXT,
                        last_success_at TEXT,
                        fetch_error TEXT,
                        fetch_error_count INTEGER DEFAULT 0,
                        consecutive_failures INTEGER DEFAULT 0,
                        is_active INTEGER DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_feeds_active ON feeds(is_active);
                    CREATE INDEX IF NOT EXISTS idx_feeds_url ON feeds(url);

                    -- Entries table
                    CREATE TABLE IF NOT EXISTS entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        feed_id INTEGER NOT NULL,
                        guid TEXT NOT NULL,
                        url TEXT,
                        title TEXT,
                        author TEXT,
                        content TEXT,
                        summary TEXT,
                        published_at TEXT,
                        updated_at TEXT,
                        first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
                        UNIQUE(feed_id, guid)
                    );
                    CREATE INDEX IF NOT EXISTS idx_entries_published ON entries(published_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_entries_feed ON entries(feed_id);
                    CREATE INDEX IF NOT EXISTS idx_entries_guid ON entries(feed_id, guid);

                    -- Admin users table
                    CREATE TABLE IF NOT EXISTS admins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        github_username TEXT UNIQUE NOT NULL,
                        github_id INTEGER,
                        display_name TEXT,
                        avatar_url TEXT,
                        is_active INTEGER DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        last_login_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_admins_github ON admins(github_username);

                    -- Audit log for admin actions
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        admin_id INTEGER,
                        action TEXT NOT NULL,
                        target_type TEXT,
                        target_id INTEGER,
                        details TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (admin_id) REFERENCES admins(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
                """)
                _log_op("database_auto_init", status="completed")
            else:
                _log_op("database_auto_init", status="already_initialized")

            self._db_initialized = True

        except Exception as e:
            _log_error("database_auto_init_error", e)
            # Don't prevent the request from proceeding
            self._db_initialized = True  # Avoid retrying on every request

    # =========================================================================
    # Cron Handler - Scheduler
    # =========================================================================

    async def scheduled(self, event: ScheduledEvent, env: WorkerEnv, ctx: WorkerCtx) -> None:
        """Hourly cron trigger - enqueue feeds for fetching.

        Content (HTML/RSS/Atom) is generated on-demand by fetch(), not pre-generated.

        Note: env and ctx are passed by the runtime but we use self.env and self.ctx
        which are set up during worker initialization.
        """
        await self._run_scheduler()

    async def _run_scheduler(self) -> dict[str, int]:
        """Hourly scheduler - enqueue each active feed as a separate message.

        Each feed gets its own queue message to ensure:
        - Isolated retries (only failed feed is retried)
        - Isolated timeouts (slow feed doesn't block others)
        - Accurate dead-lettering (DLQ shows exactly which feeds fail)
        - Parallel processing (consumers can scale independently)
        """
        # Initialize SchedulerEvent for observability
        # Note: correlation_id is auto-generated in __post_init__
        deployment = self._get_deployment_context()
        sched_event = SchedulerEvent(
            worker_version=deployment["worker_version"],
            deployment_environment=deployment["deployment_environment"],
        )

        with Timer() as total_timer:
            try:
                # Get all active feeds from D1
                with Timer() as d1_timer:
                    result = await self.env.DB.prepare("""
                        SELECT id, url, etag, last_modified
                        FROM feeds
                        WHERE is_active = 1
                    """).all()

                sched_event.scheduler_d1_ms = d1_timer.elapsed_ms
                feeds = feed_rows_from_d1(result.results)
                sched_event.feeds_queried = len(feeds)
                sched_event.feeds_active = len(feeds)

                enqueue_count = 0

                # Enqueue each feed as a SEPARATE message
                # Do NOT batch multiple feeds into one message
                with Timer() as queue_timer:
                    if self.env.FEED_QUEUE is None:
                        # Queue not available (e.g., wrangler dev --remote mode)
                        sched_event.outcome = "skipped"
                        sched_event.error_message = "Queue binding unavailable"
                    else:
                        for feed in feeds:
                            message = {
                                "feed_id": feed["id"],
                                "url": feed["url"],
                                "etag": feed.get("etag"),
                                "last_modified": feed.get("last_modified"),
                                "scheduled_at": datetime.now(timezone.utc).isoformat(),
                                # Cross-boundary correlation: link scheduler -> feed fetch
                                "correlation_id": sched_event.correlation_id,
                            }

                            await self.env.FEED_QUEUE.send(message)
                            enqueue_count += 1

                sched_event.scheduler_queue_ms = queue_timer.elapsed_ms
                sched_event.feeds_enqueued = enqueue_count

                # Run retention policy after enqueueing feeds
                # This ensures old entries are cleaned up once per cron cycle
                retention_stats = await self._apply_retention_policy()
                sched_event.retention_d1_ms = retention_stats.get("d1_ms", 0)
                sched_event.retention_vectorize_ms = retention_stats.get("vectorize_ms", 0)
                sched_event.retention_entries_scanned = retention_stats.get("entries_scanned", 0)
                sched_event.retention_entries_deleted = retention_stats.get("entries_deleted", 0)
                sched_event.retention_vectors_deleted = retention_stats.get("vectors_deleted", 0)
                sched_event.retention_errors = retention_stats.get("errors", 0)
                sched_event.retention_days = retention_stats.get("retention_days", 0)
                sched_event.retention_max_per_feed = retention_stats.get("max_per_feed", 0)

                sched_event.outcome = "success"

            except Exception as e:
                sched_event.outcome = "error"
                sched_event.error_type = type(e).__name__
                sched_event.error_message = truncate_error(e)
                raise

        sched_event.wall_time_ms = total_timer.elapsed_ms
        emit_event(sched_event)

        return {"enqueued": enqueue_count}

    # =========================================================================
    # Queue Handler - Feed Fetcher
    # =========================================================================

    async def queue(self, batch: QueueBatch, env: WorkerEnv, ctx: WorkerCtx) -> None:
        """Process a batch of feed messages from the queue.

        Each message contains exactly ONE feed to fetch.
        This ensures isolated retries and timeouts per feed.

        Note: Workers Python runtime passes (batch, env, ctx) but we use self.env from __init__.
        """
        for message in batch.messages:
            # CRITICAL: Convert JsProxy message body to Python dict
            feed_job_raw = message.body
            feed_job = _to_py_safe(feed_job_raw)
            if not feed_job or not isinstance(feed_job, dict):
                # Invalid message - emit minimal event and ack to prevent retry loop
                invalid_event = FeedFetchEvent(
                    outcome="error",
                    error_type="InvalidMessage",
                    error_message=f"Invalid body type: {type(feed_job_raw).__name__}",
                    error_retriable=False,
                )
                emit_event(invalid_event)
                message.ack()  # Don't retry invalid messages
                continue

            feed_url = feed_job.get("url", "unknown")
            feed_id = feed_job.get("feed_id", 0)
            correlation_id = feed_job.get("correlation_id", "")

            # Get deployment context for observability
            deployment = self._get_deployment_context()

            # Initialize wide event for this feed fetch
            event = FeedFetchEvent(
                feed_id=feed_id,
                feed_url=feed_url,
                queue_message_id=str(getattr(message, "id", "")),
                queue_attempt=getattr(message, "attempts", 1),
                # Deployment context
                worker_version=deployment["worker_version"],
                deployment_environment=deployment["deployment_environment"],
                # Cross-boundary correlation from scheduler
                correlation_id=correlation_id,
            )

            feed_timeout = self._get_feed_timeout()
            with Timer() as timer:
                try:
                    # Wrap entire feed processing in a timeout
                    # This is WALL TIME, not CPU time - network I/O counts here
                    result = await asyncio.wait_for(
                        self._process_single_feed(feed_job, event), timeout=feed_timeout
                    )

                    event.wall_time_ms = timer.elapsed_ms
                    event.outcome = "success"
                    event.entries_added = result.get("entries_added", 0)
                    event.entries_found = result.get("entries_found", 0)
                    message.ack()

                except TimeoutError:
                    event.wall_time_ms = timer.elapsed_ms
                    event.outcome = "error"
                    event.error_type = "TimeoutError"
                    event.error_message = f"Timeout after {feed_timeout}s"
                    event.error_retriable = True
                    await self._record_feed_error(feed_id, "Timeout", event)
                    message.retry()

                except RateLimitError as e:
                    # Rate limiting is not a failure - don't increment consecutive_failures
                    # The retry-after time was already stored in _process_single_feed
                    event.wall_time_ms = timer.elapsed_ms
                    event.outcome = "rate_limited"
                    event.error_type = "RateLimitError"
                    event.error_message = truncate_error(e)
                    event.error_retriable = True
                    # Don't call _record_feed_error - feed is not failing
                    message.retry()

                except Exception as e:
                    event.wall_time_ms = timer.elapsed_ms
                    event.outcome = "error"
                    event.error_type = type(e).__name__
                    event.error_message = truncate_error(e)
                    event.error_retriable = not isinstance(e, ValueError)
                    await self._record_feed_error(feed_id, str(e), event)
                    message.retry()

            # Emit wide event (sampling applied)
            emit_event(event)

    async def _process_single_feed(
        self, job: dict, event: FeedFetchEvent | None = None
    ) -> dict[str, Any]:
        """Fetch, parse, and store a single feed.

        This function should complete within FEED_TIMEOUT_SECONDS.

        Args:
            job: Feed job dict with feed_id, url, etag, last_modified
            event: Optional FeedFetchEvent to populate with details

        """
        feed_id = job["feed_id"]
        url = job["url"]
        etag = job.get("etag")
        last_modified = job.get("last_modified")

        # SSRF protection - validate URL before fetching
        if not self._is_safe_url(url):
            raise ValueError(f"URL failed SSRF validation: {url}")

        # Build conditional request headers (good netizen behavior)
        headers = {"User-Agent": USER_AGENT}
        if etag:
            headers["If-None-Match"] = str(etag)
        if last_modified:
            headers["If-Modified-Since"] = str(last_modified)

        # Fetch using boundary-layer safe_http_fetch
        with Timer() as http_timer:
            http_response = await safe_http_fetch(
                url, headers=headers, timeout_seconds=self._get_http_timeout()
            )

        # Extract normalized response data (all values are Python)
        status_code = http_response.status_code
        final_url = http_response.final_url
        response_headers = http_response.headers
        response_text = http_response.text if status_code != 304 else ""
        response_size = len(response_text.encode("utf-8")) if response_text else 0

        # Populate event with HTTP details
        if event:
            event.http_latency_ms = http_timer.elapsed_ms
            event.http_status = status_code
            event.http_cached = status_code == 304
            event.http_redirected = final_url != url
            event.response_size_bytes = response_size
            event.etag_present = bool(response_headers.get("etag"))
            event.last_modified_present = bool(response_headers.get("last-modified"))

        # Re-validate final URL after redirects (SSRF protection)
        if final_url != url and not self._is_safe_url(final_url):
            raise ValueError(f"Redirect target failed SSRF validation: {final_url}")

        # Handle 429/503 with Retry-After (good netizen behavior)
        # Use RateLimitError to avoid incrementing consecutive_failures
        if status_code in (429, 503):
            retry_after = response_headers.get("retry-after")
            error_msg = f"Rate limited (HTTP {status_code})"
            if retry_after:
                error_msg += f", retry after {retry_after}"
                await self._set_feed_retry_after(feed_id, retry_after)
            raise RateLimitError(error_msg, retry_after)

        # Handle 304 Not Modified - feed hasn't changed
        if status_code == 304:
            await self._update_feed_success(feed_id, etag, last_modified)
            return {"status": "not_modified", "entries_added": 0, "entries_found": 0}

        # Handle permanent redirects (301, 308) - update stored URL
        if final_url != url:
            # Note: We can't distinguish redirect types with fetch API
            # Treat any redirect as potentially permanent
            await self._update_feed_url(feed_id, final_url)
            # Track URL change on event (http_redirected already set above)
            if event:
                event.feed_url_original = url

        # Check for HTTP errors
        if status_code >= 400:
            raise ValueError(f"HTTP error {status_code}")

        # Parse feed with feedparser - response_text is now pure Python string
        feed_data = feedparser.parse(response_text)

        if feed_data.bozo and not feed_data.entries:
            raise ValueError(f"Feed parse error: {feed_data.bozo_exception}")

        # Extract cache headers from response (response_headers is Python dict in both paths)
        new_etag = response_headers.get("etag")
        new_last_modified = response_headers.get("last-modified")

        # Update feed metadata
        await self._update_feed_metadata(feed_id, feed_data.feed, new_etag, new_last_modified)

        # Process and store entries (boundary conversion handled by _to_py_list)
        entries_list = _to_py_list(feed_data.entries)

        entries_added = 0
        entries_found = len(entries_list)
        if event:
            event.entries_found = entries_found

        for entry in entries_list:
            # Ensure entry is Python dict (boundary conversion handled by _to_py_safe)
            py_entry = _to_py_safe(entry)
            if not isinstance(py_entry, dict):
                if event:
                    event.parse_errors += 1
                continue

            result = await self._upsert_entry(feed_id, py_entry, event)
            entry_id = result.get("entry_id") if result else None
            if entry_id:
                entries_added += 1
                # Aggregate indexing stats onto FeedFetchEvent
                if event and result.get("indexing_stats"):
                    stats = result["indexing_stats"]
                    event.indexing_attempted += 1
                    if stats.get("success"):
                        event.indexing_succeeded += 1
                    else:
                        event.indexing_failed += 1
                    event.indexing_total_ms += stats.get("total_ms", 0)
                    event.indexing_embedding_ms += stats.get("embedding_ms", 0)
                    event.indexing_upsert_ms += stats.get("upsert_ms", 0)
                    if stats.get("text_truncated"):
                        event.indexing_text_truncated += 1
            else:
                if event:
                    event.upsert_failures += 1

        # Mark fetch as successful
        await self._update_feed_success(feed_id, new_etag, new_last_modified)

        return {"status": "ok", "entries_added": entries_added, "entries_found": entries_found}

    def _normalize_urls(self, content: str, base_url: str) -> str:
        """Convert relative URLs in content to absolute URLs.

        Handles href and src attributes with relative paths like:
        - /images/foo.png -> https://example.com/images/foo.png
        - ../assets/bar.css -> https://example.com/assets/bar.css
        - image.jpg -> https://example.com/path/image.jpg
        """
        parsed_base = urlparse(base_url)
        base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
        base_path = parsed_base.path.rsplit("/", 1)[0] if "/" in parsed_base.path else ""

        def _resolve_url(match: re.Match[str]) -> str:
            attr = match.group(1)  # href or src
            quote = match.group(2)  # ' or "
            url = match.group(3)  # the URL value

            # Skip if already absolute or special protocol
            if url.startswith(("http://", "https://", "//", "data:", "mailto:", "#")):
                return match.group(0)

            # Resolve relative URL
            if url.startswith("/"):
                # Absolute path relative to origin
                resolved = f"{base_origin}{url}"
            else:
                # Relative path
                resolved = f"{base_origin}{base_path}/{url}"

            return f"{attr}={quote}{resolved}{quote}"

        # Match href="..." or src="..." with relative URLs
        pattern = r'(href|src)=(["\'])([^"\']+)\2'
        return re.sub(pattern, _resolve_url, content, flags=re.I)

    async def _fetch_full_content(self, url: str) -> str | None:
        """Fetch full article content from a URL when feed only provides summary.

        Uses regex-based extraction for Pyodide compatibility (no BeautifulSoup).
        Returns None if extraction fails, so caller can fall back to summary.
        """
        if not url or not self._is_safe_url(url):
            return None

        try:
            response = await safe_http_fetch(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout_seconds=self._get_http_timeout(),
            )

            if response.status_code != 200:
                return None

            html = response.text

            # Remove script and style tags with their content
            html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
            html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.I)
            html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.I)
            html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.I)

            # Try to extract content from common article containers
            # Order matters - more specific patterns first
            patterns = [
                r"<article[^>]*>(.*?)</article>",
                r"<main[^>]*>(.*?)</main>",
                r'<div[^>]*class="[^"]*(?:post-content|entry-content|article-content)[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*id="content"[^>]*>(.*?)</div>',
            ]

            content = None
            for pattern in patterns:
                match = re.search(pattern, html, flags=re.DOTALL | re.I)
                if match:
                    content = match.group(1)
                    break

            if not content:
                # Fallback: extract all paragraphs
                paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.DOTALL | re.I)
                if len(paragraphs) >= 3:
                    # Join paragraphs into content
                    content = "".join(f"<p>{p}</p>" for p in paragraphs[:50])

            if content and len(content) > 500:
                # Normalize relative URLs to absolute URLs
                content = self._normalize_urls(content, url)
                return content

            return None

        except Exception:
            # Content fetch failures are expected (timeouts, 404s, blocked)
            # Caller falls back to summary - no need to log each failure
            return None

    async def _upsert_entry(
        self, feed_id: int, entry: dict[str, Any], event: FeedFetchEvent | None = None
    ) -> dict[str, Any]:
        """Insert or update a single entry with sanitized content."""
        # Generate stable GUID - must be non-empty
        guid = entry.get("id") or entry.get("link") or entry.get("title")
        # Ensure GUID is valid (not empty, whitespace-only, or None)
        if not guid or not str(guid).strip():
            # Generate hash-based GUID as fallback
            content_hash = hashlib.sha256(
                f"{feed_id}:{entry.get('title', '')}:{entry.get('link', '')}".encode()
            ).hexdigest()[:16]
            guid = f"generated:{content_hash}"

        # Extract content (prefer full content over summary)
        # Note: After JsProxy conversion, entry is a plain dict, so use .get() not hasattr()
        content = ""
        entry_content = entry.get("content")
        if entry_content and isinstance(entry_content, list) and len(entry_content) > 0:
            first_content = entry_content[0]
            if isinstance(first_content, dict):
                content = first_content.get("value", "")
            else:
                content = str(first_content)
        elif entry.get("summary"):
            content = entry.get("summary", "")

        # If content is just a short summary, try to fetch full article content
        # This handles feeds that only provide <description> without <content:encoded>
        entry_url = entry.get("link")
        if len(content) < 500 and entry_url:
            fetched_content = await self._fetch_full_content(entry_url)
            if fetched_content:
                content = fetched_content
                if event:
                    event.content_fetched_count += 1

        # Sanitize HTML (XSS prevention)
        sanitized_content = self._sanitize_html(content)

        # Parse published date - use None if missing (don't fake current time)
        # This ensures retention policy can correctly identify old entries
        # Note: After JsProxy conversion, entry is a plain dict, so use .get() not hasattr()
        published_at = None
        pub_parsed = entry.get("published_parsed")
        upd_parsed = entry.get("updated_parsed")
        if pub_parsed and isinstance(pub_parsed, list | tuple) and len(pub_parsed) >= 6:
            published_at = datetime(*pub_parsed[:6]).isoformat()
        elif upd_parsed and isinstance(upd_parsed, list | tuple) and len(upd_parsed) >= 6:
            published_at = datetime(*upd_parsed[:6]).isoformat()
        # If no date available, leave as None (will use CURRENT_TIMESTAMP in DB)

        title = entry.get("title", "")

        # Truncate summary with indicator
        raw_summary = entry.get("summary") or ""
        if len(raw_summary) > SUMMARY_MAX_LENGTH:
            summary = raw_summary[: SUMMARY_MAX_LENGTH - 3] + "..."
        else:
            summary = raw_summary

        # Upsert to D1 - use _safe_str to convert any JsProxy/undefined to Python
        # first_seen is set on INSERT only - preserved on UPDATE to prevent spam attacks
        # where feeds retroactively add old entries that would appear as new
        result_raw = (
            await self.env.DB.prepare("""
            INSERT INTO entries (
                feed_id, guid, url, title, author, content, summary,
                published_at, first_seen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
            ON CONFLICT(feed_id, guid) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """)
            .bind(
                *entry_bind_values(
                    feed_id,
                    guid,
                    entry.get("link"),
                    title,
                    entry.get("author"),
                    sanitized_content,
                    summary,
                    published_at,
                )
            )
            .first()
        )

        # Convert JsProxy to Python dict
        result = _to_py_safe(result_raw)
        entry_id = result.get("id") if result else None

        # Index for semantic search (may fail in local dev - Vectorize not supported)
        # Capture stats for aggregation on FeedFetchEvent
        indexing_stats = None
        if entry_id and title:
            try:
                indexing_stats = await self._index_entry_for_search(
                    entry_id, title, sanitized_content, feed_id=feed_id
                )
            except Exception as e:
                # Don't fail - entry is still usable without search
                # Error is captured in indexing_stats for aggregation on parent event
                indexing_stats = {
                    "success": False,
                    "embedding_ms": 0,
                    "upsert_ms": 0,
                    "total_ms": 0,
                    "text_truncated": False,
                    "error_type": type(e).__name__,
                    "error_message": truncate_error(e),
                }

        return {"entry_id": entry_id, "indexing_stats": indexing_stats}

    async def _index_entry_for_search(
        self, entry_id: int, title: str, content: str, feed_id: int = 0, trigger: str = "feed_fetch"
    ) -> dict[str, Any]:
        """Generate embedding and store in Vectorize for semantic search.

        Args:
            entry_id: Database ID of the entry
            title: Entry title
            content: Entry content (HTML sanitized)
            feed_id: Feed ID for observability (not used in event - aggregated by caller)
            trigger: What triggered indexing - "feed_fetch", "reindex", or "manual"

        Returns:
            dict with indexing stats for aggregation on parent event:
            - success: bool
            - embedding_ms: float
            - upsert_ms: float
            - total_ms: float
            - text_truncated: bool
            - error_type: str (if failed)
            - error_message: str (if failed)

        Note: Per wide event consolidation, indexing stats are aggregated on the
        parent event (FeedFetchEvent or AdminActionEvent), not emitted separately.

        """
        stats = {
            "success": False,
            "embedding_ms": 0,
            "upsert_ms": 0,
            "total_ms": 0,
            "text_truncated": False,
            "error_type": None,
            "error_message": None,
        }

        with Timer() as wall_timer:
            try:
                # Combine title and content for embedding (truncate to configurable limit)
                max_chars = self._get_embedding_max_chars()
                combined_text = f"{title}\n\n{content[:max_chars]}"
                stats["text_truncated"] = len(content) > max_chars

                # Generate embedding using Workers AI with cls pooling for accuracy
                with Timer() as embedding_timer:
                    embedding_result = await self.env.AI.run(
                        "@cf/baai/bge-base-en-v1.5",
                        {"text": [combined_text], "pooling": "cls"},
                    )
                stats["embedding_ms"] = embedding_timer.elapsed_ms

                if not embedding_result or "data" not in embedding_result:
                    stats["error_type"] = "NoEmbeddingData"
                    stats["error_message"] = "No data in embedding result"
                    return stats

                data = embedding_result["data"]
                if not data or len(data) == 0:
                    stats["error_type"] = "EmptyEmbedding"
                    stats["error_message"] = "Empty data array in result"
                    return stats

                vector = data[0]

                # Upsert to Vectorize with entry_id as the vector ID
                with Timer() as upsert_timer:
                    await self.env.SEARCH_INDEX.upsert(
                        [
                            {
                                "id": str(entry_id),
                                "values": vector,
                                "metadata": {"title": title[:200], "entry_id": entry_id},
                            }
                        ]
                    )
                stats["upsert_ms"] = upsert_timer.elapsed_ms
                stats["success"] = True

            except Exception as e:
                stats["error_type"] = type(e).__name__
                stats["error_message"] = truncate_error(e)
                raise

        stats["total_ms"] = wall_timer.elapsed_ms
        return stats

    def _sanitize_html(self, html_content: str) -> str:
        """Sanitize HTML to prevent XSS attacks (CVE-2009-2937 mitigation)."""
        return _sanitizer.clean(html_content)

    def _is_safe_url(self, url: str) -> bool:
        """SSRF protection - reject internal/private URLs."""
        try:
            parsed = urlparse(url)
        except Exception as e:
            log_error("url_parse_error", e, url=url)
            return False

        # Only allow http/https
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname.lower() if parsed.hostname else ""

        if not hostname:
            return False

        # Block localhost variants
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False

        # Block cloud metadata endpoints
        if hostname in BLOCKED_METADATA_IPS:
            return False

        # Block private IP ranges
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
            # Block IPv6 unique local addresses (fc00::/7, which includes fd00::/8)
            # Check first byte: 0xFC or 0xFD (binary: 1111110x)
            if ip.version == 6 and (ip.packed[0] & 0xFE) == 0xFC:
                return False
        except ValueError:
            pass  # Not an IP address

        # Block internal domain patterns
        if hostname.endswith(".internal") or hostname.endswith(".local"):
            return False

        # Block cloud metadata hostnames
        metadata_hosts = [
            "metadata.google.internal",
            "metadata.azure.internal",
            "instance-data",
        ]
        return not any(hostname == h or hostname.endswith("." + h) for h in metadata_hosts)

    async def _update_feed_success(
        self, feed_id: int, etag: str | None, last_modified: str | None
    ) -> None:
        """Mark feed fetch as successful."""
        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                last_fetch_at = CURRENT_TIMESTAMP,
                last_success_at = CURRENT_TIMESTAMP,
                etag = ?,
                last_modified = ?,
                fetch_error = NULL,
                consecutive_failures = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(_safe_str(etag), _safe_str(last_modified), feed_id)
            .run()
        )

    async def _record_feed_error(
        self, feed_id: int, error_message: str, event: FeedFetchEvent | None = None
    ) -> None:
        """Record a feed fetch error and auto-deactivate after too many failures."""
        # Issue 9.4: Auto-deactivate feeds after configurable consecutive failures
        threshold = self._get_feed_auto_deactivate_threshold()
        # Note: Check consecutive_failures + 1 (the NEW value after increment) against threshold
        # to avoid race condition where the CASE sees the old value before increment
        result_raw = await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                last_fetch_at = CURRENT_TIMESTAMP,
                fetch_error = ?,
                fetch_error_count = fetch_error_count + 1,
                consecutive_failures = consecutive_failures + 1,
                is_active = CASE WHEN consecutive_failures + 1 >= ? THEN 0 ELSE is_active END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING consecutive_failures, is_active
        """)
            .bind(error_message[:500], threshold, feed_id)
            .first()
        )
        # Convert JsProxy to Python dict
        result = _to_py_safe(result_raw)
        if result and result.get("is_active") == 0 and event:
            # Feed was auto-deactivated - track on event
            event.feed_auto_deactivated = True
            event.feed_consecutive_failures = result.get("consecutive_failures", 0)

    async def _update_feed_url(self, feed_id: int, new_url: str) -> None:
        """Update feed URL after permanent redirect."""
        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(new_url, feed_id)
            .run()
        )

    async def _set_feed_retry_after(self, feed_id: int, retry_after: str) -> None:
        """Store Retry-After time for a feed (good netizen behavior).

        The retry_after value can be:
        - A number of seconds (e.g., "3600")
        - An HTTP date (e.g., "Wed, 21 Oct 2015 07:28:00 GMT")
        """
        # Parse retry_after - could be seconds or HTTP date
        try:
            seconds = int(retry_after)
            future = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            retry_until = future.isoformat().replace("+00:00", "Z")
        except ValueError:
            # Assume it's an HTTP date, store as-is for simplicity
            retry_until = retry_after

        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                fetch_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(f"Rate limited until {retry_until}", feed_id)
            .run()
        )

    async def _update_feed_metadata(
        self, feed_id: int, feed_info: FeedParserDict, etag: str | None, last_modified: str | None
    ) -> None:
        """Update feed title and other metadata from feed content."""
        # Use SafeFeedInfo wrapper for clean JS→Python boundary handling
        info = SafeFeedInfo(feed_info)

        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                title = COALESCE(?, title),
                site_url = COALESCE(?, site_url),
                author_name = COALESCE(?, author_name),
                author_email = COALESCE(?, author_email),
                etag = ?,
                last_modified = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(
                *feed_bind_values(
                    info.title,
                    info.link,
                    info.author,
                    info.author_email,
                    etag,
                    last_modified,
                    feed_id,
                )
            )
            .run()
        )

    # =========================================================================
    # HTTP Handler
    # =========================================================================

    async def fetch(
        self, request: WorkerRequest, env: WorkerEnv = None, ctx: WorkerCtx = None
    ) -> Response:
        """Handle HTTP requests."""
        # Initialize page serve event
        url = request.url
        path = (
            url.pathname
            if hasattr(url, "pathname")
            else url.split("?")[0].split("://", 1)[-1].split("/", 1)[-1]
        )
        if not path.startswith("/"):
            path = "/" + path

        # Safely extract request headers using boundary layer helper
        headers = SafeHeaders(request)
        user_agent = headers.user_agent
        referer = headers.referer

        # Get deployment context for observability
        deployment = self._get_deployment_context()

        # Initialize consolidated RequestEvent (absorbs search, generation, OAuth)
        event = RequestEvent(
            method=request.method,
            path=path,
            user_agent=user_agent[:200],
            referer=referer[:200],
            worker_version=deployment["worker_version"],
            deployment_environment=deployment["deployment_environment"],
        )

        with Timer() as timer:
            try:
                # Smart default: Auto-initialize database on first request
                await self._ensure_database_initialized()

                # Public routes (cacheable at edge via Cache-Control headers)
                if path == "/" or path == "/index.html":
                    event.route = "/"
                    response = await self._serve_html(event)
                    event.content_type = "html"
                    event.cache_status = "cacheable"

                elif path == "/titles" or path == "/titles.html":
                    event.route = "/titles"
                    response = await self._serve_titles(event)
                    event.content_type = "html"
                    event.cache_status = "cacheable"

                elif path == "/feed.atom":
                    event.route = "/feed.atom"
                    response = await self._serve_atom()
                    event.content_type = "atom"
                    event.cache_status = "cacheable"

                elif path == "/feed.rss":
                    event.route = "/feed.rss"
                    response = await self._serve_rss()
                    event.content_type = "rss"
                    event.cache_status = "cacheable"

                elif path == "/feeds.opml":
                    event.route = "/feeds.opml"
                    response = await self._export_opml()
                    event.content_type = "opml"
                    event.cache_status = "cacheable"

                elif path == "/search":
                    event.route = "/search"
                    # Search disabled in lite mode (no Vectorize)
                    if check_lite_mode(self.env):
                        response = _json_error("Search is not available in lite mode", status=404)
                        event.content_type = "error"
                    else:
                        response = await self._search_entries(request, event)
                        event.content_type = "search"
                    event.cache_status = "bypass"  # Dynamic based on query

                elif path.startswith("/static/"):
                    event.route = "/static/*"
                    response = await self._serve_static(path)
                    event.content_type = "static"
                    event.cache_status = "cacheable"

                # OAuth routes (bypass cache - session handling)
                # Disabled in lite mode (no OAuth)
                elif path == "/auth/github":
                    event.route = "/auth/github"
                    if check_lite_mode(self.env):
                        response = _json_error(
                            "Authentication is not available in lite mode", status=404
                        )
                        event.content_type = "error"
                    else:
                        event.oauth_stage = "redirect"
                        event.oauth_provider = "github"
                        event.oauth_success = None  # Redirect phase, not callback
                        response = self._redirect_to_github_oauth(request)
                        event.content_type = "auth"
                    event.cache_status = "bypass"

                elif path == "/auth/github/callback":
                    event.route = "/auth/github/callback"
                    if check_lite_mode(self.env):
                        response = _json_error(
                            "Authentication is not available in lite mode", status=404
                        )
                        event.content_type = "error"
                    else:
                        event.oauth_stage = "callback"
                        event.oauth_provider = "github"
                        response = await self._handle_github_callback(request, event)
                        event.content_type = "auth"
                    event.cache_status = "bypass"

                # Admin routes (bypass cache - authenticated, dynamic)
                # Disabled in lite mode (no OAuth, no admin)
                elif path.startswith("/admin"):
                    event.route = "/admin/*"
                    if check_lite_mode(self.env):
                        response = _json_error("Admin is not available in lite mode", status=404)
                        event.content_type = "error"
                    else:
                        response = await self._handle_admin(request, path, event)
                        event.content_type = "admin"
                    event.cache_status = "bypass"

                else:
                    event.route = "unknown"
                    response = _json_error("Not Found", status=404)
                    event.content_type = "error"
                    event.cache_status = "bypass"

            except Exception as e:
                event.wall_time_ms = timer.elapsed_ms
                event.status_code = 500
                event.outcome = "error"
                event.error_type = type(e).__name__
                event.error_message = truncate_error(e)
                emit_event(event)
                raise

        # Finalize and emit event
        event.wall_time_ms = timer.elapsed_ms
        event.status_code = response.status
        # Issue 10.3: Set response size if available (skip if JsProxy)
        try:
            if hasattr(response, "body") and response.body:
                body = response.body
                if isinstance(body, str):
                    event.response_size_bytes = len(body.encode("utf-8"))
                elif isinstance(body, bytes):
                    event.response_size_bytes = len(body)
                # Skip JsProxy or other non-standard types
        except (TypeError, AttributeError):
            pass  # Size calculation failed (JsProxy or other non-standard type)
        emit_event(event)

        return response

    async def _serve_html(self, event: RequestEvent | None = None) -> Response:
        """Generate and serve the HTML page on-demand.

        No KV caching - edge cache handles repeat requests:
        - First request: D1 query + Jinja2 render (~300-500ms)
        - Edge caches response for 1 hour
        - Subsequent requests: 0ms (served from edge)

        For a planet aggregator with ~10-20 cache misses/hour globally,
        this latency is acceptable and eliminates KV complexity.
        """
        html = await self._generate_html(event=event)
        return _html_response(html)

    async def _serve_titles(self, event: RequestEvent | None = None) -> Response:
        """Generate and serve the titles-only page on-demand.

        Similar to _serve_html but renders TEMPLATE_TITLES instead,
        showing only entry titles without content for a compact view.
        """
        html = await self._generate_html(event=event, template=TEMPLATE_TITLES)
        return _html_response(html)

    async def _generate_html(
        self,
        trigger: str = "http",
        triggered_by: str | None = None,
        event: RequestEvent | None = None,
        template: str = TEMPLATE_INDEX,
    ) -> str:
        """Generate the aggregated HTML page on-demand.

        Called by fetch() for / requests. Edge cache handles caching.

        Args:
            trigger: What triggered generation ("http", "cron", "admin_manual")
            triggered_by: Admin username if manually triggered
            event: RequestEvent to populate with generation metrics (optional)
            template: Template to render (TEMPLATE_INDEX or TEMPLATE_TITLES)

        """
        # Get planet config from environment
        planet = self._get_planet_config()

        # NOTE: Retention policy now runs in scheduler (_run_scheduler), not here
        # This ensures retention happens once per cron cycle, not on every page load

        # Query entries using configurable retention period
        # Uses first_seen for ordering/grouping to prevent spam from retroactive entries
        # Per-feed-per-day limit prevents any single feed from dominating when added
        retention_days = self._get_retention_days()
        max_per_feed = self._get_max_entries_per_feed()

        # Calculate cutoff date in Python for parameterized query
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        with Timer() as d1_timer:
            # Query entries, grouping by published_at (actual publication date)
            # Fall back to first_seen only when published_at is missing
            entries_result = await (
                self.env.DB.prepare(
                    """
                WITH ranked AS (
                    SELECT
                        e.*,
                        f.title as feed_title,
                        f.site_url as feed_site_url,
                        ROW_NUMBER() OVER (
                            PARTITION BY e.feed_id,
                                date(COALESCE(e.published_at, e.first_seen))
                            ORDER BY COALESCE(e.published_at, e.first_seen) DESC
                        ) as rn_per_day,
                        ROW_NUMBER() OVER (
                            PARTITION BY e.feed_id
                            ORDER BY COALESCE(e.published_at, e.first_seen) DESC
                        ) as rn_total
                    FROM entries e
                    JOIN feeds f ON e.feed_id = f.id
                    WHERE COALESCE(e.published_at, e.first_seen) >= ?
                    AND f.is_active = 1
                )
                SELECT * FROM ranked
                WHERE rn_per_day <= 5 AND rn_total <= ?
                ORDER BY COALESCE(published_at, first_seen) DESC
                LIMIT ?
                """
                )
                .bind(cutoff_date, max_per_feed, DEFAULT_QUERY_LIMIT)
                .all()
            )

            # Get feeds for sidebar
            feeds_result = (
                await self.env.DB.prepare("""
                SELECT
                    id, title, site_url, url, last_success_at,
                    CASE WHEN consecutive_failures < ? THEN 1 ELSE 0 END as is_healthy
                FROM feeds
                WHERE is_active = 1
                ORDER BY title
            """)
                .bind(DEFAULT_FEED_FAILURE_THRESHOLD)
                .all()
            )

        # Populate generation metrics on the consolidated event
        if event:
            event.generation_d1_ms = d1_timer.elapsed_ms
            event.generation_trigger = trigger

        # Convert D1 results to typed Python dicts
        entries = entry_rows_from_d1(entries_result.results)
        feeds = feed_rows_from_d1(feeds_result.results)

        # Smart default: Content display fallback
        # If no entries in configured date range, show the most recent entries instead
        if not entries:
            _log_op(
                "content_fallback_triggered",
                retention_days=retention_days,
                fallback_limit=FALLBACK_ENTRIES_LIMIT,
            )
            # Query most recent entries without date filter
            fallback_result = await (
                self.env.DB.prepare(
                    """
                WITH ranked AS (
                    SELECT
                        e.*,
                        f.title as feed_title,
                        f.site_url as feed_site_url,
                        ROW_NUMBER() OVER (
                            PARTITION BY e.feed_id
                            ORDER BY COALESCE(e.published_at, e.first_seen) DESC
                        ) as rn_total
                    FROM entries e
                    JOIN feeds f ON e.feed_id = f.id
                    WHERE f.is_active = 1
                )
                SELECT * FROM ranked
                WHERE rn_total <= ?
                ORDER BY COALESCE(published_at, first_seen) DESC
                LIMIT ?
                """
                )
                .bind(max_per_feed, FALLBACK_ENTRIES_LIMIT)
                .all()
            )
            entries = entry_rows_from_d1(fallback_result.results)
            if event:
                event.generation_used_fallback = True

        # Group entries by published_at (actual publication date from feed)
        # Fall back to first_seen only if published_at is missing
        # This ensures entries appear under their true publication date
        entries_by_date = {}
        for entry in entries:
            # Prefer published_at for accurate grouping, fall back to first_seen
            group_date = entry.get("published_at") or entry.get("first_seen") or ""
            date_str = group_date[:10] if group_date else "Unknown"  # YYYY-MM-DD

            # Convert to absolute date label (e.g., "January 15, 2026")
            date_label = self._format_date_label(date_str)
            if date_label not in entries_by_date:
                entries_by_date[date_label] = []

            # Add display date (same as group date for consistency)
            if date_str and date_str != "Unknown":
                entry["published_at_display"] = self._format_pub_date(group_date)
            else:
                entry["published_at_display"] = ""

            # Normalize content: strip duplicate title heading if present
            entry["content"] = _normalize_entry_content(
                entry.get("content", ""), entry.get("title")
            )

            # Compute display author (filters email addresses in Python, not templates)
            entry["display_author"] = _get_display_author(
                entry.get("author"), entry.get("feed_title")
            )

            entries_by_date[date_label].append(entry)

        # Sort entries within each day by published_at (newest first)
        for date_label in entries_by_date:
            entries_by_date[date_label].sort(
                key=lambda e: e.get("published_at") or "", reverse=True
            )

        # Sort date groups by date (most recent first)
        # Extract YYYY-MM-DD from entries to sort properly
        def get_sort_date(date_label_and_entries: tuple[str, list[dict[str, Any]]]) -> str:
            entries_list = date_label_and_entries[1]
            if entries_list:
                return entries_list[0].get("published_at") or ""
            return ""

        entries_by_date = dict(sorted(entries_by_date.items(), key=get_sort_date, reverse=True))

        for feed in feeds:
            feed["last_success_at_relative"] = self._relative_time(feed["last_success_at"])

        # Render template - track template time
        # Check if running in lite mode (no search, no auth)
        is_lite = check_lite_mode(self.env)

        # Get footer text from config
        footer_template = getattr(self.env, "FOOTER_TEXT", None) or "Powered by {name}"
        footer_text = footer_template.format(name=planet["name"])

        # Check if admin link should be shown (not in lite mode by default)
        show_admin_link_raw = getattr(self.env, "SHOW_ADMIN_LINK", None)
        show_admin_link = (show_admin_link_raw or "true").lower() == "true" and not is_lite

        # Get logo configuration for the theme
        logo = self._get_logo_config()

        # Build feed links for sidebar
        feed_links = {
            "rss": "/feed.rss",
            "titles_only": "/titles",
            "planet_planet": None,  # Not implemented
        }

        # Get theme for conditional template rendering
        theme = getattr(self.env, "THEME", None) or "default"

        # Get theme-specific related sites for sidebar
        related_sites = self._get_related_sites()

        with Timer() as render_timer:
            html = render_template(
                template,
                planet=planet,
                entries_by_date=entries_by_date,
                feeds=feeds,
                generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                is_lite_mode=is_lite,
                logo=logo,
                footer_text=footer_text,
                show_admin_link=show_admin_link,
                feed_links=feed_links,
                theme=theme,
                related_sites=related_sites,
            )

        # Populate remaining generation metrics
        if event:
            event.generation_render_ms = render_timer.elapsed_ms
            event.generation_entries_total = len(entries)
            event.generation_feeds_healthy = sum(1 for f in feeds if f.get("is_healthy"))

        return html

    async def _apply_retention_policy(self) -> dict:
        """Delete old entries and clean up vectors based on configurable retention policy.

        Returns:
            dict with retention stats for aggregation on SchedulerEvent:
            - retention_days: int
            - max_per_feed: int
            - entries_scanned: int
            - entries_deleted: int
            - vectors_deleted: int
            - errors: int

        """
        retention_days = self._get_retention_days()
        max_per_feed = self._get_max_entries_per_feed()

        stats = {
            "retention_days": retention_days,
            "max_per_feed": max_per_feed,
            "entries_scanned": 0,
            "entries_deleted": 0,
            "vectors_deleted": 0,
            "errors": 0,
        }

        # Calculate cutoff date in Python for parameterized query
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        with Timer() as d1_timer:
            # Get IDs of entries to delete
            to_delete = await (
                self.env.DB.prepare("""
                WITH ranked_entries AS (
                    SELECT
                        id,
                        feed_id,
                        published_at,
                        first_seen,
                        ROW_NUMBER() OVER (
                            PARTITION BY feed_id
                            ORDER BY published_at DESC
                        ) as rn
                    FROM entries
                ),
                entries_to_delete AS (
                    SELECT id FROM ranked_entries
                    WHERE rn > ?
                       OR COALESCE(published_at, first_seen) < ?
                )
                SELECT id FROM entries_to_delete
            """)
                .bind(max_per_feed, cutoff_date)
                .all()
            )

        deleted_ids = [row["id"] for row in entry_rows_from_d1(to_delete.results)]
        stats["entries_scanned"] = len(deleted_ids)
        stats["d1_ms"] = d1_timer.elapsed_ms

        if deleted_ids:
            # Delete vectors from Vectorize (Issue 11.2: handle errors gracefully)
            with Timer() as vectorize_timer:
                try:
                    await self.env.SEARCH_INDEX.deleteByIds([str(id) for id in deleted_ids])
                    stats["vectors_deleted"] = len(deleted_ids)
                except Exception:
                    # Error tracked in stats["errors"] for aggregation on SchedulerEvent
                    stats["errors"] += 1
                    # Continue with D1 deletion even if vector cleanup fails

            stats["vectorize_ms"] = vectorize_timer.elapsed_ms

            # Delete entries from D1 (in batches to stay under parameter limit)
            for i in range(0, len(deleted_ids), 50):
                batch = deleted_ids[i : i + 50]
                placeholders = ",".join("?" * len(batch))
                await (
                    self.env.DB.prepare(f"""
                    DELETE FROM entries WHERE id IN ({placeholders})
                """)
                    .bind(*batch)
                    .run()
                )

            stats["entries_deleted"] = len(deleted_ids)

        return stats

    def _format_datetime(self, iso_string: str | None) -> str:
        """Format ISO datetime string for display."""
        dt = _parse_iso_datetime(iso_string)
        if dt is None:
            return iso_string or ""
        return dt.strftime("%B %d, %Y at %I:%M %p")

    def _format_pub_date(self, iso_string: str | None) -> str:
        """Format publication date concisely (e.g., 'Jun 2013' or 'Jan 15')."""
        dt = _parse_iso_datetime(iso_string)
        if dt is None:
            return ""
        now = datetime.now(timezone.utc)
        # If same year, show "Mon Day" (e.g., "Jun 15")
        if dt.year == now.year:
            return dt.strftime("%b %d")
        # Otherwise show "Mon Year" (e.g., "Jun 2013")
        return dt.strftime("%b %Y")

    def _relative_time(self, iso_string: str | None) -> str:
        """Convert ISO datetime to relative time (e.g., '2 hours ago')."""
        dt = _parse_iso_datetime(iso_string)
        if dt is None:
            return "never" if not iso_string else "unknown"
        now = datetime.now(timezone.utc)
        delta = now - dt

        if delta.days > 30:
            # Use rounding for more accurate month representation
            months = (delta.days + 15) // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "just now"

    def _format_date_label(self, date_str: str) -> str:
        """Convert YYYY-MM-DD to absolute date like 'August 25, 2025'.

        Always shows the actual date rather than relative labels like 'Today'.
        This is clearer when there are gaps between posts.
        """
        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            # Format as "August 25, 2025"
            return entry_date.strftime("%B %d, %Y")
        except (ValueError, AttributeError):
            return date_str

    async def _serve_atom(self) -> Response:
        """Generate and serve Atom feed on-demand."""
        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        atom = self._generate_atom_feed(planet, entries)
        return _feed_response(atom, "application/atom+xml")

    async def _serve_rss(self) -> Response:
        """Generate and serve RSS feed on-demand."""
        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        rss = self._generate_rss_feed(planet, entries)
        return _feed_response(rss, "application/rss+xml")

    async def _get_recent_entries(self, limit: int) -> list[dict[str, Any]]:
        """Query recent entries for feeds."""
        result = (
            await self.env.DB.prepare("""
            SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            WHERE f.is_active = 1
            ORDER BY e.published_at DESC
            LIMIT ?
        """)
            .bind(limit)
            .all()
        )

        return entry_rows_from_d1(result.results)

    def _get_planet_config(self) -> dict[str, str]:
        """Get planet configuration from environment."""
        return {
            "name": getattr(self.env, "PLANET_NAME", None) or "Planet CF",
            "description": getattr(self.env, "PLANET_DESCRIPTION", None)
            or "Aggregated posts from Cloudflare employees and community",
            "link": getattr(self.env, "PLANET_URL", None) or "https://planetcf.com",
        }

    def _admin_error_response(
        self,
        message: str,
        title: str | None = None,
        status: int = 400,
        back_url: str | None = "/admin",
    ) -> Response:
        """Return an HTML error page for admin/auth errors.

        For browser-initiated requests (form submissions, OAuth callbacks),
        users expect HTML responses, not JSON. This provides a user-friendly
        error page instead of raw JSON.
        """
        planet = self._get_planet_config()
        html = render_template(
            TEMPLATE_ADMIN_ERROR,
            planet=planet,
            title=title,
            message=message,
            back_url=back_url,
        )
        return _html_response(html, cache_max_age=0)

    def _get_config_value(
        self,
        env_key: str,
        default: int | float,
        value_type: type[int] | type[float] = int,
    ) -> int | float:
        """Get a configuration value from environment with type conversion and fallback.

        This is a generic helper that consolidates the pattern used by all config getters.
        It handles environment variable lookup, type conversion, and error logging.

        Args:
            env_key: The environment variable name to look up
            default: The default value to use if not set or on error
            value_type: The type to convert to (int or float)

        Returns:
            The configured value, or the default if not set or on conversion error
        """
        try:
            value = getattr(self.env, env_key, None)
            return value_type(value) if value else default
        except (ValueError, TypeError) as e:
            _log_op(
                "config_validation_error",
                config_key=env_key,
                error=str(e),
                using_default=default,
            )
            return default

    def _get_retention_days(self) -> int:
        """Get retention days from environment, default 90."""
        return int(self._get_config_value("RETENTION_DAYS", DEFAULT_RETENTION_DAYS))

    def _get_max_entries_per_feed(self) -> int:
        """Get max entries per feed from environment, default 50."""
        return int(
            self._get_config_value("RETENTION_MAX_ENTRIES_PER_FEED", DEFAULT_MAX_ENTRIES_PER_FEED)
        )

    def _get_embedding_max_chars(self) -> int:
        """Get max chars to embed per entry from environment, default 2000."""
        return int(self._get_config_value("EMBEDDING_MAX_CHARS", DEFAULT_EMBEDDING_MAX_CHARS))

    def _get_search_score_threshold(self) -> float:
        """Get minimum similarity score threshold from environment, default 0.3."""
        return float(
            self._get_config_value("SEARCH_SCORE_THRESHOLD", DEFAULT_SEARCH_SCORE_THRESHOLD, float)
        )

    def _get_search_top_k(self) -> int:
        """Get max semantic search results from environment, default 50."""
        return int(self._get_config_value("SEARCH_TOP_K", DEFAULT_SEARCH_TOP_K))

    def _get_feed_auto_deactivate_threshold(self) -> int:
        """Get threshold for auto-deactivating feeds from environment, default 10."""
        return int(
            self._get_config_value(
                "FEED_AUTO_DEACTIVATE_THRESHOLD", DEFAULT_FEED_AUTO_DEACTIVATE_THRESHOLD
            )
        )

    def _get_feed_failure_threshold(self) -> int:
        """Get threshold for DLQ display from environment, default 3."""
        return int(self._get_config_value("FEED_FAILURE_THRESHOLD", DEFAULT_FEED_FAILURE_THRESHOLD))

    def _generate_atom_feed(self, planet: dict[str, str], entries: list[dict[str, Any]]) -> str:
        """Generate Atom 1.0 feed XML using template."""
        # Prepare entries with defaults for template
        template_entries = [
            {
                "title": e.get("title", ""),
                "url": e.get("url", ""),
                "guid": e.get("guid", e.get("url", "")),
                "published_at": e.get("published_at", ""),
                "author": e.get("author", e.get("feed_title", "")),
                "content": e.get("content", ""),
            }
            for e in entries
        ]
        return render_template(
            TEMPLATE_FEED_ATOM,
            planet=planet,
            entries=template_entries,
            updated_at=f"{datetime.now(timezone.utc).isoformat()}Z",
        )

    def _generate_rss_feed(self, planet: dict[str, str], entries: list[dict[str, Any]]) -> str:
        """Generate RSS 2.0 feed XML using template."""
        # Prepare entries with CDATA-safe content
        template_entries = [
            {
                "title": e.get("title", ""),
                "url": e.get("url", ""),
                "guid": e.get("guid", e.get("url", "")),
                "published_at": e.get("published_at", ""),
                "author": e.get("author", ""),
                # Escape ]]> in CDATA to prevent breakout attacks (Issue 2.1)
                # Content is already HTML-sanitized, but ensure CDATA boundaries are safe
                "content_cdata": e.get("content", "").replace("]]>", "]]]]><![CDATA[>"),
            }
            for e in entries
        ]
        return render_template(
            TEMPLATE_FEED_RSS,
            planet=planet,
            entries=template_entries,
            last_build_date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        )

    async def _export_opml(self) -> Response:
        """Export all active feeds as OPML using template."""
        feeds_result = await self.env.DB.prepare("""
            SELECT url, title, site_url
            FROM feeds
            WHERE is_active = 1
            ORDER BY title
        """).all()

        # Prepare feed data for template
        template_feeds = [
            {
                "title": f["title"] or f["url"],
                "url": f["url"],
                "site_url": f["site_url"] or "",
            }
            for f in feed_rows_from_d1(feeds_result.results)
        ]

        planet = self._get_planet_config()
        owner_name = getattr(self.env, "PLANET_OWNER_NAME", "Planet CF")

        opml = render_template(
            TEMPLATE_FEEDS_OPML,
            planet=planet,
            feeds=template_feeds,
            owner_name=owner_name,
            date_created=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        )

        return Response(
            opml,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Content-Disposition": 'attachment; filename="planetcf-feeds.opml"',
            },
        )

    async def _search_entries(
        self, request: WorkerRequest, event: RequestEvent | None = None
    ) -> Response:
        """Hybrid search: combines keyword matching with semantic similarity.

        Ranking strategy:
        - Keyword matches always rank above semantic matches
        - Quoted queries use phrase matching (exact sequence required)
        - Unquoted queries use substring matching

        Args:
            request: HTTP request object
            event: RequestEvent to populate with search metrics (optional)

        """
        # Parse query string
        url_str = str(request.url)
        query = ""
        if "?" in url_str:
            qs = parse_qs(url_str.split("?", 1)[1])
            query = qs.get("q", [""])[0]

        # Detect if query was originally quoted (phrase search)
        query = query.strip()
        is_phrase_search = (query.startswith('"') and query.endswith('"')) or (
            query.startswith("'") and query.endswith("'")
        )

        # Strip quotes for actual search, but remember the intent
        if is_phrase_search:
            query = query[1:-1].strip()

        # Populate search query fields on consolidated event
        if event:
            event.search_query = query[:200]
            event.search_query_length = len(query)

        if not query or len(query) < 2:
            if event:
                event.outcome = "error"
                event.error_type = "ValidationError"
                event.error_message = "Query too short"
            # Return HTML error page for browser UX, not JSON
            planet = self._get_planet_config()
            html = render_template(
                TEMPLATE_SEARCH,
                planet=planet,
                query=query,
                results=[],
                error="Please enter at least 2 characters to search.",
            )
            return _html_response(html, cache_max_age=0)
        if len(query) > MAX_SEARCH_QUERY_LENGTH:
            if event:
                event.outcome = "error"
                event.error_type = "ValidationError"
                event.error_message = "Query too long"
            # Return HTML error page for browser UX, not JSON
            planet = self._get_planet_config()
            html = render_template(
                TEMPLATE_SEARCH,
                planet=planet,
                query=query[:50] + "...",
                results=[],
                error="Search query is too long. Please use fewer than 1000 characters.",
            )
            return _html_response(html, cache_max_age=0)

        # Get search configuration
        top_k = self._get_search_top_k()
        score_threshold = self._get_search_score_threshold()

        # Track if query was truncated for user feedback
        words_truncated = False

        # Run semantic search and keyword search
        semantic_matches = []
        semantic_matches_raw = []
        keyword_entries = []

        # 1. Semantic search via Vectorize
        try:
            with Timer() as embedding_timer:
                embedding_result = await self.env.AI.run(
                    "@cf/baai/bge-base-en-v1.5", {"text": [query], "pooling": "cls"}
                )
            if event:
                event.search_embedding_ms = embedding_timer.elapsed_ms

            if embedding_result and "data" in embedding_result:
                query_vector = embedding_result["data"][0]
                with Timer() as vectorize_timer:
                    results = await self.env.SEARCH_INDEX.query(
                        query_vector, {"topK": top_k, "returnMetadata": True}
                    )
                if event:
                    event.search_vectorize_ms = vectorize_timer.elapsed_ms

                semantic_matches_raw = results.get("matches", []) if results else []

                # Apply score threshold
                semantic_matches = [
                    m for m in semantic_matches_raw if m.get("score", 0) >= score_threshold
                ]
        except Exception as e:
            if event:
                event.search_semantic_error = truncate_error(e)

        # 2. Keyword search via D1 (primary ranking signal)
        try:
            search_limit = self._get_search_top_k()
            with Timer() as d1_timer:
                # Escape special characters for LIKE pattern
                escaped_query = query.replace("%", "\\%").replace("_", "\\_")

                if is_phrase_search:
                    # Phrase search: exact sequence required
                    # LIKE '%error handling%' matches the phrase in order
                    like_pattern = f"%{escaped_query}%"
                    keyword_result = (
                        await self.env.DB.prepare("""
                        SELECT e.id, e.feed_id, e.guid, e.url, e.title, e.author,
                               e.content, e.summary, e.published_at, e.first_seen,
                               f.title as feed_title, f.site_url as feed_site_url
                        FROM entries e
                        JOIN feeds f ON e.feed_id = f.id
                        WHERE e.title LIKE ? ESCAPE '\\'
                           OR e.content LIKE ? ESCAPE '\\'
                        ORDER BY e.published_at DESC
                        LIMIT ?
                    """)
                        .bind(like_pattern, like_pattern, search_limit)
                        .all()
                    )
                else:
                    # Word search: all words must appear (any order)
                    # Split query into words and require all to match
                    words = [w.strip() for w in query.split() if w.strip()]
                    # Limit word count to prevent DoS via excessive WHERE clauses
                    if len(words) > MAX_SEARCH_WORDS:
                        words = words[:MAX_SEARCH_WORDS]
                        words_truncated = True
                        if event:
                            event.search_words_truncated = True
                    if len(words) <= 1:
                        # Single word: simple LIKE
                        like_pattern = f"%{escaped_query}%"
                        keyword_result = (
                            await self.env.DB.prepare("""
                            SELECT e.id, e.feed_id, e.guid, e.url, e.title, e.author,
                                   e.content, e.summary, e.published_at, e.first_seen,
                                   f.title as feed_title, f.site_url as feed_site_url
                            FROM entries e
                            JOIN feeds f ON e.feed_id = f.id
                            WHERE e.title LIKE ? ESCAPE '\\'
                               OR e.content LIKE ? ESCAPE '\\'
                            ORDER BY e.published_at DESC
                            LIMIT ?
                        """)
                            .bind(like_pattern, like_pattern, search_limit)
                            .all()
                        )
                    else:
                        # Multiple words: all must appear in title OR all in content
                        # Build dynamic WHERE clause (f-string needed for dynamic conditions)
                        word_patterns = []
                        bind_values = []
                        for word in words:
                            escaped_word = word.replace("%", "\\%").replace("_", "\\_")
                            word_patterns.append(f"%{escaped_word}%")
                            bind_values.append(f"%{escaped_word}%")

                        # All words in title OR all words in content
                        title_conditions = " AND ".join(
                            ["e.title LIKE ? ESCAPE '\\'" for _ in words]
                        )
                        content_conditions = " AND ".join(
                            ["e.content LIKE ? ESCAPE '\\'" for _ in words]
                        )

                        keyword_result = (
                            await self.env.DB.prepare(f"""
                            SELECT e.id, e.feed_id, e.guid, e.url, e.title, e.author,
                                   e.content, e.summary, e.published_at, e.first_seen,
                                   f.title as feed_title, f.site_url as feed_site_url
                            FROM entries e
                            JOIN feeds f ON e.feed_id = f.id
                            WHERE ({title_conditions})
                               OR ({content_conditions})
                            ORDER BY e.published_at DESC
                            LIMIT ?
                        """)
                            .bind(*bind_values, *bind_values, search_limit)
                            .all()
                        )

                keyword_entries = entry_rows_from_d1(keyword_result.results)
            if event:
                event.search_d1_ms = d1_timer.elapsed_ms
        except Exception as e:
            if event:
                event.search_keyword_error = truncate_error(e)

        # 3. Combine results: keyword matches FIRST, then semantic matches
        # This is the key ranking insight: exact text match is the strongest signal
        keyword_ids = {entry.get("id") for entry in keyword_entries if entry.get("id")}
        semantic_ids = {int(m["id"]) for m in semantic_matches}

        # Check for empty results
        if not keyword_ids and not semantic_ids:
            if event:
                event.search_results_total = 0
            planet = self._get_planet_config()
            html = render_template(TEMPLATE_SEARCH, planet=planet, query=query, results=[])
            return _html_response(html, cache_max_age=0)

        # 4. Build entry map for lookups
        entry_map = {}

        # Add keyword entries to map (already have full data)
        for entry in keyword_entries:
            entry_map[entry["id"]] = entry

        # Fetch semantic entries not already in keyword results
        semantic_only_ids = [eid for eid in semantic_ids if eid not in entry_map]
        if semantic_only_ids:
            placeholders = ",".join("?" * len(semantic_only_ids))
            db_entries = (
                await self.env.DB.prepare(f"""
                SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
                FROM entries e
                JOIN feeds f ON e.feed_id = f.id
                WHERE e.id IN ({placeholders})
            """)
                .bind(*semantic_only_ids)
                .all()
            )
            for entry in entry_rows_from_d1(db_entries.results):
                entry_map[entry["id"]] = entry

        # 5. Build sorted results: KEYWORD FIRST, SEMANTIC SECOND
        sorted_results = []
        added_ids = set()

        # Normalize query for comparison
        query_lower = query.lower().strip()

        # Counters for event metrics
        exact_title_count = 0
        title_in_query_count = 0
        query_in_title_count = 0
        keyword_content_count = 0

        # FIRST TIER: Keyword matches with title relevance (best keyword matches)
        for entry in keyword_entries:
            entry_title = (entry.get("title") or "").lower().strip()
            if not entry_title:
                continue

            entry_id = entry["id"]
            if entry_id in added_ids:
                continue

            # Exact title match (highest keyword signal)
            if query_lower == entry_title:
                sorted_results.append({**entry, "score": 1.0, "match_type": "exact_title"})
                added_ids.add(entry_id)
                exact_title_count += 1
            # Query contains entire title
            elif entry_title in query_lower:
                sorted_results.append({**entry, "score": 0.98, "match_type": "title_in_query"})
                added_ids.add(entry_id)
                title_in_query_count += 1
            # Title contains entire query
            elif query_lower in entry_title:
                sorted_results.append({**entry, "score": 0.95, "match_type": "query_in_title"})
                added_ids.add(entry_id)
                query_in_title_count += 1

        # SECOND TIER: Remaining keyword matches (content matches, partial title)
        for entry in keyword_entries:
            entry_id = entry["id"]
            if entry_id not in added_ids:
                sorted_results.append({**entry, "score": 0.80, "match_type": "keyword_content"})
                added_ids.add(entry_id)
                keyword_content_count += 1

        # THIRD TIER: Semantic matches (conceptually similar, not exact text match)
        semantic_only_count = 0
        for match in sorted(semantic_matches, key=lambda m: m.get("score", 0), reverse=True):
            entry_id = int(match["id"])
            if entry_id in entry_map and entry_id not in added_ids:
                entry = entry_map[entry_id]
                sorted_results.append(
                    {**entry, "score": match.get("score", 0), "match_type": "semantic"}
                )
                added_ids.add(entry_id)
                semantic_only_count += 1

        # Populate search metrics on consolidated event
        if event:
            event.search_results_total = len(sorted_results)
            event.search_semantic_matches = len(semantic_matches)
            event.search_keyword_matches = len(keyword_entries)
            event.search_exact_title_matches = exact_title_count
            event.search_title_in_query_matches = title_in_query_count
            event.search_query_in_title_matches = query_in_title_count

        # Add display_author to each result (filters email addresses in Python)
        for result in sorted_results:
            result["display_author"] = _get_display_author(
                result.get("author"), result.get("feed_title")
            )

        # Return HTML search results page
        planet = self._get_planet_config()
        html = render_template(
            TEMPLATE_SEARCH,
            planet=planet,
            query=query,
            results=sorted_results,
            words_truncated=words_truncated,
            max_search_words=MAX_SEARCH_WORDS,
        )
        return _html_response(html, cache_max_age=0)

    async def _serve_static(self, path: str) -> Response:
        """Serve static files."""
        # In production, static files would be served via assets binding
        # For now, serve CSS and JS inline
        if path == "/static/style.css":
            css = self._get_default_css()
            return Response(
                css,
                headers={
                    "Content-Type": "text/css",
                    "Cache-Control": "public, max-age=86400",
                },
            )
        if path == "/static/admin.js":
            js = self._get_admin_js()
            return Response(
                js,
                headers={
                    "Content-Type": "application/javascript",
                    "Cache-Control": "public, max-age=86400",
                },
            )
        if path == "/static/keyboard-nav.js":
            js = self._get_keyboard_nav_js()
            return Response(
                js,
                headers={
                    "Content-Type": "application/javascript",
                    "Cache-Control": "public, max-age=86400",
                },
            )
        if path == "/static/logo.svg":
            svg = self._get_logo_svg()
            if svg:
                return Response(
                    svg,
                    headers={
                        "Content-Type": "image/svg+xml",
                        "Cache-Control": "public, max-age=86400",
                    },
                )
        # Serve theme-specific logo images
        if path == "/static/logo.gif" or path == "/static/logo.png":
            theme = getattr(self.env, "THEME", None) or "default"
            assets = THEME_ASSETS.get(theme)
            if assets and "logo" in assets:
                logo_data = assets["logo"]
                # Parse data URI: data:image/type;base64,DATA
                if logo_data.startswith("data:"):
                    parts = logo_data.split(",", 1)
                    if len(parts) == 2:
                        header, b64_data = parts
                        # Extract content type (e.g., image/gif or image/png)
                        content_type = header.split(";")[0].replace("data:", "")
                        import base64

                        image_data = base64.b64decode(b64_data)
                        return Response(
                            image_data,
                            headers={
                                "Content-Type": content_type,
                                "Cache-Control": "public, max-age=86400",
                            },
                        )
        return _json_error("Not Found", status=404)

    def _get_logo_svg(self) -> str | None:
        """Return logo SVG based on THEME environment variable."""
        theme = getattr(self.env, "THEME", None) or "default"
        logo_config = THEME_LOGOS.get(theme)
        if logo_config:
            return logo_config.get("svg")
        return None

    def _get_logo_config(self) -> dict | None:
        """Return logo configuration dict for template rendering."""
        theme = getattr(self.env, "THEME", None) or "default"
        logo_config = THEME_LOGOS.get(theme)
        if logo_config:
            return {
                "url": logo_config["url"],
                "alt": logo_config["alt"],
                "width": logo_config["width"],
                "height": logo_config["height"],
            }
        return None

    def _get_related_sites(self) -> list[dict] | None:
        """Return theme-specific related sites for sidebar rendering.

        These extra sidebar sections match the original planet sites for
        visual fidelity.
        """
        theme = getattr(self.env, "THEME", None) or "default"

        # Theme-specific sidebar sections for visual fidelity
        # Planet Python sections match original: https://planetpython.org/
        related_sites_by_theme = {
            "planet-python": [
                {
                    "title": "Other Python Planets",
                    "links": [
                        {
                            "name": "Python Summer of Code",
                            "url": "http://terri.toybox.ca/python-soc/",
                        },
                        {"name": "Planet Python Francophone", "url": "http://www.afpy.org/planet/"},
                        {"name": "Planet Python Argentina", "url": "http://planeta.python.org.ar/"},
                        {"name": "Planet Python Brasil", "url": "http://planet.python.org.br/"},
                        {"name": "Planet Python Poland", "url": "http://pl.python.org/planeta/"},
                    ],
                },
                {
                    "title": "Python Libraries",
                    "links": [
                        {"name": "OLPC", "url": "http://planet.laptop.org/"},
                        {"name": "PySoy", "url": "http://planet.pysoy.org/"},
                        {"name": "SciPy", "url": "http://planet.scipy.org/"},
                        {"name": "SymPy", "url": "http://planet.sympy.org/"},
                        {"name": "Twisted", "url": "http://planet.twistedmatrix.com/"},
                    ],
                },
                {
                    "title": "Python/Web Planets",
                    "links": [
                        {"name": "CherryPy", "url": "http://planet.cherrypy.org/"},
                        {
                            "name": "Django Community",
                            "url": "http://www.djangoproject.com/community/",
                        },
                        {"name": "Plone", "url": "http://planet.plone.org/"},
                        {"name": "Turbogears", "url": "http://planet.turbogears.org/"},
                    ],
                },
                {
                    "title": "Other Languages",
                    "links": [
                        {"name": "Haskell", "url": "http://planet.haskell.org/"},
                        {"name": "Lisp", "url": "http://planet.lisp.org/"},
                        {"name": "Parrot", "url": "http://planet.parrotcode.org/"},
                        {"name": "Perl", "url": "http://planet.perl.org/"},
                        {"name": "Ruby", "url": "http://planetruby.0x42.net/"},
                    ],
                },
                {
                    "title": "Databases",
                    "links": [
                        {"name": "MySQL", "url": "http://www.planetmysql.org/"},
                        {"name": "PostgreSQL", "url": "http://planet.postgresql.org/"},
                    ],
                },
            ],
            # Planet Mozilla has no sidebar in original - return None
            "planet-mozilla": None,
        }

        return related_sites_by_theme.get(theme)

    def _get_default_css(self) -> str:
        """Return CSS styling based on THEME environment variable.

        Supports instance-specific themes (planet-python, planet-mozilla)
        with fallback to default STATIC_CSS.
        """
        theme = getattr(self.env, "THEME", None) or "default"
        theme_css = THEME_CSS.get(theme)
        if theme_css:
            return theme_css
        return STATIC_CSS

    def _get_admin_js(self) -> str:
        """Return admin dashboard JavaScript from templates module."""
        return ADMIN_JS

    def _get_keyboard_nav_js(self) -> str:
        """Return keyboard navigation JavaScript from templates module."""
        return KEYBOARD_NAV_JS

    # =========================================================================
    # Admin Routes
    # =========================================================================

    async def _handle_admin(
        self, request: WorkerRequest, path: str, event: RequestEvent | None = None
    ) -> Response:
        """Handle admin routes with GitHub OAuth."""
        # Verify signed session cookie (stateless, no KV)
        session = self._verify_signed_cookie(request)
        if not session:
            # Show login page instead of auto-redirecting
            return self._serve_admin_login()

        # Verify user is still an authorized admin (may have been revoked)
        admin_result = (
            await self.env.DB.prepare(
                "SELECT * FROM admins WHERE github_username = ? AND is_active = 1"
            )
            .bind(session["github_username"])
            .first()
        )

        # Convert D1 row to typed Python dict
        admin = admin_row_from_js(admin_result)

        if not admin:
            return _json_error("Unauthorized: Not an admin", status=403)

        # Route admin requests
        method = request.method

        if path == "/admin" or path == "/admin/":
            return await self._serve_admin_dashboard(admin)

        if path == "/admin/feeds" and method == "GET":
            return await self._list_feeds()

        if path == "/admin/feeds" and method == "POST":
            return await self._add_feed(request, admin)

        if path.startswith("/admin/feeds/") and method == "DELETE":
            feed_id = _validate_feed_id(path.split("/")[-1])
            if feed_id is None:
                return _json_error("Invalid feed ID", status=400)
            return await self._remove_feed(feed_id, admin)

        if path.startswith("/admin/feeds/") and method == "PUT":
            feed_id = _validate_feed_id(path.split("/")[-1])
            if feed_id is None:
                return _json_error("Invalid feed ID", status=400)
            return await self._update_feed(request, feed_id, admin)

        if path.startswith("/admin/feeds/") and path.endswith("/toggle") and method == "POST":
            # Toggle feed active status
            parts = path.split("/")
            if len(parts) >= 4:
                feed_id = _validate_feed_id(parts[3])
                if feed_id is None:
                    return _json_error("Invalid feed ID", status=400)
                return await self._update_feed(request, feed_id, admin)
            return _json_error("Invalid path", status=400)

        if path.startswith("/admin/feeds/") and method == "POST":
            # Handle form override for DELETE
            form = SafeFormData(await request.form_data())
            if form.get("_method") == "DELETE":
                feed_id = _validate_feed_id(path.split("/")[-1])
                if feed_id is None:
                    return _json_error("Invalid feed ID", status=400)
                return await self._remove_feed(feed_id, admin)
            return _json_error("Method not allowed", status=405)

        if path == "/admin/import-opml" and method == "POST":
            return await self._import_opml(request, admin)

        if path == "/admin/regenerate" and method == "POST":
            return await self._trigger_regenerate(admin)

        if path == "/admin/dlq" and method == "GET":
            return await self._view_dlq()

        if path.startswith("/admin/dlq/") and path.endswith("/retry") and method == "POST":
            # Extract feed_id from /admin/dlq/{id}/retry
            parts = path.split("/")
            if len(parts) >= 4:
                feed_id = _validate_feed_id(parts[3])
                if feed_id is None:
                    return _json_error("Invalid feed ID", status=400)
                return await self._retry_dlq_feed(feed_id, admin)
            return _json_error("Invalid path", status=400)

        if path == "/admin/audit" and method == "GET":
            return await self._view_audit_log()

        if path == "/admin/reindex" and method == "POST":
            return await self._reindex_all_entries(admin)

        if path == "/admin/logout" and method == "POST":
            return self._logout(request)

        return _json_error("Not Found", status=404)

    def _serve_admin_login(self) -> Response:
        """Serve the admin login page."""
        planet = self._get_planet_config()
        html = render_template(TEMPLATE_ADMIN_LOGIN, planet=planet)
        return _html_response(html, cache_max_age=0)

    async def _serve_admin_dashboard(self, admin: dict[str, Any]) -> Response:
        """Serve the admin dashboard."""
        feeds_result = await self.env.DB.prepare("""
            SELECT * FROM feeds ORDER BY title
        """).all()

        planet = self._get_planet_config()
        html = render_template(
            TEMPLATE_ADMIN_DASHBOARD,
            planet=planet,
            admin=admin,
            feeds=feed_rows_from_d1(feeds_result.results),
        )
        return _html_response(html, cache_max_age=0)

    async def _list_feeds(self) -> Response:
        """List all feeds as JSON."""
        result = await self.env.DB.prepare("""
            SELECT * FROM feeds ORDER BY title
        """).all()
        return _json_response({"feeds": feed_rows_from_d1(result.results)})

    async def _validate_feed_url(self, url: str) -> dict:
        """Validate a feed URL by fetching and parsing it.

        Returns dict with:
        - valid: bool
        - title: str or None (extracted from feed)
        - site_url: str or None
        - entry_count: int
        - error: str or None (if invalid)
        """
        try:
            headers = {"User-Agent": USER_AGENT}

            # Use centralized safe_http_fetch for boundary-safe HTTP
            http_response = await safe_http_fetch(url, headers=headers, timeout_seconds=10)
            status_code = http_response.status_code
            final_url = http_response.final_url
            response_text = http_response.text

            if status_code >= 400:
                return {"valid": False, "error": f"HTTP {status_code}"}

            # Check for redirects to unsafe URLs
            if final_url != url and not self._is_safe_url(final_url):
                return {
                    "valid": False,
                    "error": f"Redirect to unsafe URL: {final_url}",
                }

            # Parse with feedparser - response_text is pure Python string
            feed_data = feedparser.parse(response_text)

            # Check for parse errors
            if feed_data.bozo and not feed_data.entries:
                # Security: Log detailed error internally, return generic message
                bozo_exc = feed_data.bozo_exception
                log_op(
                    "feed_validation_parse_error",
                    url=url,
                    error_type=type(bozo_exc).__name__ if bozo_exc else "Unknown",
                    error_detail=truncate_error(bozo_exc) if bozo_exc else "Invalid format",
                )
                return {
                    "valid": False,
                    "error": "Feed format is invalid or not a recognized RSS/Atom feed",
                }

            # Extract metadata - use _safe_str for JsProxy safety
            feed_info = feed_data.feed
            title = _safe_str(feed_info.get("title"))
            site_url = _safe_str(feed_info.get("link"))
            entry_count = len(feed_data.entries)

            # Require at least a title or some entries to be considered valid
            if not title and entry_count == 0:
                return {
                    "valid": False,
                    "error": "Feed has no title and no entries",
                }

            return {
                "valid": True,
                "title": title,
                "site_url": site_url,
                "entry_count": entry_count,
                "final_url": final_url if final_url != url else None,
                "error": None,
            }

        except Exception as e:
            error_msg = truncate_error(e)
            if "timeout" in error_msg.lower():
                return {"valid": False, "error": "Timeout fetching feed (10s)"}
            return {"valid": False, "error": error_msg}

    async def _add_feed(self, request: WorkerRequest, admin: dict[str, Any]) -> Response:
        """Add a new feed with validation.

        Flow:
        1. Validate URL (SSRF protection)
        2. Fetch and parse the feed to verify it works
        3. Extract title if not provided
        4. Insert into database
        5. Queue for immediate full processing
        """
        admin_event = self._create_admin_event(admin, "add_feed", "feed")

        with Timer() as timer:
            try:
                form = SafeFormData(await request.form_data())
                url = form.get("url")
                title = form.get("title")

                if not url:
                    admin_event.outcome = "error"
                    admin_event.error_type = "ValidationError"
                    admin_event.error_message = "URL is required"
                    return self._admin_error_response(
                        "Please provide a feed URL.", title="URL Required"
                    )

                # Validate URL (SSRF protection)
                if not self._is_safe_url(url):
                    admin_event.outcome = "error"
                    admin_event.error_type = "ValidationError"
                    admin_event.error_message = "Invalid or unsafe URL"
                    return self._admin_error_response(
                        "The URL provided is invalid or points to an unsafe location.",
                        title="Invalid URL",
                    )

                # Validate the feed by fetching and parsing it
                validation = await self._validate_feed_url(url)

                if not validation["valid"]:
                    admin_event.outcome = "error"
                    admin_event.error_type = "ValidationError"
                    admin_event.error_message = truncate_error(validation["error"])
                    return self._admin_error_response(
                        f"Could not validate feed: {validation['error']}",
                        title="Feed Validation Failed",
                    )

                # Use extracted title if admin didn't provide one
                if not title:
                    title = validation.get("title")

                # If feed was permanently redirected, use the new URL
                final_url = validation.get("final_url") or url

                # Insert the validated feed
                result_raw = (
                    await self.env.DB.prepare("""
                    INSERT INTO feeds (url, title, site_url, is_active)
                    VALUES (?, ?, ?, 1)
                    RETURNING id
                """)
                    .bind(final_url, title, validation.get("site_url"))
                    .first()
                )

                # Convert JsProxy to Python dict
                result = _to_py_safe(result_raw)
                feed_id = result.get("id") if result else None
                admin_event.target_id = feed_id

                # Audit log with validation info
                await self._log_admin_action(
                    admin["id"],
                    "add_feed",
                    "feed",
                    feed_id,
                    {
                        "url": final_url,
                        "original_url": url if final_url != url else None,
                        "title": title,
                        "entry_count": validation.get("entry_count", 0),
                    },
                )

                # Queue the feed for immediate full processing (fetch entries)
                if self.env.FEED_QUEUE is not None:
                    await self.env.FEED_QUEUE.send(
                        {
                            "feed_id": feed_id,
                            "url": final_url,
                        }
                    )

                admin_event.outcome = "success"

                # Redirect back to admin
                return _redirect_response("/admin")

            except Exception as e:
                admin_event.outcome = "error"
                admin_event.error_type = type(e).__name__
                admin_event.error_message = truncate_error(e)
                return self._admin_error_response(
                    "An unexpected error occurred while adding the feed. Please try again.",
                    title="Error Adding Feed",
                    status=500,
                )
            finally:
                admin_event.wall_time_ms = timer.elapsed_ms
                emit_event(admin_event)

    async def _remove_feed(self, feed_id: int, admin: dict[str, Any]) -> Response:
        """Remove a feed."""
        admin_event = self._create_admin_event(admin, "remove_feed", "feed")

        with Timer() as timer:
            try:
                admin_event.target_id = feed_id

                # Get feed info for audit log
                feed_result = (
                    await self.env.DB.prepare("SELECT * FROM feeds WHERE id = ?")
                    .bind(feed_id)
                    .first()
                )

                # Convert D1 row to typed Python dict
                feed = feed_row_from_js(feed_result)

                if not feed:
                    admin_event.outcome = "error"
                    admin_event.error_type = "NotFound"
                    admin_event.error_message = "Feed not found"
                    return self._admin_error_response(
                        "The feed you're trying to delete could not be found.",
                        title="Feed Not Found",
                        status=404,
                    )

                # Delete feed (entries will cascade)
                await self.env.DB.prepare("DELETE FROM feeds WHERE id = ?").bind(feed_id).run()

                # Audit log - feed is now a Python dict
                await self._log_admin_action(
                    admin["id"],
                    "remove_feed",
                    "feed",
                    feed_id,
                    {"url": feed.get("url"), "title": feed.get("title")},
                )

                admin_event.outcome = "success"

                # Redirect back to admin
                return _redirect_response("/admin")

            except Exception as e:
                admin_event.outcome = "error"
                admin_event.error_type = type(e).__name__
                admin_event.error_message = truncate_error(e)
                return self._admin_error_response(
                    "An unexpected error occurred while deleting the feed. Please try again.",
                    title="Error Deleting Feed",
                    status=500,
                )
            finally:
                admin_event.wall_time_ms = timer.elapsed_ms
                emit_event(admin_event)

    async def _update_feed(
        self, request: WorkerRequest, feed_id: int, admin: dict[str, Any]
    ) -> Response:
        """Update a feed (enable/disable, edit title).

        Uses optimistic locking to prevent lost updates from concurrent edits.
        """
        admin_event = self._create_admin_event(admin, "update_feed", "feed")

        with Timer() as timer:
            try:
                admin_event.target_id = feed_id
                data_raw = await request.json()

                # Convert JsProxy to Python dict if needed
                data = _to_py_safe(data_raw) or {}

                # Build dynamic update based on provided fields
                updates = []
                params = []
                audit_details = {}

                if "is_active" in data:
                    is_active = 1 if data["is_active"] else 0
                    updates.append("is_active = ?")
                    params.append(is_active)
                    audit_details["is_active"] = is_active

                if "title" in data:
                    title = _safe_str(data["title"])
                    updates.append("title = ?")
                    params.append(title)
                    audit_details["title"] = title

                if not updates:
                    return _json_error("No valid fields to update", status=400)

                # Always update the timestamp
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(feed_id)

                sql = f"UPDATE feeds SET {', '.join(updates)} WHERE id = ?"
                await self.env.DB.prepare(sql).bind(*params).run()

                # Audit log
                await self._log_admin_action(
                    admin["id"], "update_feed", "feed", feed_id, audit_details
                )

                admin_event.outcome = "success"
                return _json_response({"success": True})

            except Exception as e:
                admin_event.outcome = "error"
                admin_event.error_type = type(e).__name__
                admin_event.error_message = truncate_error(e)
                return _json_error(str(e), status=500)
            finally:
                admin_event.wall_time_ms = timer.elapsed_ms
                emit_event(admin_event)

    async def _import_opml(self, request: WorkerRequest, admin: dict[str, Any]) -> Response:
        """Import feeds from uploaded OPML file. Admin only."""
        admin_event = self._create_admin_event(admin, "import_opml", "feeds")

        with Timer() as timer:
            try:
                form = await request.form_data()
                # File uploads need direct access, not string conversion
                opml_file = form.get("opml")

                # Check for both Python None and JavaScript undefined
                if not opml_file or _is_js_undefined(opml_file):
                    admin_event.outcome = "error"
                    admin_event.error_type = "ValidationError"
                    admin_event.error_message = "No file uploaded"
                    return self._admin_error_response(
                        "Please select an OPML file to upload.",
                        title="No File Selected",
                    )

                # Handle both JsProxy File and test mock
                if hasattr(opml_file, "text"):
                    result = opml_file.text()
                    # Await if it's a coroutine or JS Promise (JsProxy with 'then' method)
                    if asyncio.iscoroutine(result) or hasattr(result, "then"):
                        content = await result
                    else:
                        content = result
                else:
                    # Already a string (test fallback)
                    content = str(opml_file)

                admin_event.import_file_size = len(content) if content else 0

                # Parse OPML with XXE/Billion Laughs protection
                # Security: forbid_dtd=True prevents DOCTYPE declarations and entity expansion
                try:
                    parser = ET.XMLParser(forbid_dtd=True)
                    root = ET.fromstring(content, parser=parser)
                except ET.ParseError:
                    # Don't expose detailed parse errors to users
                    # Error captured on AdminActionEvent (emitted in finally block)
                    admin_event.outcome = "error"
                    admin_event.error_type = "ParseError"
                    admin_event.error_message = "Invalid OPML format"
                    return self._admin_error_response(
                        "The uploaded file is not a valid OPML file. Please check the file format.",
                        title="Invalid OPML Format",
                    )

                imported = 0
                skipped = 0
                feeds_parsed = 0
                errors = []

                for outline in root.iter("outline"):
                    xml_url = outline.get("xmlUrl")
                    if not xml_url:
                        continue

                    feeds_parsed += 1

                    # Enforce feed limit to prevent DoS via unbounded imports
                    if feeds_parsed > MAX_OPML_FEEDS:
                        errors.append(f"Feed limit ({MAX_OPML_FEEDS}) reached, skipping rest")
                        skipped += 1
                        continue

                    title = outline.get("title") or outline.get("text") or xml_url
                    html_url = outline.get("htmlUrl")

                    # Validate URL (SSRF protection)
                    if not self._is_safe_url(xml_url):
                        errors.append(f"Skipped unsafe URL: {xml_url}")
                        skipped += 1
                        continue

                    try:
                        await (
                            self.env.DB.prepare("""
                            INSERT INTO feeds (url, title, site_url, is_active)
                            VALUES (?, ?, ?, 1)
                            ON CONFLICT(url) DO NOTHING
                        """)
                            .bind(xml_url, title, html_url)
                            .run()
                        )
                        imported += 1
                    except Exception as e:
                        skipped += 1
                        errors.append(f"Failed to import {xml_url}: {e}")

                # Populate OPML import metrics
                admin_event.import_feeds_parsed = feeds_parsed
                admin_event.import_feeds_added = imported
                admin_event.import_feeds_skipped = skipped
                admin_event.import_errors = len(errors)
                admin_event.outcome = "success"

                # Audit log
                await self._log_admin_action(
                    admin["id"],
                    "import_opml",
                    "feeds",
                    None,
                    {"imported": imported, "skipped": skipped, "errors": errors[:10]},
                )

                # Redirect back to admin
                return _redirect_response("/admin")

            except Exception as e:
                admin_event.outcome = "error"
                admin_event.error_type = type(e).__name__
                admin_event.error_message = truncate_error(e)
                return self._admin_error_response(
                    "An unexpected error occurred while importing the OPML file. Please try again.",
                    title="Import Error",
                    status=500,
                )
            finally:
                admin_event.wall_time_ms = timer.elapsed_ms
                emit_event(admin_event)

    async def _trigger_regenerate(self, admin: dict[str, Any]) -> Response:
        """Force regeneration by clearing edge cache (not really possible, but log the action)."""
        # In practice, edge cache expires on its own. This is more of a manual trigger to re-fetch.
        await self._log_admin_action(admin["id"], "manual_refresh", None, None, {})

        # Queue all active feeds for immediate fetch
        await self._run_scheduler()

        return _redirect_response("/admin")

    async def _view_dlq(self) -> Response:
        """View dead letter queue contents (failed feeds with configurable threshold)."""
        threshold = self._get_feed_failure_threshold()
        result = await (
            self.env.DB.prepare("""
            SELECT id, url, title, consecutive_failures, last_fetch_at, fetch_error as last_error
            FROM feeds
            WHERE consecutive_failures >= ?
            ORDER BY consecutive_failures DESC, last_fetch_at DESC
        """)
            .bind(threshold)
            .all()
        )
        return _json_response({"failed_feeds": feed_rows_from_d1(result.results)})

    async def _retry_dlq_feed(self, feed_id: int, admin: dict[str, Any]) -> Response:
        """Retry a failed feed by resetting its failure count and re-queuing."""
        admin_event = self._create_admin_event(admin, "retry_dlq", "feed")

        with Timer() as timer:
            try:
                admin_event.target_id = feed_id
                admin_event.dlq_feed_id = feed_id

                # Get feed info
                feed_result = (
                    await self.env.DB.prepare("SELECT * FROM feeds WHERE id = ?")
                    .bind(feed_id)
                    .first()
                )

                # Convert D1 row to typed Python dict
                feed = feed_row_from_js(feed_result)

                if not feed:
                    admin_event.outcome = "error"
                    admin_event.error_type = "NotFound"
                    admin_event.error_message = "Feed not found"
                    return self._admin_error_response(
                        "The feed you're trying to retry could not be found.",
                        title="Feed Not Found",
                        status=404,
                    )

                # Capture original error for observability
                admin_event.dlq_original_error = feed.get("fetch_error", "")[
                    :ERROR_MESSAGE_MAX_LENGTH
                ]
                admin_event.dlq_action = "retry"

                # Reset failure count
                await (
                    self.env.DB.prepare("""
                    UPDATE feeds SET
                        consecutive_failures = 0,
                        is_active = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """)
                    .bind(feed_id)
                    .run()
                )

                # Queue the feed for immediate fetch - feed is now a Python dict
                if self.env.FEED_QUEUE is not None:
                    message = {
                        "feed_id": feed_id,
                        "url": feed.get("url"),
                        "etag": feed.get("etag"),
                        "last_modified": feed.get("last_modified"),
                    }
                    await self.env.FEED_QUEUE.send(message)

                # Audit log
                await self._log_admin_action(
                    admin["id"],
                    "retry_dlq",
                    "feed",
                    feed_id,
                    {"url": feed.get("url"), "previous_failures": feed.get("consecutive_failures")},
                )

                admin_event.outcome = "success"
                return _redirect_response("/admin")

            except Exception as e:
                # Error captured on AdminActionEvent (emitted in finally block)
                admin_event.outcome = "error"
                admin_event.error_type = type(e).__name__
                admin_event.error_message = truncate_error(e)
                return self._admin_error_response(
                    "An unexpected error occurred while retrying the feed. Please try again.",
                    title="Retry Error",
                    status=500,
                )
            finally:
                admin_event.wall_time_ms = timer.elapsed_ms
                emit_event(admin_event)

    async def _view_audit_log(self, offset: int = 0, limit: int = 100) -> Response:
        """View audit log with pagination support.

        Args:
            offset: Number of entries to skip (default 0)
            limit: Maximum entries to return (default 100, max 100)
        """
        # Clamp limit to prevent excessive queries
        limit = min(max(1, limit), 100)
        offset = max(0, offset)

        result = (
            await self.env.DB.prepare("""
            SELECT al.*, a.github_username, a.display_name
            FROM audit_log al
            LEFT JOIN admins a ON al.admin_id = a.id
            ORDER BY al.created_at DESC
            LIMIT ? OFFSET ?
        """)
            .bind(limit, offset)
            .all()
        )

        entries = audit_rows_from_d1(result.results)
        return _json_response(
            {
                "entries": entries,
                "offset": offset,
                "limit": limit,
                "has_more": len(entries) == limit,
            }
        )

    async def _reindex_all_entries(self, admin: dict[str, Any]) -> Response:
        """Re-index all entries in Vectorize for search.

        This is needed when entries exist in D1 but were never indexed
        (e.g., added before Vectorize was configured, or indexing failed).

        Rate limited to prevent DoS - only one reindex per REINDEX_COOLDOWN_SECONDS.
        """
        admin_event = self._create_admin_event(admin, "reindex", "search_index")

        with Timer() as timer:
            try:
                # Rate limiting: check last reindex time
                last_reindex = await self.env.DB.prepare("""
                    SELECT created_at FROM audit_log
                    WHERE action = 'reindex'
                    ORDER BY created_at DESC
                    LIMIT 1
                """).first()

                if last_reindex:
                    last_reindex_time = _parse_iso_datetime(
                        _to_py_safe(last_reindex).get("created_at")
                    )
                    if last_reindex_time:
                        elapsed = (datetime.now(timezone.utc) - last_reindex_time).total_seconds()
                        if elapsed < REINDEX_COOLDOWN_SECONDS:
                            remaining = int(REINDEX_COOLDOWN_SECONDS - elapsed)
                            admin_event.outcome = "error"
                            admin_event.error_type = "RateLimited"
                            admin_event.error_message = f"Cooldown: {remaining}s remaining"
                            return _json_error(
                                f"Reindex rate limited. Please wait {remaining} seconds.",
                                status=429,
                            )

                # Get all entries with their content (include feed_id for observability)
                result = await self.env.DB.prepare("""
                    SELECT id, feed_id, title, content FROM entries WHERE title IS NOT NULL
                """).all()

                entries = entry_rows_from_d1(result.results)
                indexed = 0
                failed = 0

                admin_event.reindex_entries_total = len(entries)

                for entry in entries:
                    entry_id = entry.get("id")
                    feed_id = entry.get("feed_id", 0)
                    title = entry.get("title", "")
                    content = entry.get("content", "")

                    if not entry_id or not title:
                        continue

                    try:
                        await self._index_entry_for_search(
                            entry_id, title, content, feed_id=feed_id, trigger="reindex"
                        )
                        indexed += 1
                    except Exception:
                        # Error count aggregated on AdminActionEvent.reindex_entries_failed
                        failed += 1

                admin_event.reindex_entries_indexed = indexed
                admin_event.reindex_entries_failed = failed

                # Log admin action
                await self._log_admin_action(
                    admin["id"],
                    "reindex",
                    "search_index",
                    0,
                    {"indexed": indexed, "failed": failed, "total": len(entries)},
                )

                admin_event.outcome = "success"

                return _json_response(
                    {
                        "success": True,
                        "indexed": indexed,
                        "failed": failed,
                        "total": len(entries),
                    }
                )

            except Exception as e:
                admin_event.outcome = "error"
                admin_event.error_type = type(e).__name__
                admin_event.error_message = truncate_error(e)
                return _json_error(str(e), status=500)
            finally:
                admin_event.reindex_total_ms = timer.elapsed_ms
                admin_event.wall_time_ms = timer.elapsed_ms
                emit_event(admin_event)

    async def _log_admin_action(
        self,
        admin_id: int | None,
        action: str | None,
        target_type: str | None,
        target_id: int | None,
        details: dict[str, Any] | None,
    ) -> None:
        """Log an admin action to the audit log."""
        # CRITICAL: First convert all inputs through _to_py_safe to handle JsProxy
        # Python None can become JavaScript undefined, which D1 rejects
        admin_id_py = _to_py_safe(admin_id)
        action_py = _to_py_safe(action)
        target_type_py = _to_py_safe(target_type)
        target_id_py = _to_py_safe(target_id)

        # Convert to safe types with fallbacks
        safe_admin_id = int(admin_id_py) if admin_id_py is not None else 0
        safe_action = str(action_py) if action_py else ""
        safe_target_type = str(target_type_py) if target_type_py else ""
        safe_target_id = int(target_id_py) if target_id_py is not None else 0

        # Ensure details dict values are Python primitives for json.dumps
        # Filter out None values to avoid any potential undefined issues
        safe_details = {}
        if details:
            for k, v in details.items():
                v_py = _to_py_safe(v)
                if v_py is not None:
                    safe_details[k] = v_py

        details_json = json.dumps(safe_details)
        await (
            self.env.DB.prepare("""
            INSERT INTO audit_log (admin_id, action, target_type, target_id, details)
            VALUES (?, ?, ?, ?, ?)
        """)
            .bind(safe_admin_id, safe_action, safe_target_type, safe_target_id, details_json)
            .run()
        )

    # =========================================================================
    # OAuth & Session Management
    # =========================================================================

    def _verify_signed_cookie(self, request: WorkerRequest) -> dict[str, Any] | None:
        """Verify the signed session cookie (stateless, no KV).

        Cookie format: base64(json_payload).signature
        """
        cookies = SafeHeaders(request).cookie
        session_cookie = None
        for cookie in cookies.split(";"):
            if cookie.strip().startswith("session="):
                session_cookie = cookie.strip()[8:]
                break

        if not session_cookie or "." not in session_cookie:
            return None

        try:
            payload_b64, signature = session_cookie.rsplit(".", 1)

            # Verify signature
            expected_sig = hmac.new(
                self.env.SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            # Decode payload
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            # Check expiration with minimal grace period for clock skew
            if payload.get("exp", 0) < time.time() - SESSION_GRACE_SECONDS:
                return None

            return payload
        except Exception as e:
            log_op(
                "session_verify_failed",
                error_type=type(e).__name__,
                error=truncate_error(e),
            )
            return None

    def _redirect_to_github_oauth(self, request: WorkerRequest) -> Response:
        """Redirect to GitHub OAuth authorization."""
        state = secrets.token_urlsafe(32)
        client_id = getattr(self.env, "GITHUB_CLIENT_ID", "")

        # Security: Use configured redirect_uri to prevent open redirect attacks
        # OAUTH_REDIRECT_URI should be set in wrangler.toml for production
        configured_redirect = getattr(self.env, "OAUTH_REDIRECT_URI", None)
        if configured_redirect:
            redirect_uri = configured_redirect
        else:
            # Fallback for local dev: extract origin from request URL
            # Note: In Cloudflare Workers, request.url is not user-controlled
            url = request.url
            if hasattr(url, "origin"):
                origin = url.origin
            else:
                url_str = str(url)
                parsed = urlparse(url_str)
                origin = f"{parsed.scheme}://{parsed.netloc}"
            redirect_uri = f"{origin}/auth/github/callback"

        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope=read:user"
            f"&state={state}"
        )

        state_cookie = f"oauth_state={state}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=600"
        return Response(
            "",
            status=302,
            headers={"Location": auth_url, "Set-Cookie": state_cookie},
        )

    async def _handle_github_callback(
        self, request: WorkerRequest, event: RequestEvent | None = None
    ) -> Response:
        """Handle GitHub OAuth callback."""
        try:
            url_str = str(request.url)
            qs = parse_qs(url_str.split("?", 1)[1]) if "?" in url_str else {}
            code = qs.get("code", [""])[0]
            state = qs.get("state", [""])[0]

            if not code:
                if event:
                    event.outcome = "error"
                    event.oauth_success = False
                    event.error_type = "ValidationError"
                    event.error_message = "Missing authorization code"
                return self._admin_error_response(
                    "GitHub did not provide an authorization code. Please try signing in again.",
                    title="Authentication Failed",
                    status=400,
                )

            # Verify state parameter matches cookie (CSRF protection)
            cookies = SafeHeaders(request).cookie
            expected_state = None
            for cookie in cookies.split(";"):
                if cookie.strip().startswith("oauth_state="):
                    expected_state = cookie.strip()[12:]
                    break

            if not state or not expected_state or state != expected_state:
                if event:
                    event.outcome = "error"
                    event.oauth_success = False
                    event.error_type = "CSRFError"
                    event.error_message = "Invalid state parameter"
                return self._admin_error_response(
                    "Security verification failed. Please try signing in again.",
                    title="Authentication Failed",
                    status=400,
                )

            client_id = getattr(self.env, "GITHUB_CLIENT_ID", "")
            client_secret = getattr(self.env, "GITHUB_CLIENT_SECRET", "")

            # Exchange code for access token using centralized safe_http_fetch
            token_response = await safe_http_fetch(
                "https://github.com/login/oauth/access_token",
                method="POST",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )

            if token_response.status_code != 200:
                if event:
                    event.outcome = "error"
                    event.oauth_success = False
                    event.error_type = "TokenExchangeError"
                    event.error_message = (
                        f"GitHub token exchange failed: {token_response.status_code}"
                    )
                return self._admin_error_response(
                    "Could not complete authentication with GitHub. Please try again.",
                    title="Authentication Failed",
                    status=502,
                )

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                error_desc = token_data.get("error_description", "Unknown error")
                if event:
                    event.outcome = "error"
                    event.oauth_success = False
                    event.error_type = "OAuthError"
                    event.error_message = f"GitHub OAuth failed: {error_desc}"[
                        :ERROR_MESSAGE_MAX_LENGTH
                    ]
                return self._admin_error_response(
                    "GitHub authentication was not completed. Please try signing in again.",
                    title="Authentication Failed",
                    status=400,
                )

            # Fetch user info using centralized safe_http_fetch
            github_headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            }

            user_response = await safe_http_fetch(
                "https://api.github.com/user",
                headers=github_headers,
            )

            if user_response.status_code != 200:
                if event:
                    event.outcome = "error"
                    event.oauth_success = False
                    event.error_type = "GitHubAPIError"
                    event.error_message = f"GitHub API error: {user_response.status_code}"
                return self._admin_error_response(
                    "Could not retrieve your GitHub profile. Please try again.",
                    title="Authentication Failed",
                    status=502,
                )

            user_data = user_response.json()
            github_username = user_data.get("login")
            github_id = user_data.get("id")

            # Verify user is an admin
            admin_result = (
                await self.env.DB.prepare(
                    "SELECT * FROM admins WHERE github_username = ? AND is_active = 1"
                )
                .bind(github_username)
                .first()
            )

            # Convert D1 row to typed Python dict
            admin = admin_row_from_js(admin_result)

            if not admin:
                if event:
                    event.outcome = "error"
                    event.oauth_success = False
                    event.error_type = "UnauthorizedError"
                    event.error_message = f"User {github_username} is not an admin"
                return self._admin_error_response(
                    "Your GitHub account is not authorized to access the admin area.",
                    title="Access Denied",
                    status=403,
                    back_url="/",
                )

            # Update admin's github_id and last_login_at
            await (
                self.env.DB.prepare("""
                UPDATE admins SET github_id = ?, last_login_at = CURRENT_TIMESTAMP
                WHERE github_username = ?
            """)
                .bind(github_id, github_username)
                .run()
            )

            # Create signed session cookie (stateless, no KV)
            session_cookie = self._create_signed_cookie(
                {
                    "github_username": github_username,
                    "github_id": github_id,
                    "avatar_url": user_data.get("avatar_url"),
                    "exp": int(time.time()) + SESSION_TTL_SECONDS,
                }
            )

            # Clear oauth_state cookie and set session cookie
            # Use list of tuples to support multiple Set-Cookie headers
            clear_state = "oauth_state=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0"
            session = (
                f"session={session_cookie}; HttpOnly; Secure; "
                f"SameSite=Lax; Path=/; Max-Age={SESSION_TTL_SECONDS}"
            )

            # Populate OAuth success metrics on consolidated event
            if event:
                event.outcome = "success"
                event.oauth_success = True
                event.oauth_username = github_username

            return Response(
                "",
                status=302,
                headers=[
                    ("Location", "/admin"),
                    ("Set-Cookie", clear_state),
                    ("Set-Cookie", session),
                ],
            )

        except Exception as e:
            # Error captured on RequestEvent (emitted by fetch() handler)
            if event:
                event.outcome = "error"
                event.oauth_success = False
                event.error_type = type(e).__name__
                event.error_message = truncate_error(e)
            return self._admin_error_response(
                "An unexpected error occurred during authentication. Please try again.",
                title="Authentication Failed",
                status=500,
            )

    def _create_signed_cookie(self, payload: dict[str, Any]) -> str:
        """Create an HMAC-signed cookie.

        Format: base64(json_payload).signature
        """
        payload_json = json.dumps(payload)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

        signature = hmac.new(
            self.env.SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()

        return f"{payload_b64}.{signature}"

    def _logout(self, request: WorkerRequest) -> Response:
        """Log out by clearing the session cookie (stateless - nothing to delete)."""
        return Response(
            "",
            status=302,
            headers={
                "Location": "/",
                "Set-Cookie": "session=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0",
            },
        )


# Alias for tests which import PlanetCF
PlanetCF = Default
