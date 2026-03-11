# src/feed_generator.py
"""Feed generation functions for Planet CF.

Pure functions that generate Atom 1.0, RSS 2.0, and RSS 1.0 (RDF) feed XML
from prepared entry data. These functions have no side effects and no database
access — they take explicit parameters and return rendered XML strings.

Extracted from main.py's _generate_atom_feed, _generate_rss_feed, and
_generate_rss10_feed instance methods.
"""

from datetime import datetime, timezone
from typing import Any

from templates import (
    TEMPLATE_FEED_ATOM,
    TEMPLATE_FEED_RSS,
    TEMPLATE_FEED_RSS10,
    render_template,
)
from xml_sanitizer import strip_xml_control_chars

__all__ = [
    "generate_atom_feed",
    "generate_rss10_feed",
    "generate_rss_feed",
    "prepare_atom_entries",
    "prepare_rss10_entries",
    "prepare_rss_entries",
]


def prepare_atom_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare entries for Atom feed template rendering.

    Strips illegal XML control characters as defense-in-depth for existing data.

    Args:
        entries: List of entry dicts from the database.

    Returns:
        List of dicts ready for the Atom template.
    """
    return [
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


def prepare_rss_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare entries for RSS 2.0 feed template rendering.

    Strips illegal XML control characters and escapes CDATA boundaries
    to prevent breakout attacks (Issue 2.1).

    Args:
        entries: List of entry dicts from the database.

    Returns:
        List of dicts ready for the RSS template.
    """
    return [
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


def prepare_rss10_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepare entries for RSS 1.0 (RDF) feed template rendering.

    RSS 1.0 uses dc:date (ISO 8601) and truncated descriptions.
    Strips illegal XML control characters as defense-in-depth.

    Args:
        entries: List of entry dicts from the database.

    Returns:
        List of dicts ready for the RSS 1.0 template.
    """
    max_desc_chars = 500
    return [
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


def generate_atom_feed(planet: dict[str, str], entries: list[dict[str, Any]], theme: str) -> str:
    """Generate Atom 1.0 feed XML using template.

    Args:
        planet: Planet configuration dict (name, url, etc.)
        entries: List of entry dicts from the database.
        theme: Theme name for template selection.

    Returns:
        Rendered Atom XML string.
    """
    template_entries = prepare_atom_entries(entries)
    return render_template(
        TEMPLATE_FEED_ATOM,
        theme=theme,
        planet=planet,
        entries=template_entries,
        updated_at=f"{datetime.now(timezone.utc).isoformat()}Z",
    )


def generate_rss_feed(planet: dict[str, str], entries: list[dict[str, Any]], theme: str) -> str:
    """Generate RSS 2.0 feed XML using template.

    Args:
        planet: Planet configuration dict (name, url, etc.)
        entries: List of entry dicts from the database.
        theme: Theme name for template selection.

    Returns:
        Rendered RSS 2.0 XML string.
    """
    template_entries = prepare_rss_entries(entries)
    return render_template(
        TEMPLATE_FEED_RSS,
        theme=theme,
        planet=planet,
        entries=template_entries,
        last_build_date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
    )


def generate_rss10_feed(planet: dict[str, str], entries: list[dict[str, Any]], theme: str) -> str:
    """Generate RSS 1.0 (RDF) feed XML using template.

    Args:
        planet: Planet configuration dict (name, url, etc.)
        entries: List of entry dicts from the database.
        theme: Theme name for template selection.

    Returns:
        Rendered RSS 1.0 XML string.
    """
    template_entries = prepare_rss10_entries(entries)
    return render_template(
        TEMPLATE_FEED_RSS10,
        theme=theme,
        planet=planet,
        entries=template_entries,
    )
