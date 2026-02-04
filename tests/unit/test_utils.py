# tests/unit/test_utils.py
"""Unit tests for utility functions in src/utils.py.

Tests the standalone helper functions directly, without going through main.py.
"""

import json
import logging
from datetime import UTC, datetime

from src.utils import (
    ERROR_MESSAGE_MAX_LENGTH,
    feed_response,
    get_display_author,
    html_response,
    json_error,
    json_response,
    log_error,
    log_op,
    normalize_entry_content,
    parse_iso_datetime,
    redirect_response,
    truncate_error,
    validate_feed_id,
    xml_escape,
)

# =============================================================================
# truncate_error
# =============================================================================


class TestTruncateError:
    """Tests for truncate_error()."""

    def test_short_string_unchanged(self):
        """Short strings are returned unchanged."""
        assert truncate_error("short") == "short"

    def test_exact_limit_unchanged(self):
        """String at exactly the limit is returned unchanged."""
        msg = "x" * ERROR_MESSAGE_MAX_LENGTH
        assert truncate_error(msg) == msg

    def test_long_string_truncated(self):
        """Long strings are truncated to ERROR_MESSAGE_MAX_LENGTH with ellipsis."""
        msg = "a" * 500
        result = truncate_error(msg)
        assert len(result) == ERROR_MESSAGE_MAX_LENGTH
        assert result.endswith("...")

    def test_exception_object(self):
        """Works with Exception objects."""
        exc = ValueError("b" * 500)
        result = truncate_error(exc)
        assert len(result) == ERROR_MESSAGE_MAX_LENGTH
        assert result.endswith("...")

    def test_custom_max_length(self):
        """Respects custom max_length parameter."""
        msg = "c" * 100
        result = truncate_error(msg, max_length=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_empty_string(self):
        """Empty string is returned unchanged."""
        assert truncate_error("") == ""


# =============================================================================
# log_op
# =============================================================================


class TestLogOp:
    """Tests for log_op()."""

    def test_returns_structured_json(self, caplog):
        """Logs a structured JSON dict with event_type and timestamp."""
        with caplog.at_level(logging.INFO, logger="src.main"):
            log_op("test_event", key="value", number=42)
        assert len(caplog.records) == 1
        output = json.loads(caplog.records[0].message)
        assert output["event_type"] == "test_event"
        assert output["key"] == "value"
        assert output["number"] == 42
        assert "timestamp" in output

    def test_timestamp_is_iso_format(self, caplog):
        """Timestamp is in ISO format with Z suffix."""
        with caplog.at_level(logging.INFO, logger="src.main"):
            log_op("ts_test")
        output = json.loads(caplog.records[0].message)
        assert output["timestamp"].endswith("Z")
        assert "T" in output["timestamp"]


# =============================================================================
# log_error
# =============================================================================


class TestLogError:
    """Tests for log_error()."""

    def test_returns_structured_error_dict(self, caplog):
        """Logs error type and truncated message."""
        with caplog.at_level(logging.INFO, logger="src.main"):
            log_error("test_error", ValueError("bad value"), extra="info")
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.ERROR
        output = json.loads(caplog.records[0].message)
        assert output["event_type"] == "test_error"
        assert output["error_type"] == "ValueError"
        assert output["error"] == "bad value"
        assert output["extra"] == "info"

    def test_truncates_long_error(self, caplog):
        """Truncates long exception messages."""
        with caplog.at_level(logging.INFO, logger="src.main"):
            log_error("long_error", RuntimeError("x" * 500))
        output = json.loads(caplog.records[0].message)
        assert len(output["error"]) == ERROR_MESSAGE_MAX_LENGTH
        assert output["error"].endswith("...")


# =============================================================================
# validate_feed_id
# =============================================================================


class TestValidateFeedId:
    """Tests for validate_feed_id()."""

    def test_valid_int_string(self):
        """Valid integer string returns int."""
        assert validate_feed_id("42") == 42

    def test_invalid_string(self):
        """Non-numeric string returns None."""
        assert validate_feed_id("abc") is None

    def test_none_input(self):
        """None returns None."""
        assert validate_feed_id(None) is None

    def test_empty_string(self):
        """Empty string returns None."""
        assert validate_feed_id("") is None

    def test_negative_string(self):
        """Negative number string returns None (isdigit fails on '-')."""
        assert validate_feed_id("-1") is None

    def test_zero(self):
        """Zero returns None (id_int <= 0)."""
        assert validate_feed_id("0") is None

    def test_large_valid_id(self):
        """Large valid ID is returned."""
        assert validate_feed_id("999999") == 999999


# =============================================================================
# xml_escape
# =============================================================================


class TestXmlEscape:
    """Tests for xml_escape()."""

    def test_escapes_ampersand(self):
        assert xml_escape("a&b") == "a&amp;b"

    def test_escapes_less_than(self):
        assert xml_escape("a<b") == "a&lt;b"

    def test_escapes_greater_than(self):
        assert xml_escape("a>b") == "a&gt;b"

    def test_escapes_all_special_chars(self):
        assert xml_escape("<a&b>") == "&lt;a&amp;b&gt;"

    def test_no_escaping_needed(self):
        assert xml_escape("hello world") == "hello world"

    def test_empty_string(self):
        assert xml_escape("") == ""


# =============================================================================
# get_display_author
# =============================================================================


class TestGetDisplayAuthor:
    """Tests for get_display_author()."""

    def test_with_author(self):
        """Returns author when valid and no @ sign."""
        assert get_display_author("Jane Doe", "Blog") == "Jane Doe"

    def test_email_falls_back_to_feed_title(self):
        """Email author falls back to feed title."""
        assert get_display_author("jane@example.com", "Blog") == "Blog"

    def test_none_author_falls_back(self):
        """None author falls back to feed title."""
        assert get_display_author(None, "Blog") == "Blog"

    def test_empty_author_falls_back(self):
        """Empty author falls back to feed title."""
        assert get_display_author("", "Blog") == "Blog"

    def test_both_missing(self):
        """Both missing returns 'Unknown'."""
        assert get_display_author(None, None) == "Unknown"


# =============================================================================
# normalize_entry_content
# =============================================================================


class TestNormalizeEntryContent:
    """Tests for normalize_entry_content()."""

    def test_picks_content_and_strips_title(self):
        """Strips matching h1 title from content."""
        content = "<h1>My Title</h1><p>Body text</p>"
        result = normalize_entry_content(content, "My Title")
        assert "<h1>" not in result
        assert "<p>Body text</p>" in result

    def test_no_match_preserves_content(self):
        """Non-matching heading is preserved."""
        content = "<h1>Other Heading</h1><p>Body</p>"
        result = normalize_entry_content(content, "My Title")
        assert "<h1>Other Heading</h1>" in result

    def test_empty_content(self):
        """Empty content returns empty."""
        assert normalize_entry_content("", "Title") == ""

    def test_none_title(self):
        """None title returns content unchanged."""
        content = "<h1>Hi</h1><p>Body</p>"
        assert normalize_entry_content(content, None) == content

    def test_no_heading(self):
        """Content without headings is returned unchanged."""
        content = "<p>Just text</p>"
        assert normalize_entry_content(content, "Title") == content


# =============================================================================
# parse_iso_datetime
# =============================================================================


class TestParseIsoDatetime:
    """Tests for parse_iso_datetime()."""

    def test_valid_iso_z(self):
        """Parses ISO string with Z suffix."""
        result = parse_iso_datetime("2026-01-17T12:30:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.tzinfo is not None

    def test_valid_iso_offset(self):
        """Parses ISO string with +00:00 offset."""
        result = parse_iso_datetime("2026-01-17T12:30:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_naive_assumes_utc(self):
        """Naive datetime gets UTC timezone."""
        result = parse_iso_datetime("2026-01-17T12:30:00")
        assert result is not None
        assert result.tzinfo == UTC

    def test_invalid_string_returns_none(self):
        """Invalid string returns None."""
        assert parse_iso_datetime("not-a-date") is None

    def test_none_input_returns_none(self):
        """None returns None."""
        assert parse_iso_datetime(None) is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert parse_iso_datetime("") is None

    def test_can_subtract_from_now(self):
        """Result can be used in datetime arithmetic."""
        result = parse_iso_datetime("2026-01-17T12:30:00")
        assert result is not None
        delta = datetime.now(UTC) - result
        assert delta is not None


# =============================================================================
# html_response
# =============================================================================


class TestHtmlResponse:
    """Tests for html_response()."""

    def test_content_type(self):
        """Response has text/html content type."""
        resp = html_response("<p>Hi</p>")
        assert resp.headers["Content-Type"] == "text/html; charset=utf-8"

    def test_csp_header(self):
        """Response has Content-Security-Policy header."""
        resp = html_response("<p>Hi</p>")
        assert "Content-Security-Policy" in resp.headers

    def test_security_headers(self):
        """Response has security headers."""
        resp = html_response("<p>Hi</p>")
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_cache_control(self):
        """Response has cache-control header."""
        resp = html_response("<p>Hi</p>", cache_max_age=7200)
        assert "max-age=7200" in resp.headers["Cache-Control"]

    def test_body(self):
        """Response body matches input."""
        resp = html_response("<p>Hi</p>")
        assert resp.body == "<p>Hi</p>"


# =============================================================================
# json_response
# =============================================================================


class TestJsonResponse:
    """Tests for json_response()."""

    def test_content_type(self):
        """Response has application/json content type."""
        resp = json_response({"key": "value"})
        assert resp.headers["Content-Type"] == "application/json"

    def test_serializes_data(self):
        """Data is JSON serialized in body."""
        resp = json_response({"key": "value"})
        assert json.loads(resp.body) == {"key": "value"}

    def test_default_status_200(self):
        """Default status is 200."""
        resp = json_response({})
        assert resp.status == 200

    def test_custom_status(self):
        """Custom status code."""
        resp = json_response({}, status=201)
        assert resp.status == 201


# =============================================================================
# json_error
# =============================================================================


class TestJsonError:
    """Tests for json_error()."""

    def test_error_body(self):
        """Error message is in body."""
        resp = json_error("bad request")
        body = json.loads(resp.body)
        assert body == {"error": "bad request"}

    def test_default_status_400(self):
        """Default status is 400."""
        resp = json_error("bad")
        assert resp.status == 400

    def test_custom_status(self):
        """Custom error status."""
        resp = json_error("not found", status=404)
        assert resp.status == 404


# =============================================================================
# redirect_response
# =============================================================================


class TestRedirectResponse:
    """Tests for redirect_response()."""

    def test_status_302(self):
        """Status is 302."""
        resp = redirect_response("https://example.com")
        assert resp.status == 302

    def test_location_header(self):
        """Location header is set."""
        resp = redirect_response("https://example.com")
        assert resp.headers["Location"] == "https://example.com"


# =============================================================================
# feed_response
# =============================================================================


class TestFeedResponse:
    """Tests for feed_response()."""

    def test_content_type(self):
        """Content type matches specified type."""
        resp = feed_response("<rss/>", "application/rss+xml")
        assert "application/rss+xml" in resp.headers["Content-Type"]

    def test_cache_control(self):
        """Cache control is set."""
        resp = feed_response("<feed/>", "application/atom+xml", cache_max_age=7200)
        assert "max-age=7200" in resp.headers["Cache-Control"]

    def test_body(self):
        """Body matches input content."""
        resp = feed_response("<rss/>", "application/rss+xml")
        assert resp.body == "<rss/>"
