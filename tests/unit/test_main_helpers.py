# tests/unit/test_main_helpers.py
"""Unit tests for helper functions in main.py."""

import json
from datetime import UTC, datetime

from src.main import (
    RateLimitError,
    _feed_response,
    _get_display_author,
    _html_response,
    _json_error,
    _json_response,
    _parse_iso_datetime,
    _redirect_response,
)
from src.observability import (
    ERROR_MESSAGE_MAX_LENGTH,
    log_error,
    log_op,
    truncate_error,
)
from src.wrappers import (
    _extract_form_value,
    _is_js_undefined,
    _safe_str,
    _to_d1_value,
    _to_py_list,
    _to_py_safe,
)

# =============================================================================
# Type Conversion Tests
# =============================================================================


class TestIsJsUndefined:
    """Tests for _is_js_undefined function.

    Note: In non-Pyodide environment, _is_js_undefined checks for JsProxy
    undefined, not Python None. Python None is just None.
    """

    def test_returns_false_for_none_in_python(self):
        """Python None is not JS undefined (in non-Pyodide)."""
        # In Pyodide, this would check for actual JS undefined
        # In Python tests, None is just None
        assert _is_js_undefined(None) is False

    def test_returns_false_for_value(self):
        """Non-None values are not undefined."""
        assert _is_js_undefined("hello") is False
        assert _is_js_undefined(0) is False
        assert _is_js_undefined(False) is False
        assert _is_js_undefined([]) is False
        assert _is_js_undefined({}) is False

    def test_returns_false_for_empty_string(self):
        """Empty string is not undefined."""
        assert _is_js_undefined("") is False


class TestSafeStr:
    """Tests for _safe_str function."""

    def test_converts_value_to_string(self):
        """Values are converted to strings."""
        assert _safe_str("hello") == "hello"
        assert _safe_str(123) == "123"
        assert _safe_str(3.14) == "3.14"

    def test_returns_none_for_none(self):
        """None returns None."""
        assert _safe_str(None) is None

    def test_returns_none_for_empty_string(self):
        """Empty string returns None (falsy)."""
        assert _safe_str("") is None


class TestToPySafe:
    """Tests for _to_py_safe function."""

    def test_returns_none_for_none(self):
        """None returns None."""
        assert _to_py_safe(None) is None

    def test_passes_through_basic_types(self):
        """Basic Python types are passed through."""
        assert _to_py_safe(42) == 42
        assert _to_py_safe(3.14) == 3.14
        assert _to_py_safe("hello") == "hello"
        assert _to_py_safe(True) is True
        assert _to_py_safe(False) is False

    def test_converts_dict_recursively(self):
        """Dicts are converted recursively."""
        result = _to_py_safe({"key": "value", "nested": {"a": 1}})
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_converts_list_recursively(self):
        """Lists are converted recursively."""
        result = _to_py_safe([1, "two", {"three": 3}])
        assert result == [1, "two", {"three": 3}]

    def test_converts_tuple_to_list(self):
        """Tuples are converted to lists."""
        result = _to_py_safe((1, 2, 3))
        assert result == [1, 2, 3]

    def test_depth_guard_prevents_unbounded_recursion(self):
        """Deeply nested structures are handled without stack overflow.

        The depth guard at _MAX_CONVERSION_DEPTH (50) should return the raw
        value once the limit is exceeded, preventing unbounded recursion.
        """
        from src.wrappers import _MAX_CONVERSION_DEPTH

        # Build a structure 100 levels deep (well past the 50-level guard)
        deep: dict | str = "leaf"
        for _i in range(100):
            deep = {"level": deep}

        # Should not raise RecursionError
        result = _to_py_safe(deep)
        assert result is not None

        # Walk into the result up to the depth limit
        node = result
        for _ in range(_MAX_CONVERSION_DEPTH):
            assert isinstance(node, dict)
            node = node["level"]

        # At depth >= _MAX_CONVERSION_DEPTH the value is returned as-is
        # (a raw dict that was not recursively converted further, but still a dict
        # because _to_py_safe returns the value unchanged at the depth limit).
        # The important thing is we didn't get a stack overflow.
        assert node is not None

    def test_depth_guard_returns_value_at_limit(self):
        """At exactly the depth limit, _to_py_safe returns value as-is."""
        from src.wrappers import _MAX_CONVERSION_DEPTH

        # Call _to_py_safe with _depth at exactly the limit
        sentinel = {"key": "should_not_be_recursed"}
        result = _to_py_safe(sentinel, _depth=_MAX_CONVERSION_DEPTH)
        # The value should be returned as-is (no conversion attempted)
        assert result is sentinel


