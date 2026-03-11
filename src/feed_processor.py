# src/feed_processor.py
"""Feed processing functions for Planet CF.

Functions for fetching, parsing, upserting, and indexing RSS/Atom feed entries.
These functions take explicit parameters (env, db, etc.) instead of using `self`,
making them testable and reusable outside the Worker class.

Extracted from main.py's _process_single_feed, _upsert_entry, _index_entry_for_search,
_sanitize_html, _is_safe_url, and related helper methods.
"""

import ipaddress
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser

from config import (
    get_embedding_max_chars,
    get_http_timeout,
    get_user_agent,
)
from content_processor import EntryContentProcessor
from models import BleachSanitizer
from observability import FeedFetchEvent, Timer
from utils import log_error, log_op, truncate_error
from wrappers import (
    SafeFeedInfo,
    _safe_str,
    _to_py_list,
    _to_py_safe,
    entry_bind_values,
    feed_bind_values,
    safe_http_fetch,
)

__all__ = [
    "RateLimitError",
    "index_entry_for_search",
    "is_safe_url",
    "process_single_feed",
    "record_feed_error",
    "sanitize_html",
    "set_feed_retry_after",
    "update_feed_metadata",
    "update_feed_success",
    "update_feed_url",
    "upsert_entry",
]

# =============================================================================
# Constants
# =============================================================================

# Cloud metadata endpoints to block (SSRF protection)
BLOCKED_METADATA_IPS = {
    "169.254.169.254",  # AWS/GCP/Azure metadata
    "100.100.100.200",  # Alibaba Cloud metadata
    "192.0.0.192",  # Oracle Cloud metadata
}

# HTML sanitizer instance (uses settings from models.py)
_sanitizer = BleachSanitizer()


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
# URL Validation (SSRF Protection)
# =============================================================================


def is_safe_url(url: str) -> bool:
    """SSRF protection - reject internal/private URLs.

    Module-level function so it can be tested directly and reused.
    """
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


# =============================================================================
# HTML Sanitization
# =============================================================================


def sanitize_html(html_content: str) -> str:
    """Sanitize HTML to prevent XSS attacks (CVE-2009-2937 mitigation)."""
    return _sanitizer.clean(html_content)


# =============================================================================
# Feed Database Helpers
# =============================================================================


