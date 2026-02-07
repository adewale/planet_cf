# tests/unit/test_admin.py
"""Unit tests for admin helper functions in src/admin.py."""

import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest

from src.admin import (
    admin_error_response,
    format_feed_validation_result,
    log_admin_action,
    parse_opml,
    validate_opml_feeds,
)
from src.config import MAX_OPML_FEEDS

# =============================================================================
# Compatibility: forbid_dtd is a Cloudflare Workers runtime extension,
# not available in standard CPython. We patch XMLParser to accept it.
# =============================================================================

_OriginalXMLParser = ET.XMLParser


class _CompatXMLParser(_OriginalXMLParser):
    """XMLParser that accepts forbid_dtd kwarg for test compatibility."""

    def __init__(self, *args, forbid_dtd=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._forbid_dtd = forbid_dtd


@pytest.fixture(autouse=True)
def _patch_xmlparser():
    """Patch XMLParser to accept forbid_dtd on standard CPython."""
    with patch.object(ET, "XMLParser", _CompatXMLParser):
        yield


# =============================================================================
# parse_opml() Tests
# =============================================================================


class TestParseOpml:
    """Tests for OPML parsing."""

    def test_valid_opml_with_feeds(self):
        """Parses valid OPML and extracts feeds."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <head><title>Test Feeds</title></head>
          <body>
            <outline text="Example Blog" title="Example Blog"
                     xmlUrl="https://example.com/feed.xml"
                     htmlUrl="https://example.com" />
            <outline text="Test Feed" title="Test Feed"
                     xmlUrl="https://test.com/rss"
                     htmlUrl="https://test.com" />
          </body>
        </opml>"""
        feeds, errors = parse_opml(opml)

        assert len(feeds) == 2
        assert feeds[0]["url"] == "https://example.com/feed.xml"
        assert feeds[0]["title"] == "Example Blog"
        assert feeds[0]["site_url"] == "https://example.com"
        assert feeds[1]["url"] == "https://test.com/rss"
        assert errors == []

    def test_empty_opml(self):
        """Parses OPML with no outline elements."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <head><title>Empty</title></head>
          <body></body>
        </opml>"""
        feeds, errors = parse_opml(opml)

        assert feeds == []
        assert errors == []

    def test_malformed_xml(self):
        """Returns error for malformed XML."""
        feeds, errors = parse_opml("<not valid xml")

        assert feeds == []
        assert len(errors) == 1
        assert "Invalid OPML format" in errors[0]

    def test_xxe_attack_rejected(self):
        """DTD/XXE payloads are rejected.

        Note: In Cloudflare Workers runtime, forbid_dtd=True blocks DTD declarations.
        In standard CPython the DTD is processed but entity resolution behaviour varies.
        This test verifies that parse_opml does not return usable feed data from
        malicious XXE payloads regardless of runtime.
        """
        xxe_payload = """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE foo [
          <!ENTITY xxe SYSTEM "file:///etc/passwd">
        ]>
        <opml version="2.0">
          <body>
            <outline xmlUrl="&xxe;" />
          </body>
        </opml>"""
        feeds, errors = parse_opml(xxe_payload)

        # The entity &xxe; either gets rejected (forbid_dtd runtime),
        # or on standard CPython, entity resolution may fail or produce empty url.
        # Either way, we should not get a valid "file:///etc/passwd" feed URL.
        if feeds:
            for feed in feeds:
                assert "file:///" not in feed["url"]
                assert "/etc/passwd" not in feed["url"]

    def test_exceeds_max_feeds_limit(self):
        """Truncates feeds exceeding MAX_OPML_FEEDS and adds warning."""
        # Build OPML with MAX_OPML_FEEDS + 5 feeds
        outlines = "\n".join(
            f'<outline xmlUrl="https://feed{i}.example.com/rss" title="Feed {i}" />'
            for i in range(MAX_OPML_FEEDS + 5)
        )
        opml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <body>{outlines}</body>
        </opml>"""

        feeds, errors = parse_opml(opml)

        assert len(feeds) == MAX_OPML_FEEDS
        assert len(errors) == 1
        assert f"{MAX_OPML_FEEDS + 5} feeds" in errors[0]
        assert f"limited to {MAX_OPML_FEEDS}" in errors[0]

    def test_outlines_without_xmlurl_are_skipped(self):
        """Outline elements without xmlUrl are ignored."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <body>
            <outline text="Category" title="Category">
              <outline xmlUrl="https://example.com/feed.xml" title="Feed" />
            </outline>
            <outline text="No URL" title="Just a label" />
          </body>
        </opml>"""
        feeds, errors = parse_opml(opml)

        assert len(feeds) == 1
        assert feeds[0]["url"] == "https://example.com/feed.xml"

    def test_uses_text_attr_when_title_missing(self):
        """Falls back to text attribute when title is missing."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <body>
            <outline text="My Blog" xmlUrl="https://example.com/feed.xml" />
          </body>
        </opml>"""
        feeds, errors = parse_opml(opml)

        assert len(feeds) == 1
        assert feeds[0]["title"] == "My Blog"

    def test_empty_title_and_text(self):
        """Returns empty string when both title and text are missing."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <body>
            <outline xmlUrl="https://example.com/feed.xml" />
          </body>
        </opml>"""
        feeds, errors = parse_opml(opml)

        assert len(feeds) == 1
        assert feeds[0]["title"] == ""
        assert feeds[0]["site_url"] == ""


# =============================================================================
# validate_opml_feeds() Tests
# =============================================================================


class TestValidateOpmlFeeds:
    """Tests for OPML feed validation."""

    def test_valid_new_feeds(self):
        """All new feeds are returned when none exist."""
        feeds = [
            {"url": "https://a.com/feed", "title": "A", "site_url": ""},
            {"url": "https://b.com/feed", "title": "B", "site_url": ""},
        ]
        new_feeds, skipped = validate_opml_feeds(feeds, set())

        assert len(new_feeds) == 2
        assert skipped == []

    def test_duplicate_urls_filtered(self):
        """Feeds with URLs already in existing_urls are skipped."""
        feeds = [
            {"url": "https://existing.com/feed", "title": "Existing", "site_url": ""},
            {"url": "https://new.com/feed", "title": "New", "site_url": ""},
        ]
        existing = {"https://existing.com/feed"}
        new_feeds, skipped = validate_opml_feeds(feeds, existing)

        assert len(new_feeds) == 1
        assert new_feeds[0]["url"] == "https://new.com/feed"
        assert len(skipped) == 1
        assert "Already exists" in skipped[0]

    def test_deduplicates_within_import(self):
        """Duplicate URLs within the same import batch are filtered."""
        feeds = [
            {"url": "https://a.com/feed", "title": "A1", "site_url": ""},
            {"url": "https://a.com/feed", "title": "A2", "site_url": ""},
        ]
        new_feeds, skipped = validate_opml_feeds(feeds, set())

        assert len(new_feeds) == 1
        assert len(skipped) == 1

    def test_empty_feeds_list(self):
        """Empty feeds list returns empty results."""
        new_feeds, skipped = validate_opml_feeds([], set())

        assert new_feeds == []
        assert skipped == []


# =============================================================================
# admin_error_response() Tests
# =============================================================================


class TestAdminErrorResponse:
    """Tests for admin error response helper."""

    def test_returns_html_response(self):
        """Returns an HTML response with the rendered error template."""
        planet = {"name": "Test Planet", "description": "Test", "link": "https://test.com"}
        response = admin_error_response(planet, "Something went wrong")

        assert response.status == 200
        assert "text/html" in response.headers.get("Content-Type", "")

    def test_no_cache(self):
        """Response has cache_max_age=0 (no caching)."""
        planet = {"name": "Test", "description": "", "link": ""}
        response = admin_error_response(planet, "Error")

        cache_control = response.headers.get("Cache-Control", "")
        assert "max-age=0" in cache_control


# =============================================================================
# format_feed_validation_result() Tests
# =============================================================================


class TestFormatFeedValidationResult:
    """Tests for feed validation result formatting."""

    def test_valid_feed_result(self):
        """Formats a valid feed result correctly."""
        result = format_feed_validation_result(
            valid=True,
            title="My Feed",
            site_url="https://example.com",
            entry_count=10,
            final_url="https://example.com/feed.xml",
        )

        assert result["valid"] is True
        assert result["title"] == "My Feed"
        assert result["site_url"] == "https://example.com"
        assert result["entry_count"] == 10
        assert result["final_url"] == "https://example.com/feed.xml"
        assert result["error"] is None

    def test_invalid_feed_result(self):
        """Formats an invalid feed result with error."""
        result = format_feed_validation_result(
            valid=False,
            error="Feed returned 404",
        )

        assert result["valid"] is False
        assert result["error"] == "Feed returned 404"
        assert result["title"] is None
        assert result["entry_count"] == 0

    def test_default_values(self):
        """Default values are applied correctly."""
        result = format_feed_validation_result(valid=True)

        assert result["valid"] is True
        assert result["title"] is None
        assert result["site_url"] is None
        assert result["entry_count"] == 0
        assert result["final_url"] is None
        assert result["error"] is None


# =============================================================================
# log_admin_action() Tests
# =============================================================================


class TestLogAdminAction:
    """Tests for admin action logging."""

    def test_logs_structured_event(self):
        """Calls log_op with correct structured fields."""
        with patch("src.admin.log_op") as mock_log:
            log_admin_action(
                action="add_feed",
                admin_username="testadmin",
                target_type="feed",
                target_id=42,
                details={"url": "https://example.com/feed.xml"},
            )

            mock_log.assert_called_once_with(
                "admin_action",
                action="add_feed",
                admin="testadmin",
                target_type="feed",
                target_id=42,
                details={"url": "https://example.com/feed.xml"},
            )

    def test_logs_with_optional_fields_as_none(self):
        """Handles optional fields being None."""
        with patch("src.admin.log_op") as mock_log:
            log_admin_action(action="login", admin_username="admin")

            mock_log.assert_called_once_with(
                "admin_action",
                action="login",
                admin="admin",
                target_type=None,
                target_id=None,
                details=None,
            )
