# src/utils.py
"""Utility functions for Planet CF.

Standalone helper functions for logging, validation, response building,
and content processing. These have no dependencies on the Worker class.
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs

from workers import Response

# =============================================================================
# Type Aliases
# =============================================================================

#: Logging kwargs - intentionally accepts any JSON-serializable values
LogKwargs = Any

# =============================================================================
# Constants
# =============================================================================

# Standardized error message truncation length
ERROR_MESSAGE_MAX_LENGTH = 200

# =============================================================================
# Structured Logging
# =============================================================================

# Configure module logger for structured operational logs
# Use "src.main" name for backward compatibility with tests
_logger = logging.getLogger("src.main")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    # Note: propagate defaults to True, needed for test caplog capture


def get_iso_timestamp() -> str:
    """Get current UTC time as ISO string with Z suffix (RFC3339).

    Centralizes the datetime→ISO string conversion used throughout the codebase.
    """
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def log_op(event_type: str, **kwargs: LogKwargs) -> None:
    """Log an operational event as structured JSON.

    Unlike wide events (FeedFetchEvent, etc.), these are simpler operational
    logs for debugging and monitoring internal operations.
    """
    event = {
        "event_type": event_type,
        "timestamp": get_iso_timestamp(),
        **kwargs,
    }
    _logger.info(json.dumps(event))


def truncate_error(error: str | Exception, max_length: int = ERROR_MESSAGE_MAX_LENGTH) -> str:
    """Truncate error message with indicator if needed.

    Unlike plain slicing, this adds an ellipsis indicator when truncation occurs,
    making it clear to readers that the message was cut off.
    """
    error_str = str(error)
    if len(error_str) <= max_length:
        return error_str
    return error_str[: max_length - 3] + "..."


def log_error(event_type: str, exception: Exception, **kwargs: LogKwargs) -> None:
    """Log an error event with standardized exception formatting.

    Uses logger.error() level for error events, making them easily
    distinguishable from info-level operational logs.
    """
    event = {
        "event_type": event_type,
        "timestamp": get_iso_timestamp(),
        "error_type": type(exception).__name__,
        "error": truncate_error(exception),
        **kwargs,
    }
    _logger.error(json.dumps(event))


# =============================================================================
# Validation Helpers
# =============================================================================


def get_display_author(author: str | None, feed_title: str | None) -> str:
    """Compute display author for an entry, filtering out email addresses.

    If author is empty or contains '@' (likely an email), use feed_title instead.
    """
    if author and "@" not in author:
        return author
    return feed_title or "Unknown"


def validate_feed_id(feed_id: str) -> int | None:
    """Validate and convert a feed ID from URL path to integer.

    Returns the integer ID if valid, None otherwise.
    Prevents path traversal and invalid ID attacks.
    """
    if not feed_id:
        return None
    if not feed_id.isdigit():
        return None
    try:
        id_int = int(feed_id)
        if id_int <= 0:
            return None
        return id_int
    except (ValueError, OverflowError):
        return None


def xml_escape(text: str) -> str:
    """Escape XML special characters for safe embedding in XML content."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def parse_query_params(url_str: str) -> dict[str, list[str]]:
    """Extract query parameters from a URL string.

    Returns a dict where each key maps to a list of values.
    """
    if "?" not in url_str:
        return {}
    query_string = url_str.split("?", 1)[1]
    return parse_qs(query_string)


# =============================================================================
# Content Processing
# =============================================================================