async def update_feed_success(
    db, feed_id: int, etag: str | None, last_modified: str | None
) -> None:
    """Mark feed fetch as successful.

    Args:
        db: D1 database binding (env.DB).
        feed_id: ID of the feed to update.
        etag: ETag header value from the response.
        last_modified: Last-Modified header value from the response.
    """
    await (
        db.prepare("""
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


async def record_feed_error(
    db, feed_id: int, error_message: str, auto_deactivate_threshold: int
) -> bool:
    """Record a feed fetch error and auto-deactivate after too many failures.

    Args:
        db: D1 database binding (env.DB).
        feed_id: ID of the feed to update.
        error_message: Error message to store.
        auto_deactivate_threshold: Number of consecutive failures before auto-deactivation.

    Returns:
        True if the feed was auto-deactivated by this call.
    """
    # Issue 9.4: Auto-deactivate feeds after configurable consecutive failures
    # Note: Check consecutive_failures + 1 (the NEW value after increment) against threshold
    # to avoid race condition where the CASE sees the old value before increment
    result_raw = await (
        db.prepare("""
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
        .bind(error_message[:500], auto_deactivate_threshold, feed_id)
        .first()
    )
    # Convert JsProxy to Python dict
    result = _to_py_safe(result_raw)
    if result and result.get("is_active") == 0:
        log_op(
            "feed_auto_deactivated",
            feed_id=feed_id,
            consecutive_failures=result.get("consecutive_failures"),
            reason="Too many consecutive failures",
        )
        return True
    return False


async def update_feed_url(db, feed_id: int, new_url: str, old_url: str | None = None) -> None:
    """Update feed URL after permanent redirect.

    Also logs the URL change to the audit_log table for tracking.

    Args:
        db: D1 database binding (env.DB).
        feed_id: ID of the feed to update.
        new_url: The new URL to set.
        old_url: The previous URL (for audit logging). If not provided,
                 will be fetched from the database.
    """
    # If old_url not provided, fetch it from database for audit logging
    if old_url is None:
        result = await db.prepare("SELECT url FROM feeds WHERE id = ?").bind(feed_id).first()
        old_url = result.get("url") if result else None

    # Update the feed URL
    await (
        db.prepare("""
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
        db.prepare("""
        INSERT INTO audit_log (admin_id, action, target_type, target_id, details)
        VALUES (?, ?, ?, ?, ?)
    """)
        .bind(0, "url_updated", "feed", feed_id, details)
        .run()
    )


async def set_feed_retry_after(db, feed_id: int, retry_after: str) -> None:
    """Store Retry-After time for a feed (good netizen behavior).

    The retry_after value can be:
    - A number of seconds (e.g., "3600")
    - An HTTP date (e.g., "Wed, 21 Oct 2015 07:28:00 GMT")

    Args:
        db: D1 database binding (env.DB).
        feed_id: ID of the feed to update.
        retry_after: Retry-After header value.
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
        db.prepare("""
        UPDATE feeds SET
            fetch_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """)
        .bind(f"Rate limited until {retry_until}", feed_id)
        .run()
    )


async def update_feed_metadata(
    db, feed_id: int, feed_info, etag: str | None, last_modified: str | None
) -> None:
    """Update feed title and other metadata from feed content.

    Args:
        db: D1 database binding (env.DB).
        feed_id: ID of the feed to update.
        feed_info: feedparser's FeedParserDict with feed metadata.
        etag: ETag header value from the response.
        last_modified: Last-Modified header value from the response.
    """
    # Use SafeFeedInfo wrapper for clean JS->Python boundary handling
    info = SafeFeedInfo(feed_info)

    await (
        db.prepare("""
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


# =============================================================================
# Search Indexing
# =============================================================================


async def index_entry_for_search(
    ai,
    search_index,
    entry_id: int,
    title: str,
    content: str,
    embedding_max_chars: int,
    feed_id: int = 0,
    trigger: str = "feed_fetch",
) -> dict[str, Any]:
    """Generate embedding and store in Vectorize for semantic search.

    Args:
        ai: Workers AI binding (env.AI).
        search_index: Vectorize index binding (env.SEARCH_INDEX).
        entry_id: Database ID of the entry.
        title: Entry title.
        content: Entry content (HTML sanitized).
        embedding_max_chars: Max characters to include in embedding text.
        feed_id: Feed ID for observability (not used in event - aggregated by caller).
        trigger: What triggered indexing - "feed_fetch", "reindex", or "manual".

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
    stats: dict[str, object] = {
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
            combined_text = f"{title}\n\n{content[:embedding_max_chars]}"
            stats["text_truncated"] = len(content) > embedding_max_chars

            # Generate embedding using Workers AI with cls pooling for accuracy
            with Timer() as embedding_timer:
                embedding_result = await ai.run(
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
                await search_index.upsert(
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


# =============================================================================
# Core Feed Processing
# =============================================================================


async def upsert_entry(
    env, feed_id: int, entry: dict[str, Any], embedding_max_chars: int
) -> dict[str, Any]:
    """Insert or update a single entry with sanitized content.

    Args:
        env: Worker environment bindings (needs env.DB, env.AI, env.SEARCH_INDEX).
        feed_id: ID of the feed this entry belongs to.
        entry: Parsed entry dict from feedparser.
        embedding_max_chars: Max characters to include in embedding text.

    Returns:
        dict with entry_id and optional indexing_stats.
    """
    # Use EntryContentProcessor for GUID generation, content extraction, and date parsing
    processor = EntryContentProcessor(entry, feed_id)
    processed = processor.process()

    guid = processed.guid
    content = processed.content
    title = processed.title
    summary = processed.summary
    published_at = processed.published_at

    # Sanitize HTML (XSS prevention)
    sanitized_content = sanitize_html(content)

    # Upsert to D1 - use _safe_str to convert any JsProxy/undefined to Python
    # first_seen is set on INSERT only - preserved on UPDATE to prevent spam attacks
    # where feeds retroactively add old entries that would appear as new
    result_raw = (
        await env.DB.prepare("""
        INSERT INTO entries (
            feed_id, guid, url, title, author, content, summary,
            published_at, first_seen
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
        ON CONFLICT(feed_id, guid) DO UPDATE SET
            title = excluded.title,
            content = excluded.content,
            summary = excluded.summary,
            author = excluded.author,
            url = excluded.url,
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
            env.DB.prepare("""
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
            indexing_stats = await index_entry_for_search(
                env.AI,
                env.SEARCH_INDEX,
                entry_id,
                title,
                sanitized_content,
                embedding_max_chars=embedding_max_chars,
                feed_id=feed_id,
            )
        except Exception as e:
            # Log but don't fail - entry is still usable without search
            log_op(
                "search_index_skipped",
                entry_id=entry_id,
                error_type=type(e).__name__,
                error=truncate_error(e),
            )
            # Create failed stats for aggregation
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


async def process_single_feed(
    env, job: dict, event: FeedFetchEvent | None = None
) -> dict[str, Any]:
    """Fetch, parse, and store a single feed.

    This function should complete within FEED_TIMEOUT_SECONDS.

    Args:
        env: Worker environment bindings (needs env.DB, env.AI, env.SEARCH_INDEX).
        job: Feed job dict with feed_id, url, etag, last_modified.
        event: Optional FeedFetchEvent to populate with details.

    Returns:
        dict with status, entries_added, and entries_found.
    """
    feed_id = job["feed_id"]
    url = job["url"]
    etag = job.get("etag")
    last_modified = job.get("last_modified")

    # SSRF protection - validate URL before fetching
    if not is_safe_url(url):
        raise ValueError(f"URL failed SSRF validation: {url}")

    # Build conditional request headers (good netizen behavior)
    user_agent = get_user_agent(env)
    headers = {"User-Agent": user_agent}
    if etag:
        headers["If-None-Match"] = str(etag)
    if last_modified:
        headers["If-Modified-Since"] = str(last_modified)

    # Fetch using boundary-layer safe_http_fetch
    http_timeout = get_http_timeout(env)
    with Timer() as http_timer:
        http_response = await safe_http_fetch(url, headers=headers, timeout_seconds=http_timeout)

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
    if final_url != url and not is_safe_url(final_url):
        raise ValueError(f"Redirect target failed SSRF validation: {final_url}")

    # Handle 429/503 with Retry-After (good netizen behavior)
    # Use RateLimitError to avoid incrementing consecutive_failures
    if status_code in (429, 503):
        retry_after = response_headers.get("retry-after")
        error_msg = f"Rate limited (HTTP {status_code})"
        if retry_after:
            error_msg += f", retry after {retry_after}"
            await set_feed_retry_after(env.DB, feed_id, retry_after)
        raise RateLimitError(error_msg, retry_after)

    # Handle 304 Not Modified - feed hasn't changed
    if status_code == 304:
        await update_feed_success(env.DB, feed_id, etag, last_modified)
        return {"status": "not_modified", "entries_added": 0, "entries_found": 0}

    # Handle permanent redirects (301, 308) - update stored URL
    if final_url != url:
        # Note: We can't distinguish redirect types with fetch API
        # Treat any redirect as potentially permanent
        await update_feed_url(env.DB, feed_id, final_url, old_url=url)
        log_op("feed_url_updated", old_url=url, new_url=final_url)

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
    await update_feed_metadata(env.DB, feed_id, feed_data.feed, new_etag, new_last_modified)

    # Process and store entries (boundary conversion handled by _to_py_list)
    entries_list = _to_py_list(feed_data.entries)

    entries_added = 0
    entries_found = len(entries_list)
    if event:
        event.entries_found = entries_found

    log_op("feed_entries_found", feed_id=feed_id, entries_count=entries_found)

    embedding_max_chars = get_embedding_max_chars(env)

    for entry in entries_list:
        # Ensure entry is Python dict (boundary conversion handled by _to_py_safe)
        py_entry = _to_py_safe(entry)
        if not isinstance(py_entry, dict):
            log_op("entry_not_dict", entry_type=type(py_entry).__name__)
            continue

        result = await upsert_entry(env, feed_id, py_entry, embedding_max_chars)
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
            log_op("entry_upsert_failed", feed_id=feed_id, entry_title=entry_title)

    # Mark fetch as successful
    await update_feed_success(env.DB, feed_id, new_etag, new_last_modified)

    log_op("feed_processed", feed_url=url, entries_added=entries_added)
    return {"status": "ok", "entries_added": entries_added, "entries_found": entries_found}