class TestToPyList:
    """Tests for _to_py_list function."""

    def test_converts_list(self):
        """List is converted to Python list of dicts."""
        result = _to_py_list([{"a": 1}, {"b": 2}])
        assert result == [{"a": 1}, {"b": 2}]

    def test_returns_empty_for_none(self):
        """None returns empty list."""
        assert _to_py_list(None) == []

    def test_converts_empty_list(self):
        """Empty list returns empty list."""
        assert _to_py_list([]) == []


class TestToD1Value:
    """Tests for _to_d1_value function."""

    def test_passes_through_primitives(self):
        """Primitives are passed through."""
        assert _to_d1_value(42) == 42
        assert _to_d1_value("hello") == "hello"
        assert _to_d1_value(3.14) == 3.14

    def test_handles_none(self):
        """None is handled (converted to JS null in Pyodide)."""
        # In non-Pyodide environment, None is returned as-is
        result = _to_d1_value(None)
        assert result is None


# =============================================================================
# Response Helper Tests
# =============================================================================


class TestHtmlResponse:
    """Tests for _html_response function."""

    def test_sets_content_type(self):
        """Response has text/html content type."""
        response = _html_response("<p>Hello</p>")
        assert response.headers["Content-Type"] == "text/html; charset=utf-8"

    def test_sets_cache_control(self):
        """Response has cache control header."""
        response = _html_response("<p>Hello</p>", cache_max_age=3600)
        assert "max-age=3600" in response.headers["Cache-Control"]

    def test_sets_body(self):
        """Response contains the HTML body."""
        response = _html_response("<p>Hello</p>")
        assert response.body == "<p>Hello</p>"

    def test_default_status_200(self):
        """Default status is 200."""
        response = _html_response("<p>Hello</p>")
        assert response.status == 200


class TestJsonResponse:
    """Tests for _json_response function."""

    def test_sets_content_type(self):
        """Response has application/json content type."""
        response = _json_response({"key": "value"})
        assert response.headers["Content-Type"] == "application/json"

    def test_serializes_data(self):
        """Data is JSON serialized."""
        response = _json_response({"key": "value", "number": 42})
        body = json.loads(response.body)
        assert body == {"key": "value", "number": 42}

    def test_default_status_200(self):
        """Default status is 200."""
        response = _json_response({})
        assert response.status == 200

    def test_custom_status(self):
        """Custom status can be set."""
        response = _json_response({}, status=201)
        assert response.status == 201


class TestJsonError:
    """Tests for _json_error function."""

    def test_returns_error_json(self):
        """Returns JSON with error message."""
        response = _json_error("Something went wrong")
        body = json.loads(response.body)
        assert body == {"error": "Something went wrong"}

    def test_default_status_400(self):
        """Default status is 400."""
        response = _json_error("Bad request")
        assert response.status == 400

    def test_custom_status(self):
        """Custom status can be set."""
        response = _json_error("Not found", status=404)
        assert response.status == 404
        response = _json_error("Server error", status=500)
        assert response.status == 500


class TestRedirectResponse:
    """Tests for _redirect_response function."""

    def test_sets_location_header(self):
        """Response has Location header."""
        response = _redirect_response("https://example.com")
        assert response.headers["Location"] == "https://example.com"

    def test_status_302(self):
        """Status is 302 (Found)."""
        response = _redirect_response("https://example.com")
        assert response.status == 302


