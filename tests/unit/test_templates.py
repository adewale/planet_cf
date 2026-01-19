# tests/unit/test_templates.py
"""Unit tests for template loading and rendering."""

import pytest

from src.templates import (
    ADMIN_JS,
    STATIC_CSS,
    TEMPLATE_ADMIN_DASHBOARD,
    TEMPLATE_ADMIN_LOGIN,
    TEMPLATE_FEED_ATOM,
    TEMPLATE_FEED_RSS,
    TEMPLATE_FEEDS_OPML,
    TEMPLATE_INDEX,
    TEMPLATE_SEARCH,
    render_template,
)

# =============================================================================
# Template Rendering Tests
# =============================================================================


class TestRenderTemplate:
    """Tests for render_template function."""

    def test_renders_index_template(self):
        """Index template renders without error."""
        html = render_template(
            TEMPLATE_INDEX,
            planet={"name": "Test Planet", "description": "A test planet"},
            entries_by_date={},
            feeds=[],
            generated_at="2026-01-01T00:00:00Z",
        )
        assert "Test Planet" in html
        assert "<!doctype html>" in html.lower()

    def test_renders_search_template(self):
        """Search template renders without error."""
        html = render_template(
            TEMPLATE_SEARCH,
            planet={"name": "Test Planet"},
            query="test query",
            results=[],
            search_time_ms=100,
        )
        assert "Test Planet" in html
        assert "test query" in html

    def test_renders_admin_dashboard(self):
        """Admin dashboard template renders without error."""
        html = render_template(
            TEMPLATE_ADMIN_DASHBOARD,
            planet={"name": "Test Planet"},
            admin={"display_name": "Admin User", "avatar_url": None},
            feeds=[],
            stats={"total_feeds": 0, "total_entries": 0, "healthy_feeds": 0},
        )
        assert "Test Planet" in html
        assert "Admin User" in html

    def test_renders_admin_login(self):
        """Admin login template renders without error."""
        html = render_template(
            TEMPLATE_ADMIN_LOGIN,
            planet={"name": "Test Planet"},
        )
        assert "Test Planet" in html
        assert "login" in html.lower()

    def test_renders_atom_feed(self):
        """Atom feed template renders valid XML."""
        xml = render_template(
            TEMPLATE_FEED_ATOM,
            planet={"name": "Test Planet", "url": "https://example.com", "description": "Test"},
            entries=[],
            generated_at="2026-01-01T00:00:00Z",
        )
        assert '<?xml version="1.0"' in xml
        assert "<feed" in xml
        assert "Test Planet" in xml

    def test_renders_rss_feed(self):
        """RSS feed template renders valid XML."""
        xml = render_template(
            TEMPLATE_FEED_RSS,
            planet={"name": "Test Planet", "url": "https://example.com", "description": "Test"},
            entries=[],
            generated_at="2026-01-01T00:00:00Z",
        )
        assert '<?xml version="1.0"' in xml
        assert "<rss" in xml
        assert "Test Planet" in xml

    def test_renders_opml(self):
        """OPML template renders valid XML."""
        xml = render_template(
            TEMPLATE_FEEDS_OPML,
            planet={"name": "Test Planet"},
            feeds=[],
            generated_at="2026-01-01T00:00:00Z",
        )
        assert '<?xml version="1.0"' in xml
        assert "<opml" in xml
        assert "Test Planet" in xml

    def test_missing_template_raises(self):
        """Missing template raises TemplateNotFound."""
        from jinja2 import TemplateNotFound

        with pytest.raises(TemplateNotFound):
            render_template("nonexistent.html")


