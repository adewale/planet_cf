# src/admin.py
"""Admin functionality for Planet CF.

Helper functions for admin operations including feed management
and OPML import/export.
"""

import xml.etree.ElementTree as ET
from typing import Any

from config import MAX_OPML_FEEDS
from templates import TEMPLATE_ADMIN_ERROR, render_template
from utils import log_op, truncate_error

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
    from workers import Response

    html = render_template(
        TEMPLATE_ADMIN_ERROR,
        theme=theme,
        planet=planet,
        title=title,
        message=message,
        back_url=back_url,
    )
    return Response(
        html,
        status=status,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
        },
    )


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
