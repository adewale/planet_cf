# src/admin.py
"""Admin functionality for Planet CF.

Helper functions for admin operations including feed management,
OPML import/export, and audit logging.
"""

import xml.etree.ElementTree as ET
from typing import Any

from config import MAX_OPML_FEEDS
from templates import TEMPLATE_ADMIN_ERROR, render_template
from utils import html_response, log_op, truncate_error

# =============================================================================
# Admin Response Helpers
# =============================================================================


def admin_error_response(
    planet: dict[str, str],
    message: str,
    title: str | None = None,
    status: int = 400,
    back_url: str | None = "/admin",
    theme: str = "default",
) -> Any:
    """Create an HTML error page for admin/auth errors.

    Args:
        planet: Planet configuration dict (name, description, link)
        message: Error message to display
        title: Optional error title
        status: HTTP status code
        back_url: URL for the back button
        theme: Theme name for template rendering

    Returns:
        Response with rendered error page.
    """
    html = render_template(
        TEMPLATE_ADMIN_ERROR,
        theme=theme,
        planet=planet,
        title=title,
        message=message,
        back_url=back_url,
    )
    return html_response(html, cache_max_age=0)


# =============================================================================
# OPML Parsing
# =============================================================================


def parse_opml(opml_content: str) -> tuple[list[dict[str, str]], list[str]]:
    """Parse OPML content and extract feed URLs.

    Uses secure XML parsing with DTD disabled to prevent XXE attacks.

    Args:
        opml_content: Raw OPML XML content

    Returns:
        Tuple of (feeds_list, errors_list).
        feeds_list contains dicts with 'url', 'title', 'site_url'.
        errors_list contains any parsing warnings.
    """
    feeds = []
    errors = []

    try:
        # Security: forbid_dtd=True prevents DOCTYPE declarations and entity expansion
        # S314: We use forbid_dtd=True to mitigate XXE attacks, same as defusedxml
        parser = ET.XMLParser(forbid_dtd=True)  # noqa: S314
        root = ET.fromstring(opml_content, parser=parser)  # noqa: S314
    except ET.ParseError as e:
        log_op("opml_parse_error", error=truncate_error(e))
        return [], [f"Invalid OPML format: {truncate_error(e)}"]

    # Find all outline elements with xmlUrl (RSS/Atom feeds)
    for outline in root.iter("outline"):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            feed = {
                "url": xml_url,
                "title": outline.get("title") or outline.get("text") or "",
                "site_url": outline.get("htmlUrl") or "",
            }
            feeds.append(feed)

    if len(feeds) > MAX_OPML_FEEDS:
        errors.append(f"OPML contains {len(feeds)} feeds, limited to {MAX_OPML_FEEDS}")
        feeds = feeds[:MAX_OPML_FEEDS]

    return feeds, errors


def validate_opml_feeds(
    feeds: list[dict[str, str]],
    existing_urls: set[str],
) -> tuple[list[dict[str, str]], list[str]]:
    """Filter OPML feeds, removing duplicates.

    Args:
        feeds: List of feed dicts from parse_opml
        existing_urls: Set of URLs already in the database

    Returns:
        Tuple of (new_feeds, skipped_messages).
    """
    new_feeds = []
    skipped = []

    for feed in feeds:
        url = feed["url"]
        if url in existing_urls:
            skipped.append(f"Already exists: {url}")
        else:
            new_feeds.append(feed)
            existing_urls.add(url)  # Prevent duplicates within import

    return new_feeds, skipped


# =============================================================================
# Feed Validation Results
# =============================================================================


def format_feed_validation_result(
    valid: bool,
    title: str | None = None,
    site_url: str | None = None,
    entry_count: int = 0,
    final_url: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Format a feed validation result.

    Args:
        valid: Whether the feed is valid
        title: Extracted feed title
        site_url: Extracted site URL
        entry_count: Number of entries found
        final_url: Final URL after redirects (if different)
        error: Error message if invalid

    Returns:
        Dict with validation results.
    """
    return {
        "valid": valid,
        "title": title,
        "site_url": site_url,
        "entry_count": entry_count,
        "final_url": final_url,
        "error": error,
    }


# =============================================================================
# Audit Logging
# =============================================================================


def log_admin_action(
    action: str,
    admin_username: str,
    target_type: str | None = None,
    target_id: int | str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Log an admin action for operational visibility.

    This logs to the structured log (not the audit_log table).
    The audit_log table insert should be done separately with database access.

    Args:
        action: Action type (e.g., "add_feed", "remove_feed")
        admin_username: Username of the admin performing the action
        target_type: Type of target (e.g., "feed", "entry")
        target_id: ID of the target
        details: Additional details about the action
    """
    log_op(
        "admin_action",
        action=action,
        admin=admin_username,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