class TestFeedResponse:
    """Tests for _feed_response function."""

    def test_sets_content_type(self):
        """Response has correct content type."""
        response = _feed_response("<rss>...</rss>", "application/rss+xml")
        assert "application/rss+xml" in response.headers["Content-Type"]

    def test_sets_cache_control(self):
        """Response has cache control header."""
        response = _feed_response("<feed>...</feed>", "application/atom+xml", cache_max_age=7200)
        assert "max-age=7200" in response.headers["Cache-Control"]


# =============================================================================
# Form Extraction Tests
# =============================================================================


class MockFormData:
    """Mock form data for testing."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key):
        return self._data.get(key)


class TestExtractFormValue:
    """Tests for _extract_form_value function."""

    def test_returns_string_value(self):
        """Returns string value from form."""
        form = MockFormData({"name": "test"})
        assert _extract_form_value(form, "name") == "test"

    def test_handles_missing_key(self):
        """Returns None for missing key."""
        form = MockFormData({})
        assert _extract_form_value(form, "missing") is None

    def test_handles_none_value(self):
        """Returns None for None value."""
        form = MockFormData({"empty": None})
        assert _extract_form_value(form, "empty") is None


# =============================================================================
# Logging Tests
# =============================================================================


class TestLogOp:
    """Tests for log_op function."""

    def test_prints_json(self, caplog):
        """Logs JSON to stderr via logging module."""
        import logging

        logger = logging.getLogger("src.observability")
        old_propagate = logger.propagate
        logger.propagate = True
        try:
            with caplog.at_level("INFO", logger="src.observability"):
                log_op("test_event", key="value", number=42)
            assert len(caplog.records) == 1
            output = json.loads(caplog.records[0].message)
            assert output["event_type"] == "test_event"
            assert output["key"] == "value"
            assert output["number"] == 42
        finally:
            logger.propagate = old_propagate

    def test_includes_timestamp(self, caplog):
        """Log includes timestamp."""
        import logging

        logger = logging.getLogger("src.observability")
        old_propagate = logger.propagate
        logger.propagate = True
        try:
            with caplog.at_level("INFO", logger="src.observability"):
                log_op("test_event")
            assert len(caplog.records) == 1
            output = json.loads(caplog.records[0].message)
            assert "timestamp" in output
        finally:
            logger.propagate = old_propagate


# =============================================================================
# Error Message Length Constant Test
# =============================================================================


class TestErrorMessageMaxLength:
    """Tests for ERROR_MESSAGE_MAX_LENGTH constant."""

    def test_constant_value(self):
        """Constant is set to expected value."""
        assert ERROR_MESSAGE_MAX_LENGTH == 200

    def test_truncation_usage(self):
        """Truncation works as expected."""
        long_message = "x" * 500
        truncated = long_message[:ERROR_MESSAGE_MAX_LENGTH]
        assert len(truncated) == 200


class TestTruncateError:
    """Tests for truncate_error helper function."""

    def test_short_message_unchanged(self):
        """Messages under limit are returned unchanged."""
        msg = "Short error"
        assert truncate_error(msg) == msg

    def test_exact_limit_unchanged(self):
        """Messages at exactly the limit are returned unchanged."""
        msg = "x" * ERROR_MESSAGE_MAX_LENGTH
        assert truncate_error(msg) == msg
        assert len(truncate_error(msg)) == ERROR_MESSAGE_MAX_LENGTH

    def test_long_message_truncated_with_ellipsis(self):
        """Messages over limit are truncated with ellipsis indicator."""
        msg = "x" * 500
        result = truncate_error(msg)
        assert len(result) == ERROR_MESSAGE_MAX_LENGTH
        assert result.endswith("...")

    def test_works_with_exception(self):
        """Can truncate exception objects."""
        error = ValueError("x" * 500)
        result = truncate_error(error)
        assert len(result) == ERROR_MESSAGE_MAX_LENGTH
        assert result.endswith("...")


class TestLogError:
    """Tests for log_error helper function."""

    def test_logs_error_type_and_message(self, caplog):
        """Logs error type and truncated message via logging module at ERROR level."""
        import logging

        logger = logging.getLogger("src.observability")
        old_propagate = logger.propagate
        logger.propagate = True
        try:
            error = ValueError("Test error message")
            with caplog.at_level("INFO", logger="src.observability"):
                log_error("test_event", error, extra_field="extra_value")

            assert len(caplog.records) == 1
            # Verify it logs at ERROR level (not INFO)
            assert caplog.records[0].levelno == logging.ERROR
            output = json.loads(caplog.records[0].message)

            assert output["event_type"] == "test_event"
            assert output["error_type"] == "ValueError"
            assert output["error"] == "Test error message"
            assert output["extra_field"] == "extra_value"
        finally:
            logger.propagate = old_propagate


class TestRateLimitError:
    """Tests for RateLimitError exception class."""

    def test_basic_creation(self):
        """Can create with just a message."""
        error = RateLimitError("Rate limited")
        assert str(error) == "Rate limited"
        assert error.retry_after is None

    def test_with_retry_after(self):
        """Can create with retry_after value."""
        error = RateLimitError("Rate limited", retry_after="3600")
        assert str(error) == "Rate limited"
        assert error.retry_after == "3600"

    def test_is_exception(self):
        """Is a proper Exception subclass."""
        error = RateLimitError("Rate limited")
        assert isinstance(error, Exception)

        # Can be raised and caught
        try:
            raise error
        except RateLimitError as e:
            assert str(e) == "Rate limited"


class TestGetDisplayAuthor:
    """Tests for _get_display_author function."""

    def test_returns_author_when_valid(self):
        """Returns author when it's non-empty and doesn't contain @."""
        result = _get_display_author("John Doe", "Blog Title")
        assert result == "John Doe"

    def test_filters_email_address(self):
        """Filters author that looks like an email address."""
        result = _get_display_author("john@example.com", "Blog Title")
        assert result == "Blog Title"

    def test_returns_feed_title_when_author_none(self):
        """Returns feed title when author is None."""
        result = _get_display_author(None, "Blog Title")
        assert result == "Blog Title"

    def test_returns_feed_title_when_author_empty(self):
        """Returns feed title when author is empty string."""
        result = _get_display_author("", "Blog Title")
        assert result == "Blog Title"

    def test_returns_unknown_when_both_missing(self):
        """Returns 'Unknown' when both author and feed_title are missing."""
        result = _get_display_author(None, None)
        assert result == "Unknown"

    def test_returns_unknown_when_email_and_no_feed_title(self):
        """Returns 'Unknown' when author is email and feed_title is None."""
        result = _get_display_author("user@domain.com", None)
        assert result == "Unknown"

    def test_allows_at_sign_in_name(self):
        """Filters names containing @ (they look like emails)."""
        result = _get_display_author("John @home", "Blog Title")
        assert result == "Blog Title"


# =============================================================================
# Datetime Parsing Tests
# =============================================================================


class TestParseIsoDatetime:
    """Tests for _parse_iso_datetime function."""

    def test_parses_z_suffix(self):
        """Parses ISO datetime with Z suffix."""
        result = _parse_iso_datetime("2026-01-17T12:30:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 17
        assert result.hour == 12
        assert result.minute == 30
        assert result.tzinfo is not None

    def test_parses_offset_suffix(self):
        """Parses ISO datetime with +00:00 offset."""
        result = _parse_iso_datetime("2026-01-17T12:30:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_parses_naive_datetime_assumes_utc(self):
        """Parses naive datetime (no timezone) and assumes UTC."""
        result = _parse_iso_datetime("2026-01-17T12:30:00")
        assert result is not None
        assert result.tzinfo == UTC

    def test_returns_none_for_none_input(self):
        """Returns None for None input."""
        assert _parse_iso_datetime(None) is None

    def test_returns_none_for_empty_string(self):
        """Returns None for empty string."""
        assert _parse_iso_datetime("") is None

    def test_returns_none_for_invalid_format(self):
        """Returns None for invalid datetime format."""
        assert _parse_iso_datetime("not-a-date") is None
        assert _parse_iso_datetime("2026/01/17") is None

    def test_result_is_timezone_aware(self):
        """Result is always timezone-aware for valid input."""
        # Z suffix
        result1 = _parse_iso_datetime("2026-01-17T12:30:00Z")
        assert result1 is not None
        assert result1.tzinfo is not None

        # Offset suffix
        result2 = _parse_iso_datetime("2026-01-17T12:30:00+00:00")
        assert result2 is not None
        assert result2.tzinfo is not None

        # Naive (should be converted to UTC)
        result3 = _parse_iso_datetime("2026-01-17T12:30:00")
        assert result3 is not None
        assert result3.tzinfo is not None

    def test_can_subtract_from_now(self):
        """Result can be subtracted from datetime.now(timezone.utc) without error.

        This is the bug that was fixed - naive datetimes from the database
        caused TypeError when subtracting from timezone-aware now.
        """
        # Naive datetime (the problematic case)
        result = _parse_iso_datetime("2026-01-17T12:30:00")
        assert result is not None
        now = datetime.now(UTC)
        # This should not raise TypeError
        delta = now - result
        assert delta is not None

    def test_parses_microseconds(self):
        """Parses ISO datetime with microseconds."""
        result = _parse_iso_datetime("2026-01-17T12:30:00.123456Z")
        assert result is not None
        assert result.microsecond == 123456


# =============================================================================
# Content Normalization Tests
# =============================================================================


class TestNormalizeEntryContent:
    """Tests for _normalize_entry_content function.

    Based on actual duplicate title patterns found in Planet CF feeds:
    - Jilles Soeters: metadata before h1 (date / read time)
    - Boris Tane: whitespace-padded h1, metadata after
    - Sunil Pai: h1 directly at start
    """

    def test_strips_h1_with_whitespace_padding(self):
        """Strips h1 with whitespace padding inside tags (Boris Tane pattern)."""
        from src.main import _normalize_entry_content

        content = "  <h1> What even are Cloudflare Durable Objects? </h1> \n\nNov 4, 2025"
        title = "What even are Cloudflare Durable Objects?"
        result = _normalize_entry_content(content, title)
        assert "<h1>" not in result
        assert "Nov 4, 2025" in result

    def test_strips_h1_with_metadata_before(self):
        """Strips h1 when metadata (date/read time) appears before it (Jilles pattern)."""
        from src.main import _normalize_entry_content

        content = "January 15, 2026  / 9 min read   \n\n <h1> Open Graph Images in Astro: Build-Time vs Runtime </h1>   \n<p>Content here</p>"
        title = "Open Graph Images in Astro: Build-Time vs Runtime"
        result = _normalize_entry_content(content, title)
        assert "<h1>" not in result
        assert "January 15, 2026" not in result
        assert "<p>Content here</p>" in result

    def test_strips_h1_with_metadata_after(self):
        """Strips h1 when metadata appears after it (Boris pattern)."""
        from src.main import _normalize_entry_content

        content = "  <h1> Unlimited On-Demand Graph Databases with Cloudflare Durable Objects </h1> \n\nOct 27, 2025  \n\n<p>Content</p>"
        title = "Unlimited On-Demand Graph Databases with Cloudflare Durable Objects"
        result = _normalize_entry_content(content, title)
        assert "<h1>" not in result
        assert "Oct 27, 2025" in result
        assert "<p>Content</p>" in result

    def test_strips_h1_directly_at_start(self):
        """Strips h1 when it appears directly at content start (Sunil pattern)."""
        from src.main import _normalize_entry_content

        content = (
            "<h1>where good ideas come from (for coding agents)</h1> 3 January 2026  <p>Content</p>"
        )
        title = "where good ideas come from (for coding agents)"
        result = _normalize_entry_content(content, title)
        assert "<h1>" not in result
        assert "3 January 2026" in result
        assert "<p>Content</p>" in result

    def test_case_insensitive_matching(self):
        """Matches title case-insensitively."""
        from src.main import _normalize_entry_content

        content = "<h1>THE CONTEXT IS THE WORK</h1><p>Content</p>"
        title = "the context is the work"
        result = _normalize_entry_content(content, title)
        assert "<h1>" not in result
        assert "<p>Content</p>" in result

    def test_preserves_h1_when_title_doesnt_match(self):
        """Preserves h1 when title doesn't match heading text."""
        from src.main import _normalize_entry_content

        content = "<h1>Introduction</h1><p>Content</p>"
        title = "My Blog Post Title"
        result = _normalize_entry_content(content, title)
        assert "<h1>Introduction</h1>" in result
        assert "<p>Content</p>" in result

    def test_preserves_h1_in_middle_of_content(self):
        """Preserves h1 that appears in middle of content, not at start."""
        from src.main import _normalize_entry_content

        content = "<p>Intro paragraph</p><h1>My Title</h1><p>More content</p>"
        title = "My Title"
        result = _normalize_entry_content(content, title)
        assert "<h1>My Title</h1>" in result
        assert result == content

    def test_strips_h2_matching_title(self):
        """Strips h2 when it matches title."""
        from src.main import _normalize_entry_content

        content = "<h2>My Post Title</h2><p>Content here</p>"
        title = "My Post Title"
        result = _normalize_entry_content(content, title)
        assert "<h2>" not in result
        assert "<p>Content here</p>" in result

    def test_handles_empty_content(self):
        """Returns empty content unchanged."""
        from src.main import _normalize_entry_content

        result = _normalize_entry_content("", "Some Title")
        assert result == ""

    def test_handles_empty_title(self):
        """Returns content unchanged when title is empty."""
        from src.main import _normalize_entry_content

        content = "<h1>Heading</h1><p>Content</p>"
        result = _normalize_entry_content(content, "")
        assert result == content

    def test_handles_none_title(self):
        """Returns content unchanged when title is None."""
        from src.main import _normalize_entry_content

        content = "<h1>Heading</h1><p>Content</p>"
        result = _normalize_entry_content(content, None)
        assert result == content

    def test_strips_h1_with_link_wrapper(self):
        """Strips h1 containing a link-wrapped title."""
        from src.main import _normalize_entry_content

        content = '<h1><a href="https://example.com/post">My Post Title</a></h1><p>Content</p>'
        title = "My Post Title"
        result = _normalize_entry_content(content, title)
        assert "<h1>" not in result
        assert "<p>Content</p>" in result

    def test_preserves_content_without_headings(self):
        """Preserves content that has no h1/h2 headings."""
        from src.main import _normalize_entry_content

        content = "<p>Just a paragraph</p><p>Another paragraph</p>"
        title = "Some Title"
        result = _normalize_entry_content(content, title)
        assert result == content


