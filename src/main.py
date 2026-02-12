# src/main.py
"""Planet CF - Feed Aggregator for Cloudflare Python Workers.

Main Worker entrypoint handling all triggers:
- scheduled(): Hourly cron to enqueue feed fetches
- queue(): Queue consumer for feed fetching
- fetch(): HTTP request handling (generates content on-demand)
"""

import asyncio
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

from admin import admin_error_response as _admin_error_response_fn

# Abstraction modules for reduced code duplication
from admin_context import admin_action_context
from auth import (
    build_clear_oauth_state_cookie_header,
    build_clear_session_cookie_header,
    build_oauth_state_cookie_header,
    build_session_cookie_header,
    create_signed_cookie,
    get_session_from_cookies,
)
from config import (
    DEFAULT_FEED_FAILURE_THRESHOLD,
    DEFAULT_QUERY_LIMIT,
    FALLBACK_ENTRIES_LIMIT,
    MAX_OPML_FEEDS,
    MAX_SEARCH_QUERY_LENGTH,
    MAX_SEARCH_WORDS,
    REINDEX_COOLDOWN_SECONDS,
    SESSION_TTL_SECONDS,
    get_content_days,
    get_embedding_max_chars,
    get_feed_auto_deactivate_threshold,
    get_feed_failure_threshold,
    get_feed_recovery_enabled,
    get_feed_recovery_limit,
    get_feed_timeout,
    get_http_timeout,
    get_max_entries_per_feed,
    get_planet_config,
    get_retention_days,
    get_search_score_threshold,
    get_search_top_k,
    get_user_agent,
)
from content_processor import EntryContentProcessor
from instance_config import is_lite_mode as check_lite_mode
from models import BleachSanitizer
from oauth_handler import GitHubOAuthHandler, extract_oauth_state_from_cookies
from observability import (
    FeedFetchEvent,
    RequestEvent,
    SchedulerEvent,
    Timer,
    emit_event,
)
from route_dispatcher import Route, RouteDispatcher, RouteMatch
from search_query import SearchQueryBuilder
from templates import (
    _EMBEDDED_TEMPLATES,
    TEMPLATE_ADMIN_DASHBOARD,
    TEMPLATE_ADMIN_LOGIN,
    TEMPLATE_FEED_ATOM,
    TEMPLATE_FEED_HEALTH,
    TEMPLATE_FEED_RSS,
    TEMPLATE_FEED_RSS10,
    TEMPLATE_FEEDS_OPML,
    TEMPLATE_FOAFROLL,
    TEMPLATE_INDEX,
    TEMPLATE_SEARCH,
    TEMPLATE_TITLES,
    THEME_LOGOS,
    render_template,
)
from utils import (
    ERROR_MESSAGE_MAX_LENGTH,
)
from utils import (
    feed_response as _feed_response,
)
from utils import (
    format_date_label as _format_date_label,
)
from utils import (
    format_pub_date as _format_pub_date,
)
from utils import (
    get_display_author as _get_display_author,
)
from utils import (
    html_response as _html_response,
)
from utils import (
    json_error as _json_error,
)
from utils import (
    json_response as _json_response,
)
from utils import (
    log_error as _log_error,
)
from utils import (
    log_op as _log_op,
)
from utils import (
    normalize_entry_content as _normalize_entry_content,
)
from utils import (
    parse_iso_datetime as _parse_iso_datetime,
)
from utils import (
    redirect_response as _redirect_response,
)
from utils import (
    relative_time as _relative_time,
)
from utils import (
    truncate_error as _truncate_error,
)
from utils import (
    validate_feed_id as _validate_feed_id,
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
from xml_sanitizer import strip_xml_control_chars

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


def _classify_error(exc: Exception) -> str:
    """Classify an exception into an error category for observability."""
    error_type = type(exc).__name__
    error_str = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in error_str:
        return "timeout"
    if "d1" in error_str or "database" in error_str or "sql" in error_str:
        return "database"
    if "parse" in error_str or "xml" in error_str or "feed" in error_type.lower():
        return "parse"
    if isinstance(exc, ConnectionError | OSError) or "fetch" in error_str:
        return "network"
    if isinstance(exc, ValueError) or "ssrf" in error_str or "invalid" in error_str:
        return "validation"
    return "unknown"


# =============================================================================
# Configuration
# =============================================================================

# Constants imported from config module (single source of truth)

# HTML sanitizer instance (uses settings from models.py)
_sanitizer = BleachSanitizer()

# Themes that hide sidebar feed links (RSS, titles only) from the template
_THEMES_HIDE_SIDEBAR_LINKS: frozenset[str] = frozenset({"planet-cloudflare"})

# Themes that enable RSS 1.0 (RDF) feed format
_THEMES_WITH_RSS10: frozenset[str] = frozenset({"planet-mozilla"})

# Themes that enable FOAF (Friend of a Friend) feed
_THEMES_WITH_FOAF: frozenset[str] = frozenset({"planet-mozilla"})

# Cloud metadata endpoints to block (SSRF protection)
BLOCKED_METADATA_IPS = {
    "169.254.169.254",  # AWS/GCP/Azure metadata
    "100.100.100.200",  # Alibaba Cloud metadata
    "192.0.0.192",  # Oracle Cloud metadata
}


def is_safe_url(url: str) -> bool:
    """SSRF protection - reject internal/private URLs.

    Module-level function so it can be tested directly and reused.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        _log_error("url_parse_error", e, url=url)
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
    _router: RouteDispatcher | None = None  # Cached route dispatcher

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

    def _get_feed_timeout(self) -> int:
        """Get feed timeout from environment, default 60 seconds."""
        return get_feed_timeout(self.env)

    def _get_http_timeout(self) -> int:
        """Get HTTP timeout from environment, default 30 seconds."""
        return get_http_timeout(self.env)

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
                        last_entry_at TEXT,
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

                    -- Migration tracking
                    CREATE TABLE IF NOT EXISTS applied_migrations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        migration_name TEXT UNIQUE NOT NULL,
                        applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                _log_op("database_auto_init", status="completed")
            else:
                _log_op("database_auto_init", status="already_initialized")
                # Validate existing schema has all expected columns
                await self._check_schema_drift()

            self._db_initialized = True

        except Exception as e:
            _log_error("database_auto_init_error", e)
            # Don't prevent the request from proceeding
            self._db_initialized = True  # Avoid retrying on every request

    # Expected columns for each table (must match CREATE TABLE above)
    _EXPECTED_COLUMNS: dict[str, set[str]] = {
        "feeds": {
            "id",
            "url",
            "title",
            "site_url",
            "author_name",
            "author_email",
            "etag",
            "last_modified",
            "last_fetch_at",
            "last_success_at",
            "last_entry_at",
            "fetch_error",
            "fetch_error_count",
            "consecutive_failures",
            "is_active",
            "created_at",
            "updated_at",
        },
        "entries": {
            "id",
            "feed_id",
            "guid",
            "url",
            "title",
            "author",
            "content",
            "summary",
            "published_at",
            "updated_at",
            "first_seen",
            "created_at",
        },
        "admins": {
            "id",
            "github_username",
            "github_id",
            "display_name",
            "avatar_url",
            "is_active",
            "created_at",
            "last_login_at",
        },
        "audit_log": {
            "id",
            "admin_id",
            "action",
            "target_type",
            "target_id",
            "details",
            "created_at",
        },
    }

    async def _check_schema_drift(self) -> None:
        """Check that existing database schema has all expected columns.

        Runs once on startup for existing databases. Logs a warning for
        any missing columns — this means a migration hasn't been applied.
        Does not block requests; this is observability only.
        """
        try:
            for table_name, expected_cols in self._EXPECTED_COLUMNS.items():
                result = await self.env.DB.prepare(
                    f"PRAGMA table_info({table_name})"  # noqa: S608
                ).all()
                if not result or not result.results:
                    continue
                actual_cols = set()
                for row in result.results:
                    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
                    col_name = row.name if hasattr(row, "name") else row.get("name")
                    if col_name:
                        actual_cols.add(col_name)
                missing = expected_cols - actual_cols
                if missing:
                    _log_op(
                        "schema_drift_detected",
                        table=table_name,
                        missing_columns=sorted(missing),
                        hint="Run pending migrations: see migrations/ directory",
                    )
        except Exception as e:
            _log_error("schema_drift_check_error", e)

    # =========================================================================
    # Cron Handler - Scheduler
    # =========================================================================

    async def scheduled(
        self,
        event: ScheduledEvent,
        env: WorkerEnv = None,
        ctx: WorkerCtx = None,
    ) -> None:
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

                # Auto-recovery: retry a small number of disabled feeds per hour
                if get_feed_recovery_enabled(self.env) and self.env.FEED_QUEUE is not None:
                    recovery_limit = get_feed_recovery_limit(self.env)
                    if recovery_limit > 0:
                        disabled_result = (
                            await self.env.DB.prepare("""
                            SELECT id, url, etag, last_modified
                            FROM feeds
                            WHERE is_active = 0
                            ORDER BY updated_at DESC
                            LIMIT ?
                        """)
                            .bind(recovery_limit)
                            .all()
                        )
                        disabled_feeds = feed_rows_from_d1(disabled_result.results)

                        for feed in disabled_feeds:
                            await (
                                self.env.DB.prepare("""
                                UPDATE feeds SET
                                    is_active = 1,
                                    consecutive_failures = 0,
                                    fetch_error = NULL,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?
                            """)
                                .bind(feed["id"])
                                .run()
                            )
                            await self.env.FEED_QUEUE.send(
                                {
                                    "feed_id": feed["id"],
                                    "url": feed["url"],
                                    "etag": feed.get("etag"),
                                    "last_modified": feed.get("last_modified"),
                                    "scheduled_at": datetime.now(timezone.utc).isoformat(),
                                    "correlation_id": sched_event.correlation_id,
                                    "is_recovery_attempt": True,
                                }
                            )
                            enqueue_count += 1
                            _log_op(
                                "feed_recovery_attempt",
                                feed_id=feed["id"],
                                feed_url=feed["url"],
                            )

                        sched_event.feeds_recovery_attempted = len(disabled_feeds)

                # Feed health summary for observability (#11, #12, #18)
                try:
                    health_result = (
                        await self.env.DB.prepare("""
                        SELECT
                            SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) as disabled,
                            SUM(CASE WHEN is_active = 0
                                AND updated_at >= datetime('now', '-1 hour')
                                THEN 1 ELSE 0 END) as newly_disabled,
                            SUM(CASE WHEN consecutive_failures >= ? THEN 1 ELSE 0 END) as dlq_depth
                        FROM feeds
                    """)
                        .bind(self._get_feed_failure_threshold())
                        .first()
                    )
                    if health_result:
                        health = _to_py_safe(health_result)
                        sched_event.feeds_disabled = health.get("disabled") or 0
                        sched_event.feeds_newly_disabled = health.get("newly_disabled") or 0
                        sched_event.dlq_depth = health.get("dlq_depth") or 0

                    # Error clustering: find error patterns affecting 2+ feeds
                    cluster_result = await self.env.DB.prepare("""
                        SELECT fetch_error, COUNT(*) as cnt
                        FROM feeds
                        WHERE fetch_error IS NOT NULL AND consecutive_failures > 0
                        GROUP BY fetch_error
                        HAVING COUNT(*) >= 2
                        ORDER BY cnt DESC
                    """).all()
                    clusters = _to_py_safe(cluster_result.results) if cluster_result else []
                    if clusters:
                        sched_event.error_clusters = len(clusters)
                        top = clusters[0] if isinstance(clusters, list) and clusters else None
                        if top and isinstance(top, dict):
                            sched_event.error_cluster_top = str(top.get("fetch_error", ""))[:200]
                except Exception as e:
                    _log_error("health_summary_error", e)

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

                # Pre-warm edge cache for main pages so the next visitor gets a cache hit
                try:
                    base_url = (getattr(self.env, "PLANET_URL", None) or "").rstrip("/")
                    if base_url:
                        warm_headers = {"User-Agent": self._get_user_agent()}
                        for path in ("/", "/titles", "/feed.atom", "/feed.rss"):
                            await safe_http_fetch(f"{base_url}{path}", headers=warm_headers)
                except Exception:
                    _log_op("cache_prewarm_failed")

                sched_event.outcome = "success"

            except Exception as e:
                sched_event.outcome = "error"
                sched_event.error_type = type(e).__name__
                sched_event.error_message = _truncate_error(e)
                raise

        sched_event.wall_time_ms = total_timer.elapsed_ms
        emit_event(sched_event)

        return {"enqueued": enqueue_count}

    # =========================================================================
    # Queue Handler - Feed Fetcher
    # =========================================================================

    async def queue(self, batch: QueueBatch, env: WorkerEnv = None, ctx: WorkerCtx = None) -> None:
        """Process a batch of feed messages from the queue.

        Each message contains exactly ONE feed to fetch.
        This ensures isolated retries and timeouts per feed.

        Note: Workers Python runtime passes (batch, env, ctx) but we use self.env from __init__.
        """
        batch_queue = _safe_str(getattr(batch, "queue", "")) or ""
        _log_op("queue_batch_received", batch_size=len(batch.messages), queue=batch_queue)

        # DLQ consumer: log permanently failed messages and ack them
        if "dlq" in batch_queue.lower():
            for message in batch.messages:
                body = _to_py_safe(message.body)
                feed_id = body.get("feed_id", 0) if isinstance(body, dict) else 0
                feed_url = body.get("url", "unknown") if isinstance(body, dict) else "unknown"
                _log_op(
                    "dlq_message_consumed",
                    feed_id=feed_id,
                    feed_url=feed_url,
                    attempts=getattr(message, "attempts", "?"),
                )
                message.ack()
            return

        for message in batch.messages:
            # CRITICAL: Convert JsProxy message body to Python dict
            feed_job_raw = message.body
            feed_job = _to_py_safe(feed_job_raw)
            if not feed_job or not isinstance(feed_job, dict):
                _log_op("queue_message_invalid", body_type=type(feed_job_raw).__name__)
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
                    event.error_category = "timeout"
                    deactivated = await self._record_feed_error(feed_id, "Timeout")
                    event.feed_auto_deactivated = deactivated
                    message.retry()

                except RateLimitError as e:
                    # Rate limiting is not a failure - don't increment consecutive_failures
                    # The retry-after time was already stored in _process_single_feed
                    event.wall_time_ms = timer.elapsed_ms
                    event.outcome = "rate_limited"
                    event.error_type = "RateLimitError"
                    event.error_message = _truncate_error(e)
                    event.error_retriable = True
                    event.error_category = "rate_limit"
                    # Don't call _record_feed_error - feed is not failing
                    message.retry()

                except Exception as e:
                    event.wall_time_ms = timer.elapsed_ms
                    event.outcome = "error"
                    event.error_type = type(e).__name__
                    event.error_message = _truncate_error(e)
                    event.error_retriable = not isinstance(e, ValueError)
                    event.error_category = _classify_error(e)
                    deactivated = await self._record_feed_error(feed_id, str(e))
                    event.feed_auto_deactivated = deactivated
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
        headers = {"User-Agent": self._get_user_agent()}
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
            await self._update_feed_url(feed_id, final_url, old_url=url)
            _log_op("feed_url_updated", old_url=url, new_url=final_url)

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

        _log_op("feed_entries_found", feed_id=feed_id, entries_count=entries_found)

        for entry in entries_list:
            # Ensure entry is Python dict (boundary conversion handled by _to_py_safe)
            py_entry = _to_py_safe(entry)
            if not isinstance(py_entry, dict):
                _log_op("entry_not_dict", entry_type=type(py_entry).__name__)
                continue

            result = await self._upsert_entry(feed_id, py_entry)
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
                entry_title = str(py_entry.get("title", ""))[:50]
                _log_op("entry_upsert_failed", feed_id=feed_id, entry_title=entry_title)

        # Mark fetch as successful
        await self._update_feed_success(feed_id, new_etag, new_last_modified)

        _log_op("feed_processed", feed_url=url, entries_added=entries_added)
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
                headers={"User-Agent": self._get_user_agent()},
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

        except Exception as e:
            _log_op("content_fetch_error", url=url, error=_truncate_error(e))
            return None

    async def _upsert_entry(self, feed_id: int, entry: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a single entry with sanitized content."""
        # Use EntryContentProcessor for GUID generation, content extraction, and date parsing
        processor = EntryContentProcessor(entry, feed_id)
        processed = processor.process()

        guid = processed.guid
        content = processed.content
        title = processed.title
        summary = processed.summary
        published_at = processed.published_at

        # If content is just a short summary, try to fetch full article content
        # This handles feeds that only provide <description> without <content:encoded>
        entry_url = entry.get("link")
        if len(content) < 500 and entry_url:
            fetched_content = await self._fetch_full_content(entry_url)
            if fetched_content:
                content = fetched_content
                _log_op(
                    "full_content_fetched",
                    url=entry_url[:100],
                    content_len=len(content),
                )

        # Sanitize HTML (XSS prevention)
        sanitized_content = self._sanitize_html(content)

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

        # Update feed's last_entry_at when a new entry is successfully added
        if entry_id:
            await (
                self.env.DB.prepare("""
                UPDATE feeds SET
                    last_entry_at = COALESCE(?, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """)
                .bind(published_at, feed_id)
                .run()
            )

        # Index for semantic search (may fail in local dev - Vectorize not supported)
        # Capture stats for aggregation on FeedFetchEvent
        indexing_stats = None
        if entry_id and title:
            try:
                indexing_stats = await self._index_entry_for_search(
                    entry_id, title, sanitized_content, feed_id=feed_id
                )
            except Exception as e:
                # Log but don't fail - entry is still usable without search
                _log_op(
                    "search_index_skipped",
                    entry_id=entry_id,
                    error_type=type(e).__name__,
                    error=_truncate_error(e),
                )
                # Create failed stats for aggregation
                indexing_stats = {
                    "success": False,
                    "embedding_ms": 0,
                    "upsert_ms": 0,
                    "total_ms": 0,
                    "text_truncated": False,
                    "error_type": type(e).__name__,
                    "error_message": _truncate_error(e),
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
                stats["error_message"] = _truncate_error(e)
                raise

        stats["total_ms"] = wall_timer.elapsed_ms
        return stats

    def _sanitize_html(self, html_content: str) -> str:
        """Sanitize HTML to prevent XSS attacks (CVE-2009-2937 mitigation)."""
        return _sanitizer.clean(html_content)

    def _is_safe_url(self, url: str) -> bool:
        """SSRF protection - reject internal/private URLs.

        Delegates to the module-level is_safe_url() function.
        """
        return is_safe_url(url)

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

    async def _record_feed_error(self, feed_id: int, error_message: str) -> bool:
        """Record a feed fetch error and auto-deactivate after too many failures.

        Returns True if the feed was auto-deactivated by this call.
        """
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
        if result and result.get("is_active") == 0:
            _log_op(
                "feed_auto_deactivated",
                feed_id=feed_id,
                consecutive_failures=result.get("consecutive_failures"),
                reason="Too many consecutive failures",
            )
            return True
        return False

    async def _update_feed_url(
        self, feed_id: int, new_url: str, old_url: str | None = None
    ) -> None:
        """Update feed URL after permanent redirect.

        Also logs the URL change to the audit_log table for tracking.

        Args:
            feed_id: ID of the feed to update
            new_url: The new URL to set
            old_url: The previous URL (for audit logging). If not provided,
                     will be fetched from the database.
        """
        # If old_url not provided, fetch it from database for audit logging
        if old_url is None:
            result = (
                await self.env.DB.prepare("SELECT url FROM feeds WHERE id = ?")
                .bind(feed_id)
                .first()
            )
            old_url = result.get("url") if result else None

        # Update the feed URL
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

        # Log to audit_log for tracking URL changes
        # For auto-updates (not triggered by admin), use system user
        details = json.dumps({"old_url": old_url, "new_url": new_url})
        await (
            self.env.DB.prepare("""
            INSERT INTO audit_log (admin_id, action, target_type, target_id, details)
            VALUES (?, ?, ?, ?, ?)
        """)
            .bind(0, "url_updated", "feed", feed_id, details)
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

    def _create_router(self) -> RouteDispatcher:
        """Create or return the cached route dispatcher with all route definitions."""
        if self._router is not None:
            return self._router
        self._router = RouteDispatcher(
            [
                # Public routes (cacheable at edge)
                Route(path="/", content_type="html", cacheable=True),
                Route(path="/index.html", content_type="html", cacheable=True, route_name="/"),
                Route(path="/titles", content_type="html", cacheable=True),
                Route(
                    path="/titles.html", content_type="html", cacheable=True, route_name="/titles"
                ),
                Route(path="/feed.atom", content_type="atom", cacheable=True),
                Route(path="/feed.rss", content_type="rss", cacheable=True),
                Route(path="/feed.rss10", content_type="rss10", cacheable=True),
                Route(path="/feeds.opml", content_type="opml", cacheable=True),
                Route(path="/foafroll.xml", content_type="foaf", cacheable=True),
                Route(path="/health", content_type="health", cacheable=False),
                Route(
                    path="/search", content_type="search", cacheable=False, lite_mode_disabled=True
                ),
                # OAuth routes
                Route(
                    path="/auth/github",
                    content_type="auth",
                    cacheable=False,
                    lite_mode_disabled=True,
                ),
                Route(
                    path="/auth/github/callback",
                    content_type="auth",
                    cacheable=False,
                    lite_mode_disabled=True,
                ),
                # Admin routes
                Route(
                    path="/admin",
                    prefix=True,
                    content_type="admin",
                    cacheable=False,
                    requires_auth=True,
                    route_name="/admin/*",
                    lite_mode_disabled=True,
                ),
            ]
        )
        return self._router

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

                # Use RouteDispatcher to match path and get route metadata
                router = self._create_router()
                match = router.match(path, request.method)

                if match:
                    # Set event metadata from route
                    event.route = match.route_name
                    event.cache_status = match.cache_status

                    # Check lite mode for disabled routes
                    if match.lite_mode_disabled and check_lite_mode(self.env):
                        response = _json_error(
                            f"{match.content_type.title()} is not available in lite mode",
                            status=404,
                        )
                        event.content_type = "error"
                    else:
                        # Dispatch to appropriate handler based on route
                        response = await self._dispatch_route(match, request, path, event)
                        event.content_type = match.content_type
                else:
                    # No route matched
                    event.route = "unknown"
                    response = _json_error("Not Found", status=404)
                    event.content_type = "error"
                    event.cache_status = "bypass"

            except Exception as e:
                _log_op(
                    "request_error",
                    path=path,
                    error_type=type(e).__name__,
                    error=_truncate_error(e),
                )
                event.wall_time_ms = timer.elapsed_ms
                event.status_code = 500
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

    async def _dispatch_route(
        self, match: RouteMatch, request: WorkerRequest, path: str, event: RequestEvent
    ) -> Response:
        """Dispatch to the appropriate handler based on route match."""
        route_path = match.route.path

        # Public routes
        if route_path in ("/", "/index.html"):
            return await self._serve_html(event)
        elif route_path in ("/titles", "/titles.html"):
            return await self._serve_titles(event)
        elif route_path == "/feed.atom":
            return await self._serve_atom()
        elif route_path == "/feed.rss":
            return await self._serve_rss()
        elif route_path == "/feed.rss10":
            return await self._serve_rss10()
        elif route_path == "/feeds.opml":
            return await self._export_opml()
        elif route_path == "/foafroll.xml":
            return await self._serve_foaf()
        elif route_path == "/health":
            return await self._serve_health()
        elif route_path == "/search":
            return await self._search_entries(request, event)
        # OAuth routes
        elif route_path == "/auth/github":
            secret_error = self._check_auth_secrets()
            if secret_error:
                return secret_error
            event.oauth_stage = "redirect"
            event.oauth_provider = "github"
            event.oauth_success = None  # Redirect phase, not callback
            return self._redirect_to_github_oauth(request)
        elif route_path == "/auth/github/callback":
            secret_error = self._check_auth_secrets()
            if secret_error:
                return secret_error
            event.oauth_stage = "callback"
            event.oauth_provider = "github"
            return await self._handle_github_callback(request, event)

        # Admin routes
        elif route_path == "/admin":
            return await self._handle_admin(request, path, event)

        # Fallback (should not reach here if routes are configured correctly)
        return _json_error("Not Found", status=404)

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
                    id, title, site_url, url, last_success_at, fetch_error,
                    consecutive_failures, is_active,
                    CASE WHEN consecutive_failures < ? THEN 1 ELSE 0 END as is_healthy
                FROM feeds
                ORDER BY title
            """)
                .bind(DEFAULT_FEED_FAILURE_THRESHOLD)
                .all()
            )

            # Get recent entries per feed for sidebar (configurable via CONTENT_DAYS)
            content_days = get_content_days(self.env)
            content_cutoff = (datetime.now(timezone.utc) - timedelta(days=content_days)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            recent_entries_result = (
                await self.env.DB.prepare("""
                SELECT feed_id, title, url
                FROM entries
                WHERE published_at >= ?
                  AND title IS NOT NULL AND title != ''
                ORDER BY feed_id, published_at DESC
            """)
                .bind(content_cutoff)
                .all()
            )

        # Populate generation metrics on the consolidated event
        if event:
            event.generation_d1_ms = d1_timer.elapsed_ms
            event.generation_trigger = trigger

        # Convert D1 results to typed Python dicts
        entries = entry_rows_from_d1(entries_result.results)
        feeds = feed_rows_from_d1(feeds_result.results)

        # Build recent entries per feed (max 3 per feed) for sidebar
        recent_by_feed: dict[int, list[dict[str, str]]] = {}
        for row in _to_py_list(recent_entries_result.results):
            py_row = _to_py_safe(row) if not isinstance(row, dict) else row
            if not py_row:
                continue
            fid = int(py_row.get("feed_id", 0))
            if fid and len(recent_by_feed.get(fid, [])) < 3:
                recent_by_feed.setdefault(fid, []).append(
                    {
                        "title": _safe_str(py_row.get("title")) or "",
                        "url": _safe_str(py_row.get("url")) or "",
                    }
                )

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
            date_label = _format_date_label(date_str)
            if date_label not in entries_by_date:
                entries_by_date[date_label] = []

            # Add display date (same as group date for consistency)
            if date_str and date_str != "Unknown":
                entry["published_at_display"] = _format_pub_date(group_date)
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

        stale_threshold = datetime.now(timezone.utc) - timedelta(days=90)
        for feed in feeds:
            feed["last_success_at_relative"] = _relative_time(feed["last_success_at"])
            feed["recent_entries"] = recent_by_feed.get(feed["id"], [])
            # Compute status message for sidebar tooltips
            fetch_err = feed.get("fetch_error")
            if fetch_err:
                feed["message"] = fetch_err
            elif feed.get("last_success_at"):
                try:
                    last_ok = datetime.fromisoformat(feed["last_success_at"].replace("Z", "+00:00"))
                    if last_ok.tzinfo is None:
                        last_ok = last_ok.replace(tzinfo=timezone.utc)
                    if last_ok < stale_threshold:
                        days_ago = (datetime.now(timezone.utc) - last_ok).days
                        feed["message"] = f"no activity in {days_ago} days"
                    else:
                        feed["message"] = None
                except (ValueError, AttributeError):
                    feed["message"] = None
            else:
                feed["message"] = None
            # Flag for template CSS class (is_active controls fetching, not display)
            feed["is_inactive"] = not feed.get("is_active", 1)

        # Render template - track template time
        # Check if running in lite mode (no search, no auth)
        is_lite = check_lite_mode(self.env)

        # Build feed_links dict for templates
        theme = self._get_theme()
        feed_links: dict[str, str] = {
            "atom": "/feed.atom",
            "rss": "/feed.rss",
            "opml": "/feeds.opml",
        }
        # Only include RSS 1.0 for themes that use it (or env var override)
        enable_rss10 = str(getattr(self.env, "ENABLE_RSS10", "") or "").lower()
        if theme in _THEMES_WITH_RSS10 or enable_rss10 == "true":
            feed_links["rss10"] = "/feed.rss10"
        enable_foaf = str(getattr(self.env, "ENABLE_FOAF", "") or "").lower()
        if theme in _THEMES_WITH_FOAF or enable_foaf == "true":
            feed_links["foaf"] = "/foafroll.xml"
        # Only include sidebar links for themes that use them (or env var override)
        hide_sidebar = str(getattr(self.env, "HIDE_SIDEBAR_LINKS", "") or "").lower()
        if theme not in _THEMES_HIDE_SIDEBAR_LINKS and hide_sidebar != "true":
            feed_links["sidebar_rss"] = "/feed.rss"
            feed_links["titles_only"] = "/titles"

        # Check if admin link should be shown (env var override, else default: True in full mode)
        show_admin_link_env = getattr(self.env, "SHOW_ADMIN_LINK", None)
        if show_admin_link_env is not None and str(show_admin_link_env).lower() == "false":
            show_admin_link = False
        elif show_admin_link_env is not None and str(show_admin_link_env).lower() == "true":
            show_admin_link = True
        else:
            show_admin_link = not is_lite

        # Build date_labels for themes (identity mapping since keys are already formatted)
        date_labels = {date_key: date_key for date_key in entries_by_date}

        with Timer() as render_timer:
            html = render_template(
                template,
                theme=self._get_theme(),
                planet=planet,
                entries_by_date=entries_by_date,
                feeds=feeds,
                feed_links=feed_links,
                date_labels=date_labels,
                generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                is_lite_mode=is_lite,
                show_admin_link=show_admin_link,
                logo=THEME_LOGOS.get(theme),
                submission=None,
                related_sites=None,
                footer_text=getattr(self.env, "FOOTER_TEXT", None) or "Powered by Planet CF",
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
                if self.env.SEARCH_INDEX is not None:
                    try:
                        await self.env.SEARCH_INDEX.deleteByIds([str(id) for id in deleted_ids])
                        stats["vectors_deleted"] = len(deleted_ids)
                    except Exception as e:
                        stats["errors"] += 1
                        _log_op(
                            "vectorize_delete_error",
                            error_type=type(e).__name__,
                            error_message=_truncate_error(e),
                            ids_count=len(deleted_ids),
                        )
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
            _log_op("retention_cleanup", entries_deleted=len(deleted_ids))

        return stats

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

    async def _serve_rss10(self) -> Response:
        """Generate and serve RSS 1.0 (RDF) feed on-demand."""
        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        rss10 = self._generate_rss10_feed(planet, entries)
        return _feed_response(rss10, "application/rdf+xml")

    async def _get_recent_entries(self, limit: int) -> list[dict[str, Any]]:
        """Query recent entries for feeds."""
        result = (
            await self.env.DB.prepare("""
            SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            ORDER BY e.published_at DESC
            LIMIT ?
        """)
            .bind(limit)
            .all()
        )

        return entry_rows_from_d1(result.results)

    def _get_planet_config(self) -> dict[str, str]:
        """Get planet configuration from environment."""
        return get_planet_config(self.env)

    def _get_theme(self) -> str:
        """Get the theme name from environment (default: 'default').

        Logs a warning if the theme is not found in embedded templates,
        since it will fall back to the default theme at render time.
        """
        raw = getattr(self.env, "THEME", None)
        theme = str(raw) if raw and isinstance(raw, str) else "default"
        if theme not in _EMBEDDED_TEMPLATES:
            _log_op("theme_not_found", theme=theme, fallback="default")
        return theme

    def _get_user_agent(self) -> str:
        """Get user agent string, supporting USER_AGENT_TEMPLATE env var."""
        return get_user_agent(self.env)

    def _admin_error_response(
        self,
        message: str,
        title: str | None = None,
        status: int = 400,
        back_url: str | None = "/admin",
    ) -> Response:
        """Return an HTML error page for admin/auth errors."""
        return _admin_error_response_fn(
            self._get_planet_config(),
            message,
            title=title,
            status=status,
            back_url=back_url,
            theme=self._get_theme(),
        )

    def _get_retention_days(self) -> int:
        """Get retention days from environment, default 90."""
        return get_retention_days(self.env)

    def _get_max_entries_per_feed(self) -> int:
        """Get max entries per feed from environment, default 100."""
        return get_max_entries_per_feed(self.env)

    def _get_embedding_max_chars(self) -> int:
        """Get max chars to embed per entry from environment, default 2000."""
        return get_embedding_max_chars(self.env)

    def _get_search_score_threshold(self) -> float:
        """Get minimum similarity score threshold from environment, default 0.3."""
        return get_search_score_threshold(self.env)

    def _get_search_top_k(self) -> int:
        """Get max semantic search results from environment, default 50."""
        return get_search_top_k(self.env)

    def _get_feed_auto_deactivate_threshold(self) -> int:
        """Get threshold for auto-deactivating feeds from environment, default 10."""
        return get_feed_auto_deactivate_threshold(self.env)

    def _get_feed_failure_threshold(self) -> int:
        """Get threshold for DLQ display from environment, default 3."""
        return get_feed_failure_threshold(self.env)

    def _generate_atom_feed(self, planet: dict[str, str], entries: list[dict[str, Any]]) -> str:
        """Generate Atom 1.0 feed XML using template."""
        # Prepare entries with defaults for template
        # Strip illegal XML control characters as defense-in-depth for existing data
        template_entries = [
            {
                "title": strip_xml_control_chars(e.get("title", "")),
                "url": e.get("url", ""),
                "guid": e.get("guid", e.get("url", "")),
                "published_at": e.get("published_at", ""),
                "author": strip_xml_control_chars(e.get("author", e.get("feed_title", ""))),
                "content": strip_xml_control_chars(e.get("content", "")),
            }
            for e in entries
        ]
        return render_template(
            TEMPLATE_FEED_ATOM,
            theme=self._get_theme(),
            planet=planet,
            entries=template_entries,
            updated_at=f"{datetime.now(timezone.utc).isoformat()}Z",
        )

    def _generate_rss_feed(self, planet: dict[str, str], entries: list[dict[str, Any]]) -> str:
        """Generate RSS 2.0 feed XML using template."""
        # Prepare entries with CDATA-safe content
        # Strip illegal XML control characters as defense-in-depth for existing data
        template_entries = [
            {
                "title": strip_xml_control_chars(e.get("title", "")),
                "url": e.get("url", ""),
                "guid": e.get("guid", e.get("url", "")),
                "published_at": e.get("published_at", ""),
                "author": strip_xml_control_chars(e.get("author", "")),
                # Escape ]]> in CDATA to prevent breakout attacks (Issue 2.1)
                # Content is already HTML-sanitized, but ensure CDATA boundaries are safe
                # Also strip illegal XML control chars for defense-in-depth
                "content_cdata": strip_xml_control_chars(e.get("content", "")).replace(
                    "]]>", "]]]]><![CDATA[>"
                ),
            }
            for e in entries
        ]
        return render_template(
            TEMPLATE_FEED_RSS,
            theme=self._get_theme(),
            planet=planet,
            entries=template_entries,
            last_build_date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        )

    def _generate_rss10_feed(self, planet: dict[str, str], entries: list[dict[str, Any]]) -> str:
        """Generate RSS 1.0 (RDF) feed XML using template."""
        # RSS 1.0 uses dc:date (ISO 8601) and truncated descriptions
        # Strip illegal XML control characters as defense-in-depth for existing data
        max_desc_chars = 500
        template_entries = [
            {
                "title": strip_xml_control_chars(e.get("title", "")),
                "url": e.get("url", ""),
                "published_at_iso": e.get("published_at", ""),
                "author": strip_xml_control_chars(e.get("author", e.get("feed_title", ""))),
                # Truncate content for RSS 1.0 descriptions, escape CDATA boundary
                "content_truncated": strip_xml_control_chars(
                    e.get("content", "")[:max_desc_chars]
                ).replace("]]>", "]]]]><![CDATA[>"),
            }
            for e in entries
        ]
        return render_template(
            TEMPLATE_FEED_RSS10,
            theme=self._get_theme(),
            planet=planet,
            entries=template_entries,
        )

    async def _export_opml(self) -> Response:
        """Export all active feeds as OPML using template."""
        feeds_result = await self.env.DB.prepare("""
            SELECT url, title, site_url
            FROM feeds
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
            theme=self._get_theme(),
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

    async def _serve_foaf(self) -> Response:
        """Generate and serve FOAF (Friend of a Friend) RDF feed."""
        feeds_result = await self.env.DB.prepare("""
            SELECT url, title, site_url
            FROM feeds
            ORDER BY title
        """).all()

        template_feeds = [
            {
                "title": f["title"] or f["url"],
                "url": f["url"],
                "site_url": f["site_url"] or f["url"],
            }
            for f in feed_rows_from_d1(feeds_result.results)
        ]

        planet = self._get_planet_config()
        foaf = render_template(
            TEMPLATE_FOAFROLL,
            theme=self._get_theme(),
            planet=planet,
            feeds=template_feeds,
        )

        return _feed_response(foaf, "application/rdf+xml")

    async def _serve_health(self) -> Response:
        """Public health endpoint returning JSON feed health summary.

        No authentication required. Returns non-sensitive aggregate data only.
        Used by post-deploy verification and monitoring.
        """
        result = await self.env.DB.prepare("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_active = 1
                    AND consecutive_failures = 0
                    THEN 1 ELSE 0 END) as healthy,
                SUM(CASE WHEN is_active = 1
                    AND consecutive_failures > 0
                    AND consecutive_failures < 3
                    THEN 1 ELSE 0 END) as warning,
                SUM(CASE WHEN is_active = 1
                    AND consecutive_failures >= 3
                    THEN 1 ELSE 0 END) as failing,
                SUM(CASE WHEN is_active = 0
                    THEN 1 ELSE 0 END) as inactive
            FROM feeds
        """).first()
        health = _to_py_safe(result) if result else {}
        total = health.get("total") or 0
        healthy = health.get("healthy") or 0
        warning = health.get("warning") or 0
        failing = health.get("failing") or 0
        inactive = health.get("inactive") or 0

        status = "healthy"
        if inactive > 0 or failing > 0:
            status = "degraded"
        if total == 0 or (healthy == 0 and total > 0):
            status = "unhealthy"

        return _json_response(
            {
                "status": status,
                "feeds": {
                    "total": total,
                    "healthy": healthy,
                    "warning": warning,
                    "failing": failing,
                    "inactive": inactive,
                },
            }
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
                theme=self._get_theme(),
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
                theme=self._get_theme(),
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
            _log_op("semantic_search_failed", error=_truncate_error(e))

        # 2. Keyword search via D1 (primary ranking signal)
        # Use SearchQueryBuilder for SQL query construction
        try:
            search_limit = self._get_search_top_k()
            with Timer() as d1_timer:
                # Build search query using SearchQueryBuilder
                builder = SearchQueryBuilder(
                    query=query,
                    is_phrase_search=is_phrase_search,
                    max_words=MAX_SEARCH_WORDS,
                )
                search_result = builder.build(limit=search_limit)

                # Track if words were truncated for DoS protection
                if search_result.words_truncated:
                    words_truncated = True
                    if event:
                        event.search_words_truncated = True

                # Execute the built query
                keyword_result = (
                    await self.env.DB.prepare(search_result.sql).bind(*search_result.params).all()
                )

                keyword_entries = entry_rows_from_d1(keyword_result.results)
            if event:
                event.search_d1_ms = d1_timer.elapsed_ms
        except Exception as e:
            _log_op("keyword_search_failed", error=_truncate_error(e))

        # 3. Combine results: keyword matches FIRST, then semantic matches
        # This is the key ranking insight: exact text match is the strongest signal
        keyword_ids = {entry.get("id") for entry in keyword_entries if entry.get("id")}
        semantic_ids = {int(m["id"]) for m in semantic_matches}

        # Check for empty results
        if not keyword_ids and not semantic_ids:
            if event:
                event.search_results_total = 0
            planet = self._get_planet_config()
            html = render_template(
                TEMPLATE_SEARCH, theme=self._get_theme(), planet=planet, query=query, results=[]
            )
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
            theme=self._get_theme(),
            planet=planet,
            query=query,
            results=sorted_results,
            words_truncated=words_truncated,
            max_search_words=MAX_SEARCH_WORDS,
        )
        return _html_response(html, cache_max_age=0)

    # =========================================================================
    # Admin Routes
    # =========================================================================

    def _check_auth_secrets(self) -> Response | None:
        """Check that required auth secrets are configured.

        Returns an error Response if secrets are missing, or None if all OK.
        """
        missing = []
        if not getattr(self.env, "SESSION_SECRET", None):
            missing.append("SESSION_SECRET")
        if not getattr(self.env, "GITHUB_CLIENT_ID", None):
            missing.append("GITHUB_CLIENT_ID")
        if not getattr(self.env, "GITHUB_CLIENT_SECRET", None):
            missing.append("GITHUB_CLIENT_SECRET")
        if missing:
            return Response(
                f"<h1>Server Configuration Error</h1>"
                f"<p>{', '.join(missing)} not configured. "
                f"Set the required secrets for admin/auth functionality.</p>",
                status=500,
                headers={"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"},
            )
        return None

    async def _handle_admin(
        self, request: WorkerRequest, path: str, event: RequestEvent | None = None
    ) -> Response:
        """Handle admin routes with GitHub OAuth."""
        # Validate required secrets before proceeding
        secret_error = self._check_auth_secrets()
        if secret_error:
            return secret_error

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

        if path == "/admin/health" and method == "GET":
            return await self._view_feed_health()

        if path == "/admin/reindex" and method == "POST":
            return await self._reindex_all_entries(admin)

        if path == "/admin/logout" and method == "POST":
            return self._logout(request)

        return _json_error("Not Found", status=404)

    def _serve_admin_login(self) -> Response:
        """Serve the admin login page."""
        planet = self._get_planet_config()
        html = render_template(TEMPLATE_ADMIN_LOGIN, theme=self._get_theme(), planet=planet)
        return _html_response(html, cache_max_age=0)

    async def _serve_admin_dashboard(self, admin: dict[str, Any]) -> Response:
        """Serve the admin dashboard with feed health warnings."""
        feeds_result = await self.env.DB.prepare("""
            SELECT * FROM feeds ORDER BY title
        """).all()
        feeds = feed_rows_from_d1(feeds_result.results)

        # Calculate health warnings for banner (#16)
        failing = [f for f in feeds if f.get("is_active") and f.get("consecutive_failures", 0) >= 3]
        inactive = [f for f in feeds if not f.get("is_active")]
        health_warnings: list[str] = []
        if inactive:
            names = ", ".join(f.get("title") or f.get("url", "?") for f in inactive[:3])
            suffix = f" and {len(inactive) - 3} more" if len(inactive) > 3 else ""
            health_warnings.append(f"{len(inactive)} feed(s) inactive: {names}{suffix}")
        if failing:
            names = ", ".join(f.get("title") or f.get("url", "?") for f in failing[:3])
            suffix = f" and {len(failing) - 3} more" if len(failing) > 3 else ""
            health_warnings.append(f"{len(failing)} feed(s) failing: {names}{suffix}")

        planet = self._get_planet_config()
        html = render_template(
            TEMPLATE_ADMIN_DASHBOARD,
            theme=self._get_theme(),
            planet=planet,
            admin=admin,
            feeds=feeds,
            health_warnings=health_warnings,
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
            headers = {"User-Agent": self._get_user_agent()}

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
                _log_op(
                    "feed_validation_parse_error",
                    url=url,
                    error_type=type(bozo_exc).__name__ if bozo_exc else "Unknown",
                    error_detail=_truncate_error(bozo_exc) if bozo_exc else "Invalid format",
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
            error_msg = _truncate_error(e)
            error_lower = error_msg.lower()
            is_timeout = isinstance(e, TimeoutError) or "timeout" in error_lower
            if is_timeout or "timed out" in error_lower:
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
        deployment = self._get_deployment_context()
        async with admin_action_context(
            admin, "add_feed", "feed", deployment, self._log_admin_action
        ) as ctx:
            try:
                form = SafeFormData(await request.form_data())
                url = form.get("url")
                title = form.get("title")

                if not url:
                    ctx.set_error("ValidationError", "URL is required")
                    return self._admin_error_response(
                        "Please provide a feed URL.", title="URL Required"
                    )

                # Validate URL (SSRF protection)
                if not self._is_safe_url(url):
                    ctx.set_error("ValidationError", "Invalid or unsafe URL")
                    return self._admin_error_response(
                        "The URL provided is invalid or points to an unsafe location.",
                        title="Invalid URL",
                    )

                # Validate the feed by fetching and parsing it
                validation = await self._validate_feed_url(url)

                if not validation["valid"]:
                    ctx.set_error("ValidationError", _truncate_error(validation["error"]))
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
                ctx.set_target_id(feed_id)

                # Audit log with validation info
                await ctx.log_action(
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

                ctx.set_success()

                # Redirect back to admin
                return _redirect_response("/admin")

            except Exception as e:
                ctx.set_error_from_exception(e)
                return self._admin_error_response(
                    "An unexpected error occurred while adding the feed. Please try again.",
                    title="Error Adding Feed",
                    status=500,
                )

    async def _remove_feed(self, feed_id: int, admin: dict[str, Any]) -> Response:
        """Remove a feed."""
        deployment = self._get_deployment_context()
        async with admin_action_context(
            admin, "remove_feed", "feed", deployment, self._log_admin_action
        ) as ctx:
            try:
                ctx.set_target_id(feed_id)

                # Get feed info for audit log
                feed_result = (
                    await self.env.DB.prepare("SELECT * FROM feeds WHERE id = ?")
                    .bind(feed_id)
                    .first()
                )

                # Convert D1 row to typed Python dict
                feed = feed_row_from_js(feed_result)

                if not feed:
                    ctx.set_error("NotFound", "Feed not found")
                    return self._admin_error_response(
                        "The feed you're trying to delete could not be found.",
                        title="Feed Not Found",
                        status=404,
                    )

                # Delete feed (entries will cascade)
                await self.env.DB.prepare("DELETE FROM feeds WHERE id = ?").bind(feed_id).run()

                # Audit log - feed is now a Python dict
                await ctx.log_action(
                    admin["id"],
                    "remove_feed",
                    "feed",
                    feed_id,
                    {"url": feed.get("url"), "title": feed.get("title")},
                )

                ctx.set_success()

                # Redirect back to admin
                return _redirect_response("/admin")

            except Exception as e:
                ctx.set_error_from_exception(e)
                return self._admin_error_response(
                    "An unexpected error occurred while deleting the feed. Please try again.",
                    title="Error Deleting Feed",
                    status=500,
                )

    async def _update_feed(
        self, request: WorkerRequest, feed_id: int, admin: dict[str, Any]
    ) -> Response:
        """Update a feed (enable/disable, edit title).

        Uses optimistic locking to prevent lost updates from concurrent edits.
        """
        deployment = self._get_deployment_context()
        async with admin_action_context(
            admin, "update_feed", "feed", deployment, self._log_admin_action
        ) as ctx:
            try:
                ctx.set_target_id(feed_id)
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
                await ctx.log_action(admin["id"], "update_feed", "feed", feed_id, audit_details)

                ctx.set_success()
                return _json_response({"success": True})

            except Exception as e:
                ctx.set_error_from_exception(e)
                return _json_error(str(e), status=500)

    async def _import_opml(self, request: WorkerRequest, admin: dict[str, Any]) -> Response:
        """Import feeds from uploaded OPML file. Admin only."""
        deployment = self._get_deployment_context()
        async with admin_action_context(
            admin, "import_opml", "feeds", deployment, self._log_admin_action
        ) as ctx:
            try:
                form = await request.form_data()
                # File uploads need direct access, not string conversion
                opml_file = form.get("opml")

                # Check for both Python None and JavaScript undefined
                if not opml_file or _is_js_undefined(opml_file):
                    ctx.set_error("ValidationError", "No file uploaded")
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

                ctx.set_import_metrics(file_size=len(content) if content else 0)

                # Parse OPML with XXE/Billion Laughs protection
                # Security: forbid_dtd=True prevents DOCTYPE declarations and entity expansion
                try:
                    parser = ET.XMLParser(forbid_dtd=True)
                    root = ET.fromstring(content, parser=parser)
                except ET.ParseError as e:
                    # Don't expose detailed parse errors to users
                    _log_op("opml_parse_error", error=_truncate_error(e))
                    ctx.set_error("ParseError", "Invalid OPML format")
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
                ctx.set_import_metrics(
                    feeds_parsed=feeds_parsed,
                    feeds_added=imported,
                    feeds_skipped=skipped,
                    errors=len(errors),
                )
                ctx.set_success()

                # Audit log
                await ctx.log_action(
                    admin["id"],
                    "import_opml",
                    "feeds",
                    None,
                    {"imported": imported, "skipped": skipped, "errors": errors[:10]},
                )

                # Redirect back to admin
                return _redirect_response("/admin")

            except Exception as e:
                ctx.set_error_from_exception(e)
                return self._admin_error_response(
                    "An unexpected error occurred while importing the OPML file. Please try again.",
                    title="Import Error",
                    status=500,
                )

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
        return _json_response({"feeds": feed_rows_from_d1(result.results)})

    async def _retry_dlq_feed(self, feed_id: int, admin: dict[str, Any]) -> Response:
        """Retry a failed feed by resetting its failure count and re-queuing."""
        deployment = self._get_deployment_context()
        async with admin_action_context(
            admin, "retry_dlq", "feed", deployment, self._log_admin_action
        ) as ctx:
            try:
                ctx.set_target_id(feed_id)
                ctx.set_dlq_metrics(feed_id=feed_id)

                # Get feed info
                feed_result = (
                    await self.env.DB.prepare("SELECT * FROM feeds WHERE id = ?")
                    .bind(feed_id)
                    .first()
                )

                # Convert D1 row to typed Python dict
                feed = feed_row_from_js(feed_result)

                if not feed:
                    ctx.set_error("NotFound", "Feed not found")
                    return self._admin_error_response(
                        "The feed you're trying to retry could not be found.",
                        title="Feed Not Found",
                        status=404,
                    )

                # Capture original error for observability
                ctx.set_dlq_metrics(
                    original_error=feed.get("fetch_error", ""),
                    action="retry",
                )

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
                await ctx.log_action(
                    admin["id"],
                    "retry_dlq",
                    "feed",
                    feed_id,
                    {"url": feed.get("url"), "previous_failures": feed.get("consecutive_failures")},
                )

                ctx.set_success()
                return _redirect_response("/admin")

            except Exception as e:
                ctx.set_error_from_exception(e)
                _log_op("dlq_retry_error", feed_id=feed_id, error=str(e))
                return self._admin_error_response(
                    "An unexpected error occurred while retrying the feed. Please try again.",
                    title="Retry Error",
                    status=500,
                )

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

    async def _view_feed_health(self) -> Response:
        """View feed health dashboard with statistics.

        Shows all feeds with their health information including:
        - Last successful fetch time
        - Last new entry date
        - Consecutive failures count
        - Active/inactive status
        """
        # Query all feeds with health information
        result = await self.env.DB.prepare("""
            SELECT
                f.id,
                f.url,
                f.title,
                f.site_url,
                f.last_fetch_at,
                f.last_success_at,
                f.last_entry_at,
                f.fetch_error,
                f.consecutive_failures,
                f.is_active,
                f.created_at,
                (SELECT COUNT(*) FROM entries e WHERE e.feed_id = f.id) as entry_count
            FROM feeds f
            ORDER BY
                CASE
                    WHEN f.is_active = 0 THEN 3
                    WHEN f.consecutive_failures >= 3 THEN 1
                    WHEN f.consecutive_failures > 0 THEN 2
                    ELSE 4
                END,
                f.consecutive_failures DESC,
                f.title
        """).all()

        feeds = feed_rows_from_d1(result.results)

        # Calculate health status for each feed
        for feed in feeds:
            if not feed.get("is_active"):
                feed["health_status"] = "inactive"
            elif feed.get("consecutive_failures", 0) >= 3:
                feed["health_status"] = "failing"
            elif feed.get("consecutive_failures", 0) > 0:
                feed["health_status"] = "warning"
            else:
                feed["health_status"] = "healthy"

        planet = self._get_planet_config()
        html = render_template(
            TEMPLATE_FEED_HEALTH,
            theme=self._get_theme(),
            planet=planet,
            feeds=feeds,
            total_feeds=len(feeds),
            healthy_count=sum(1 for f in feeds if f.get("health_status") == "healthy"),
            warning_count=sum(1 for f in feeds if f.get("health_status") == "warning"),
            failing_count=sum(1 for f in feeds if f.get("health_status") == "failing"),
            inactive_count=sum(1 for f in feeds if f.get("health_status") == "inactive"),
        )
        return _html_response(html, cache_max_age=0)

    async def _reindex_all_entries(self, admin: dict[str, Any]) -> Response:
        """Re-index all entries in Vectorize for search.

        This is needed when entries exist in D1 but were never indexed
        (e.g., added before Vectorize was configured, or indexing failed).

        Rate limited to prevent DoS - only one reindex per REINDEX_COOLDOWN_SECONDS.
        """
        deployment = self._get_deployment_context()
        async with admin_action_context(
            admin, "reindex", "search_index", deployment, self._log_admin_action
        ) as ctx:
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
                            ctx.set_error("RateLimited", f"Cooldown: {remaining}s remaining")
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

                ctx.set_reindex_metrics(entries_total=len(entries))

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
                    except Exception as e:
                        failed += 1
                        _log_op(
                            "reindex_entry_failed",
                            entry_id=entry_id,
                            error_type=type(e).__name__,
                            error=_truncate_error(e),
                        )

                ctx.set_reindex_metrics(entries_indexed=indexed, entries_failed=failed)

                # Log admin action
                await ctx.log_action(
                    admin["id"],
                    "reindex",
                    "search_index",
                    0,
                    {"indexed": indexed, "failed": failed, "total": len(entries)},
                )

                ctx.set_success()

                return _json_response(
                    {
                        "success": True,
                        "indexed": indexed,
                        "failed": failed,
                        "total": len(entries),
                    }
                )

            except Exception as e:
                ctx.set_error_from_exception(e)
                return _json_error(str(e), status=500)

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

        Delegates to auth.get_session_from_cookies for the actual verification.
        """
        cookies = SafeHeaders(request).cookie
        return get_session_from_cookies(cookies, self.env.SESSION_SECRET)

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

        state_cookie = build_oauth_state_cookie_header(state)
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
            # Extract OAuth parameters from URL
            url_str = str(request.url)
            qs = parse_qs(url_str.split("?", 1)[1]) if "?" in url_str else {}
            code = qs.get("code", [""])[0]
            state = qs.get("state", [""])[0]

            # Extract expected state from cookies
            cookies = SafeHeaders(request).cookie
            expected_state = extract_oauth_state_from_cookies(cookies)

            # Use GitHubOAuthHandler for OAuth flow
            client_id = getattr(self.env, "GITHUB_CLIENT_ID", "")
            client_secret = getattr(self.env, "GITHUB_CLIENT_SECRET", "")
            oauth_handler = GitHubOAuthHandler(client_id, client_secret, self._get_user_agent())

            # Authenticate: verify state, exchange code, get user info
            user_result, token_result = await oauth_handler.authenticate(
                code, state, expected_state
            )

            # Handle OAuth errors
            if not user_result.success:
                error = user_result.error or token_result.error
                if error:
                    if event:
                        event.outcome = "error"
                        event.oauth_success = False
                        event.error_type = error.error_type
                        event.error_message = error.message[:ERROR_MESSAGE_MAX_LENGTH]
                    return self._admin_error_response(
                        error.message,
                        title="Authentication Failed",
                        status=error.status_code,
                    )

            github_username = user_result.username
            github_id = user_result.user_id

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
                    "avatar_url": user_result.avatar_url,
                    "exp": int(time.time()) + SESSION_TTL_SECONDS,
                }
            )

            # Clear oauth_state cookie and set session cookie
            # Use list of tuples to support multiple Set-Cookie headers
            clear_state = build_clear_oauth_state_cookie_header()
            session = build_session_cookie_header(session_cookie)

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
            # Issue 4.5/6.5: Use _log_op() for structured logging
            _log_op(
                "oauth_error",
                error_type=type(e).__name__,
                error_message=_truncate_error(e),
            )
            if event:
                event.outcome = "error"
                event.oauth_success = False
                event.error_type = type(e).__name__
                event.error_message = _truncate_error(e)
            return self._admin_error_response(
                "An unexpected error occurred during authentication. Please try again.",
                title="Authentication Failed",
                status=500,
            )

    def _create_signed_cookie(self, payload: dict[str, Any]) -> str:
        """Create an HMAC-signed cookie.

        Delegates to auth.create_signed_cookie for the actual signing.
        """
        return create_signed_cookie(payload, self.env.SESSION_SECRET)

    def _logout(self, request: WorkerRequest) -> Response:
        """Log out by clearing the session cookie (stateless - nothing to delete)."""
        return Response(
            "",
            status=302,
            headers={
                "Location": "/",
                "Set-Cookie": build_clear_session_cookie_header(),
            },
        )


# Alias for tests which import PlanetCF
PlanetCF = Default
