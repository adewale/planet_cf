# tests/unit/test_main_helpers.py
"""Unit tests for helper functions in main.py."""

import json

from src.main import (
    ERROR_MESSAGE_MAX_LENGTH,
    _extract_form_value,
    _feed_response,
    _html_response,
    _is_js_undefined,
    _json_error,
    _json_response,
    _log_op,
    _redirect_response,
    _safe_str,
    _to_d1_value,
    _to_py_list,
    _to_py_primitive,
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


class TestToPyPrimitive:
    """Tests for _to_py_primitive function."""

    def test_returns_none_for_none(self):
        """None returns None."""
        assert _to_py_primitive(None) is None

    def test_passes_through_basic_types(self):
        """Basic Python types are passed through."""
        assert _to_py_primitive(42) == 42
        assert _to_py_primitive(3.14) == 3.14
        assert _to_py_primitive("hello") == "hello"
        assert _to_py_primitive(True) is True
        assert _to_py_primitive(False) is False

    def test_converts_dict_recursively(self):
        """Dicts are converted recursively."""
        result = _to_py_primitive({"key": "value", "nested": {"a": 1}})
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_converts_list_recursively(self):
        """Lists are converted recursively."""
        result = _to_py_primitive([1, "two", {"three": 3}])
        assert result == [1, "two", {"three": 3}]

    def test_converts_tuple_to_list(self):
        """Tuples are converted to lists."""
        result = _to_py_primitive((1, 2, 3))
        assert result == [1, 2, 3]


class TestToPySafe:
    """Tests for _to_py_safe function."""

    def test_delegates_to_to_py_primitive(self):
        """_to_py_safe delegates to _to_py_primitive."""
        assert _to_py_safe(None) is None
        assert _to_py_safe(42) == 42
        assert _to_py_safe({"key": "value"}) == {"key": "value"}


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
    """Tests for _log_op function."""

    def test_prints_json(self, capsys):
        """Logs JSON to stdout."""
        _log_op("test_event", key="value", number=42)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["event_type"] == "test_event"
        assert output["key"] == "value"
        assert output["number"] == 42

    def test_includes_timestamp(self, capsys):
        """Log includes timestamp."""
        _log_op("test_event")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert "timestamp" in output


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