# =============================================================================
# Theme-aware CSS Serving Tests
# =============================================================================


class _MinimalEnv:
    """Minimal mock environment for theme tests."""

    def __init__(self, theme: str | None = None):
        self.DB = _MockDB()
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = None
        self.DEAD_LETTER_QUEUE = None
        self.PLANET_NAME = "Test"
        self.SESSION_SECRET = "test-secret-key-for-testing-only"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"
        if theme is not None:
            self.THEME = theme


class _MockDB:
    """Minimal mock D1 database for theme tests."""

    def prepare(self, sql: str):
        return self

    def bind(self, *args):
        return self

    async def all(self):
        class _Result:
            results = []
            success = True

        return _Result()

    async def first(self):
        return None


# =============================================================================
# Conditional feed_links Tests
# =============================================================================


class TestFeedLinksConditionalSidebarRss:
    """Tests for conditional feed_links.sidebar_rss based on theme."""

    def test_planet_cloudflare_excludes_sidebar_links(self):
        """For planet-cloudflare theme, feed_links should NOT contain sidebar_rss or titles_only."""
        from src.main import _THEMES_HIDE_SIDEBAR_LINKS

        # Simulate the feed_links construction logic from _generate_html
        theme = "planet-cloudflare"
        feed_links: dict[str, str] = {
            "atom": "/feed.atom",
            "rss": "/feed.rss",
            "opml": "/feeds.opml",
        }
        if theme not in _THEMES_HIDE_SIDEBAR_LINKS:
            feed_links["sidebar_rss"] = "/feed.rss"
            feed_links["titles_only"] = "/titles"

        assert "sidebar_rss" not in feed_links
        assert "titles_only" not in feed_links
        # Base links should still be present
        assert "rss" in feed_links
        assert "atom" in feed_links
        assert "opml" in feed_links

    def test_default_theme_includes_sidebar_links(self):
        """For default theme, feed_links should contain sidebar_rss and titles_only."""
        from src.main import _THEMES_HIDE_SIDEBAR_LINKS

        theme = "default"
        feed_links: dict[str, str] = {
            "atom": "/feed.atom",
            "rss": "/feed.rss",
            "opml": "/feeds.opml",
        }
        if theme not in _THEMES_HIDE_SIDEBAR_LINKS:
            feed_links["sidebar_rss"] = "/feed.rss"
            feed_links["titles_only"] = "/titles"

        assert "sidebar_rss" in feed_links
        assert feed_links["sidebar_rss"] == "/feed.rss"
        assert "titles_only" in feed_links
        assert feed_links["titles_only"] == "/titles"

    def test_themes_hide_sidebar_links_contains_planet_cloudflare(self):
        """The _THEMES_HIDE_SIDEBAR_LINKS constant includes planet-cloudflare."""
        from src.main import _THEMES_HIDE_SIDEBAR_LINKS

        assert "planet-cloudflare" in _THEMES_HIDE_SIDEBAR_LINKS
        assert isinstance(_THEMES_HIDE_SIDEBAR_LINKS, frozenset)


