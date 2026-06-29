# tests/unit/test_admin.py
"""Unit tests for admin helper functions in src/admin.py."""

import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest

from src.admin import (
    admin_error_response,
    parse_opml,
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
        """M-S3: DTD/XXE payloads are rejected outright (not stripped).

        forbid_dtd is unavailable in Pyodide, and the old regex strip broke on
        internal subsets containing ">". A legitimate OPML never needs a DOCTYPE,
        so any DOCTYPE/ENTITY presence is a hard parse error — no feed data is
        ever extracted from a malicious XXE payload.
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

        assert feeds == []
        assert len(errors) == 1
        assert "DOCTYPE/ENTITY" in errors[0]

    def test_doctype_rejected_even_when_innocuous(self):
        """M-S3: any DOCTYPE is rejected, even a benign SYSTEM reference.

        The previous behavior stripped DOCTYPE and parsed; that regex was the
        regression. Rejecting outright is the safe, portable choice.
        """
        opml_with_doctype = """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE opml SYSTEM "opml.dtd">
        <opml version="2.0">
          <body>
            <outline xmlUrl="https://example.com/feed.xml" text="Test" />
          </body>
        </opml>"""
        feeds, errors = parse_opml(opml_with_doctype)

        assert feeds == []
        assert len(errors) == 1
        assert "DOCTYPE/ENTITY" in errors[0]

    def test_doctype_with_internal_subset_containing_gt(self):
        """M-S3 regression: an internal subset containing '>' must still be rejected.

        This is the exact case the old `<!DOCTYPE[^>]*>` regex strip failed on.
        """
        payload = """<?xml version="1.0"?>
        <!DOCTYPE opml [<!ENTITY x "a > b">]>
        <opml version="2.0"><body>
            <outline xmlUrl="https://example.com/feed.xml" />
        </body></opml>"""
        feeds, errors = parse_opml(payload)

        assert feeds == []
        assert len(errors) == 1
        assert "DOCTYPE/ENTITY" in errors[0]

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
# admin_error_response() Tests
# =============================================================================


class TestAdminErrorResponse:
    """Tests for admin error response helper."""

    def test_returns_html_response(self):
        """Returns an HTML response with the rendered error template and correct status."""
        planet = {"name": "Test Planet", "description": "Test", "link": "https://test.com"}
        response = admin_error_response(planet, "Something went wrong")

        assert response.status == 400  # Default status for admin errors
        assert "text/html" in response.headers.get("Content-Type", "")

    def test_no_cache(self):
        """Response has no-store cache control (no caching)."""
        planet = {"name": "Test", "description": "", "link": ""}
        response = admin_error_response(planet, "Error")

        cache_control = response.headers.get("Cache-Control", "")
        assert "no-store" in cache_control

    def test_security_headers_applied(self):
        """M-S4: admin error pages carry the standard security headers."""
        planet = {"name": "Test", "description": "", "link": ""}
        response = admin_error_response(planet, "Error")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
