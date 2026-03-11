# tests/unit/test_main_helpers.py
"""Unit tests for helper functions unique to main.py and wrappers.py.

Functions that live in src/utils.py are tested in test_utils.py.
This file covers:
- JS/Python boundary wrappers (src/wrappers.py)
- RateLimitError exception (src/main.py)
- Theme-aware feed link constants (src/main.py)
"""

from src.main import RateLimitError
from src.wrappers import (
    _extract_form_value,
    _is_js_undefined,
    _safe_str,
    _to_d1_value,
    _to_py_list,
    _to_py_safe,
)

# =============================================================================
# Type Conversion Tests (src/wrappers.py)
# =============================================================================


class TestIsJsUndefined:
    """Tests for _is_js_undefined function.

    Note: In non-Pyodide environment, _is_js_undefined checks for JsProxy
    undefined, not Python None. Python None is just None.
    """

    def test_returns_false_for_none_in_python(self):
        """Python None is not JS undefined (in non-Pyodide)."""
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

    def test_detects_jsnull_mock_in_pyodide_mode(self, monkeypatch):
        """JsNull objects are detected as undefined/null when HAS_PYODIDE is True."""
        import src.wrappers as wrappers_mod
        from tests.mocks.jsproxy import JsNullMock

        monkeypatch.setattr(wrappers_mod, "HAS_PYODIDE", True)
        js_null = JsNullMock()
        assert type(js_null).__name__ == "JsNull"
        assert _is_js_undefined(js_null) is True

    def test_to_py_safe_converts_jsnull_to_none(self, monkeypatch):
        """_to_py_safe should convert JsNull to Python None."""
        import src.wrappers as wrappers_mod
        from tests.mocks.jsproxy import JsNullMock

        monkeypatch.setattr(wrappers_mod, "HAS_PYODIDE", True)
        assert _to_py_safe(JsNullMock()) is None


class TestSafeStr:
    """Tests for _safe_str function."""

    def test_converts_value_to_string(self):
        assert _safe_str("hello") == "hello"
        assert _safe_str(123) == "123"
        assert _safe_str(3.14) == "3.14"

    def test_returns_none_for_none(self):
        assert _safe_str(None) is None

    def test_returns_empty_string_as_is(self):
        """Empty string is returned as-is (not converted to None)."""
        assert _safe_str("") == ""


class TestToPySafe:
    """Tests for _to_py_safe function."""

    def test_returns_none_for_none(self):
        assert _to_py_safe(None) is None

    def test_passes_through_basic_types(self):
        assert _to_py_safe(42) == 42
        assert _to_py_safe(3.14) == 3.14
        assert _to_py_safe("hello") == "hello"
        assert _to_py_safe(True) is True
        assert _to_py_safe(False) is False

    def test_converts_dict_recursively(self):
        result = _to_py_safe({"key": "value", "nested": {"a": 1}})
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_converts_list_recursively(self):
        result = _to_py_safe([1, "two", {"three": 3}])
        assert result == [1, "two", {"three": 3}]

    def test_converts_tuple_to_list(self):
        result = _to_py_safe((1, 2, 3))
        assert result == [1, 2, 3]

    def test_depth_guard_prevents_unbounded_recursion(self):
        """Deeply nested structures are handled without stack overflow."""
        from src.wrappers import _MAX_CONVERSION_DEPTH

        deep: dict | str = "leaf"
        for _i in range(100):
            deep = {"level": deep}

        result = _to_py_safe(deep)
        assert result is not None

        node = result
        for _ in range(_MAX_CONVERSION_DEPTH):
            assert isinstance(node, dict)
            node = node["level"]

        assert node is not None

    def test_depth_guard_returns_value_at_limit(self):
        """At exactly the depth limit, _to_py_safe returns value as-is."""
        from src.wrappers import _MAX_CONVERSION_DEPTH

        sentinel = {"key": "should_not_be_recursed"}
        result = _to_py_safe(sentinel, _depth=_MAX_CONVERSION_DEPTH)
        assert result is sentinel


class TestToPyList:
    """Tests for _to_py_list function."""

    def test_converts_list(self):
        result = _to_py_list([{"a": 1}, {"b": 2}])
        assert result == [{"a": 1}, {"b": 2}]

    def test_returns_empty_for_none(self):
        assert _to_py_list(None) == []

    def test_converts_empty_list(self):
        assert _to_py_list([]) == []


class TestToD1Value:
    """Tests for _to_d1_value function."""

    def test_passes_through_primitives(self):
        assert _to_d1_value(42) == 42
        assert _to_d1_value("hello") == "hello"
        assert _to_d1_value(3.14) == 3.14

    def test_handles_none(self):
        result = _to_d1_value(None)
        assert result is None


# =============================================================================
# Form Extraction Tests (src/wrappers.py)
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
        form = MockFormData({"name": "test"})
        assert _extract_form_value(form, "name") == "test"

    def test_handles_missing_key(self):
        form = MockFormData({})
        assert _extract_form_value(form, "missing") is None

    def test_handles_none_value(self):
        form = MockFormData({"empty": None})
        assert _extract_form_value(form, "empty") is None


# =============================================================================
# RateLimitError Tests (src/main.py)
# =============================================================================


class TestRateLimitError:
    """Tests for RateLimitError exception class."""

    def test_basic_creation(self):
        error = RateLimitError("Rate limited")
        assert str(error) == "Rate limited"
        assert error.retry_after is None

    def test_with_retry_after(self):
        error = RateLimitError("Rate limited", retry_after="3600")
        assert str(error) == "Rate limited"
        assert error.retry_after == "3600"

    def test_is_exception(self):
        error = RateLimitError("Rate limited")
        assert isinstance(error, Exception)

        try:
            raise error
        except RateLimitError as e:
            assert str(e) == "Rate limited"


# =============================================================================
# Conditional feed_links Tests (src/main.py)
# =============================================================================


class TestFeedLinksConditionalSidebarRss:
    """Tests for conditional feed_links.sidebar_rss based on theme."""

    def test_planet_cloudflare_excludes_sidebar_links(self):
        from src.main import _THEMES_HIDE_SIDEBAR_LINKS

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
        assert "rss" in feed_links
        assert "atom" in feed_links
        assert "opml" in feed_links

    def test_default_theme_includes_sidebar_links(self):
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
        from src.main import _THEMES_HIDE_SIDEBAR_LINKS

        assert "planet-cloudflare" in _THEMES_HIDE_SIDEBAR_LINKS
        assert isinstance(_THEMES_HIDE_SIDEBAR_LINKS, frozenset)


class TestFeedLinksConditionalRss10:
    """Tests for conditional feed_links.rss10 based on theme."""

    def test_planet_mozilla_includes_rss10(self):
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
        from src.main import _THEMES_WITH_RSS10

        assert isinstance(_THEMES_WITH_RSS10, frozenset)
        assert "planet-mozilla" in _THEMES_WITH_RSS10