class TestTemplateXSSPrevention:
    """Tests for XSS prevention via template autoescape."""

    def test_escapes_html_in_planet_name(self):
        """HTML in planet name is escaped."""
        html = render_template(
            TEMPLATE_INDEX,
            planet={"name": "<script>alert('xss')</script>", "description": "Safe"},
            entries_by_date={},
            feeds=[],
            generated_at="2026-01-01T00:00:00Z",
        )
        # Check that the XSS payload is escaped (not that there are no script tags,
        # since we have a legitimate inline script for keyboard navigation)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_html_in_search_query(self):
        """HTML in search query is escaped."""
        html = render_template(
            TEMPLATE_SEARCH,
            planet={"name": "Test"},
            query="<script>alert('xss')</script>",
            results=[],
            search_time_ms=100,
        )
        assert "<script>alert" not in html

    def test_admin_name_is_escaped(self):
        """HTML in admin display name is escaped."""
        html = render_template(
            TEMPLATE_ADMIN_DASHBOARD,
            planet={"name": "Test"},
            admin={"display_name": "<img src=x onerror=alert(1)>", "avatar_url": None},
            feeds=[],
            stats={"total_feeds": 0, "total_entries": 0, "healthy_feeds": 0},
        )
        # Check that the raw HTML tag is escaped (< becomes &lt;)
        # The text "onerror=" appears in escaped form as visible text, not as an attribute
        assert "&lt;img" in html
        # Make sure it's not an actual img tag with onerror attribute
        assert "<img src=x onerror" not in html


class TestTemplateEmptyEntries:
    """Tests for templates handling empty data."""

    def test_index_handles_empty_entries(self):
        """Index template handles empty entries gracefully."""
        html = render_template(
            TEMPLATE_INDEX,
            planet={"name": "Test", "description": "Test"},
            entries_by_date={},
            feeds=[],
            generated_at="2026-01-01T00:00:00Z",
        )
        assert "No entries yet" in html

    def test_search_handles_empty_results(self):
        """Search template handles empty results gracefully."""
        html = render_template(
            TEMPLATE_SEARCH,
            planet={"name": "Test"},
            query="nothing",
            results=[],
            search_time_ms=50,
        )
        assert "No results" in html or "0" in html


# =============================================================================
# Static Asset Tests
# =============================================================================


class TestStaticCSS:
    """Tests for embedded CSS."""

    def test_css_is_not_empty(self):
        """CSS content is not empty."""
        assert len(STATIC_CSS) > 100

    def test_css_contains_basic_rules(self):
        """CSS contains expected selectors."""
        assert "body" in STATIC_CSS
        assert "header" in STATIC_CSS

    def test_css_has_no_script_injection(self):
        """CSS doesn't contain script injection."""
        assert "<script>" not in STATIC_CSS.lower()
        assert "javascript:" not in STATIC_CSS.lower()


class TestAdminJS:
    """Tests for embedded admin JavaScript."""

    def test_js_is_not_empty(self):
        """JavaScript content is not empty."""
        assert len(ADMIN_JS) > 100

    def test_js_contains_functions(self):
        """JavaScript contains expected functions."""
        assert "function" in ADMIN_JS or "=>" in ADMIN_JS

    def test_js_no_eval(self):
        """JavaScript doesn't use eval (security)."""
        assert "eval(" not in ADMIN_JS


# =============================================================================
# Template Constant Tests
# =============================================================================


class TestTemplateConstants:
    """Tests for template name constants."""

    def test_template_constants_are_strings(self):
        """All template constants are strings."""
        assert isinstance(TEMPLATE_INDEX, str)
        assert isinstance(TEMPLATE_SEARCH, str)
        assert isinstance(TEMPLATE_ADMIN_DASHBOARD, str)
        assert isinstance(TEMPLATE_ADMIN_LOGIN, str)
        assert isinstance(TEMPLATE_FEED_ATOM, str)
        assert isinstance(TEMPLATE_FEED_RSS, str)
        assert isinstance(TEMPLATE_FEEDS_OPML, str)

    def test_template_constants_have_extensions(self):
        """Template constants have valid file extensions."""
        assert TEMPLATE_INDEX.endswith(".html")
        assert TEMPLATE_SEARCH.endswith(".html")
        assert TEMPLATE_ADMIN_DASHBOARD.endswith(".html")
        assert TEMPLATE_ADMIN_LOGIN.endswith(".html")
        assert TEMPLATE_FEED_ATOM.endswith(".xml")
        assert TEMPLATE_FEED_RSS.endswith(".xml")
        assert TEMPLATE_FEEDS_OPML.endswith(".opml")