class TestFeedLinksConditionalRss10:
    """Tests for conditional feed_links.rss10 based on theme."""

    def test_planet_mozilla_includes_rss10(self):
        """For planet-mozilla theme, feed_links should contain rss10."""
        from src.main import _THEMES_WITH_RSS10

        theme = "planet-mozilla"
        feed_links: dict[str, str] = {
            "atom": "/feed.atom",
            "rss": "/feed.rss",
            "opml": "/feeds.opml",
        }
        if theme in _THEMES_WITH_RSS10:
            feed_links["rss10"] = "/feed.rss10"

        assert "rss10" in feed_links
        assert feed_links["rss10"] == "/feed.rss10"

    def test_default_theme_excludes_rss10(self):
        """For default theme, feed_links should NOT contain rss10."""
        from src.main import _THEMES_WITH_RSS10

        theme = "default"
        feed_links: dict[str, str] = {
            "atom": "/feed.atom",
            "rss": "/feed.rss",
            "opml": "/feeds.opml",
        }
        if theme in _THEMES_WITH_RSS10:
            feed_links["rss10"] = "/feed.rss10"

        assert "rss10" not in feed_links

    def test_planet_cloudflare_excludes_rss10(self):
        """For planet-cloudflare theme, feed_links should NOT contain rss10."""
        from src.main import _THEMES_WITH_RSS10

        theme = "planet-cloudflare"
        feed_links: dict[str, str] = {
            "atom": "/feed.atom",
            "rss": "/feed.rss",
            "opml": "/feeds.opml",
        }
        if theme in _THEMES_WITH_RSS10:
            feed_links["rss10"] = "/feed.rss10"

        assert "rss10" not in feed_links

    def test_themes_with_rss10_is_frozenset(self):
        """The _THEMES_WITH_RSS10 constant is a frozenset containing planet-mozilla."""
        from src.main import _THEMES_WITH_RSS10

        assert isinstance(_THEMES_WITH_RSS10, frozenset)
        assert "planet-mozilla" in _THEMES_WITH_RSS10