def normalize_entry_content(content: str, title: str | None) -> str:
    """Normalize entry content for display by removing duplicate title headings.

    Many feeds include the post title as an <h1> or <h2> at the start of the
    content body. Since our template already displays the title, this creates
    visual duplication. This function strips the leading heading if it matches
    the entry title.
    """
    if not content or not title:
        return content

    title_normalized = title.strip().lower()
    search_content = content[:1000] if len(content) > 1000 else content

    pattern = (
        r"^(\s*(?:[A-Za-z]+\s+\d{1,2},?\s+\d{4}\s*)?(?:/\s*\d+\s*min\s*read\s*)?\s*)"
        r"<(h[12])(?:\s[^>]*)?>\s*"
        r"(?:(<a[^>]*>)\s*)?"
        r"([^<]+?)"
        r"\s*(?:(</a>)\s*)?"
        r"</\2>"
    )

    match = re.match(pattern, search_content, re.IGNORECASE)

    if match:
        heading_text = match.group(4).strip().lower()
        if heading_text == title_normalized:
            return content[match.end() :].lstrip()

    return content


# =============================================================================
# Response Builders
# =============================================================================

# Security headers applied to all HTML responses
SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

# Default Content Security Policy
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src https: data:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def _build_cache_control(max_age: int) -> str:
    """Build Cache-Control header value with stale-while-revalidate."""
    return f"public, max-age={max_age}, stale-while-revalidate=60"


def html_response(content: str, cache_max_age: int = 3600) -> Response:
    """Create an HTML response with caching and security headers."""
    return Response(
        content,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": _build_cache_control(cache_max_age),
            "Content-Security-Policy": DEFAULT_CSP,
            **SECURITY_HEADERS,
        },
    )


def json_response(data: dict, status: int = 200) -> Response:
    """Create a JSON response."""
    return Response(
        json.dumps(data),
        status=status,
        headers={"Content-Type": "application/json"},
    )


def json_error(message: str, status: int = 400) -> Response:
    """Create a JSON error response."""
    return json_response({"error": message}, status=status)


def redirect_response(location: str) -> Response:
    """Create a redirect response."""
    return Response("", status=302, headers={"Location": location})


def feed_response(content: str, content_type: str, cache_max_age: int = 3600) -> Response:
    """Create a feed response (Atom/RSS/OPML) with caching headers."""
    return Response(
        content,
        headers={
            "Content-Type": f"{content_type}; charset=utf-8",
            "Cache-Control": _build_cache_control(cache_max_age),
        },
    )


# =============================================================================
# Datetime Helpers
# =============================================================================


def parse_iso_datetime(iso_string: str | None) -> datetime | None:
    """Parse an ISO datetime string to a timezone-aware datetime.

    Handles various ISO formats:
    - With Z suffix: "2026-01-17T12:00:00Z"
    - With offset: "2026-01-17T12:00:00+00:00"
    - Naive (no timezone): "2026-01-17T12:00:00" (assumes UTC)
    """
    if not iso_string:
        return None
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, AttributeError):
        return None


def format_datetime(iso_string: str | None) -> str:
    """Format ISO datetime string for display (e.g., 'January 15, 2026 at 02:30 PM')."""
    dt = parse_iso_datetime(iso_string)
    if dt is None:
        return iso_string or ""
    return dt.strftime("%B %d, %Y at %I:%M %p")


def format_pub_date(iso_string: str | None) -> str:
    """Format publication date concisely (e.g., 'Jun 2013' or 'Jan 15').

    If same year as now, shows "Mon Day" (e.g., "Jun 15").
    Otherwise shows "Mon Year" (e.g., "Jun 2013").
    """
    dt = parse_iso_datetime(iso_string)
    if dt is None:
        return ""
    now = datetime.now(UTC)
    if dt.year == now.year:
        return dt.strftime("%b %d")
    return dt.strftime("%b %Y")


def relative_time(iso_string: str | None) -> str:
    """Convert ISO datetime to relative time (e.g., '2 hours ago')."""
    dt = parse_iso_datetime(iso_string)
    if dt is None:
        return "never" if not iso_string else "unknown"
    now = datetime.now(UTC)
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


def format_date_label(date_str: str) -> str:
    """Convert YYYY-MM-DD to absolute date like 'August 25, 2025'.

    Always shows the actual date rather than relative labels like 'Today'.
    This is clearer when there are gaps between posts.
    """
    try:
        entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        return entry_date.strftime("%B %d, %Y")
    except (ValueError, AttributeError):
        return date_str
