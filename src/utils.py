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


def log_op(event_type: str, **kwargs: LogKwargs) -> None:
    """Log an operational event as structured JSON.

    Unlike wide events (FeedFetchEvent, etc.), these are simpler operational
    logs for debugging and monitoring internal operations.
    """
    event = {
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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


def html_response(content: str, cache_max_age: int = 3600) -> Response:
    """Create an HTML response with caching and security headers."""
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
            "Cache-Control": f"public, max-age={cache_max_age}, stale-while-revalidate=60",
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
