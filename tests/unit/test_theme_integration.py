# tests/unit/test_theme_integration.py
"""
Tests to ensure the theme system is properly integrated.

These tests verify that:
1. Each theme's templates are included in the generated templates.py
2. The render_template function accepts and uses the theme parameter
3. Theme-specific templates render different HTML than default
4. Templates receive all required variables
"""

import pytest

from templates import (
    _EMBEDDED_TEMPLATES,
    TEMPLATE_INDEX,
    TEMPLATE_SEARCH,
    TEMPLATE_TITLES,
    render_template,
)


class TestThemeTemplatesGenerated:
    """Verify that build_templates.py generated all expected themes."""

    def test_embedded_templates_has_default_theme(self):
        """Default theme must always exist."""
        assert "default" in _EMBEDDED_TEMPLATES
        assert TEMPLATE_INDEX in _EMBEDDED_TEMPLATES["default"]

    def test_embedded_templates_has_planet_mozilla_theme(self):
        """Planet Mozilla theme must be generated."""
        assert "planet-mozilla" in _EMBEDDED_TEMPLATES
        assert TEMPLATE_INDEX in _EMBEDDED_TEMPLATES["planet-mozilla"]

    def test_embedded_templates_has_planet_python_theme(self):
        """Planet Python theme must be generated."""
        assert "planet-python" in _EMBEDDED_TEMPLATES
        assert TEMPLATE_INDEX in _EMBEDDED_TEMPLATES["planet-python"]

    def test_embedded_templates_has_shared_templates(self):
        """Shared templates (feeds) must exist."""
        assert "_shared" in _EMBEDDED_TEMPLATES
        assert "feed.atom.xml" in _EMBEDDED_TEMPLATES["_shared"]
        assert "feed.rss.xml" in _EMBEDDED_TEMPLATES["_shared"]
        assert "feed.rss10.xml" in _EMBEDDED_TEMPLATES["_shared"]
        assert "feeds.opml" in _EMBEDDED_TEMPLATES["_shared"]

    def test_each_theme_has_required_templates(self):
        """Each theme must have index, search, and titles templates."""
        required_templates = [TEMPLATE_INDEX, TEMPLATE_SEARCH, TEMPLATE_TITLES]
        for theme in ["default", "planet-mozilla", "planet-python"]:
            for template in required_templates:
                assert template in _EMBEDDED_TEMPLATES[theme], (
                    f"Theme '{theme}' missing template '{template}'"
                )


class TestRenderTemplateThemeParameter:
    """Verify render_template uses the theme parameter correctly."""

    @pytest.fixture
    def minimal_context(self):
        """Minimal context required by all index templates."""
        return {
            "planet": {"name": "Test Planet", "description": "Test", "link": "/"},
            "entries_by_date": {},
            "feeds": [],
            "feed_links": {"atom": "/feed.atom", "rss": "/feed.rss", "opml": "/feeds.opml"},
            "generated_at": "2024-01-01 00:00 UTC",
            "is_lite_mode": False,
            "show_admin_link": False,
            "logo": None,
            "submission": None,
            "related_sites": None,
            "footer_text": "Test",
        }

    def test_render_template_accepts_theme_parameter(self, minimal_context):
        """render_template must accept theme as a keyword argument."""
        # Should not raise
        html = render_template(TEMPLATE_INDEX, theme="default", **minimal_context)
        assert html is not None
        assert len(html) > 0

    def test_render_template_with_planet_mozilla_theme(self, minimal_context):
        """render_template with planet-mozilla theme should use Mozilla templates."""
        # Add Mozilla-specific context
        minimal_context["date_labels"] = {}
        html = render_template(TEMPLATE_INDEX, theme="planet-mozilla", **minimal_context)
        assert html is not None
        # Mozilla template uses #header instead of <header>
        assert 'id="header"' in html or 'class="main-container"' in html

    def test_render_template_with_planet_python_theme(self, minimal_context):
        """render_template with planet-python theme should use Python templates."""
        # Add Python-specific context
        minimal_context["date_labels"] = {}
        html = render_template(TEMPLATE_INDEX, theme="planet-python", **minimal_context)
        assert html is not None
        # Python template uses specific structure
        assert 'id="logoheader"' in html or 'id="content-body"' in html

    def test_different_themes_produce_different_html(self, minimal_context):
        """Each theme should produce structurally different HTML."""
        minimal_context["date_labels"] = {}

        default_html = render_template(TEMPLATE_INDEX, theme="default", **minimal_context)
        mozilla_html = render_template(TEMPLATE_INDEX, theme="planet-mozilla", **minimal_context)
        python_html = render_template(TEMPLATE_INDEX, theme="planet-python", **minimal_context)

        # They should all be different (not just the same default template)
        assert default_html != mozilla_html, "Mozilla theme should differ from default"
        assert default_html != python_html, "Python theme should differ from default"
        assert mozilla_html != python_html, "Mozilla and Python themes should differ"


class TestTemplateVariableContracts:
    """Verify templates receive all required variables without errors."""

    @pytest.fixture
    def full_context(self):
        """Full context with all variables templates might need."""
        return {
            "planet": {
                "name": "Test Planet",
                "description": "Test desc",
                "link": "https://test.com",
            },
            "entries_by_date": {
                "January 1, 2024": [
                    {
                        "id": 1,
                        "title": "Test Entry",
                        "url": "https://example.com/post",
                        "content": "<p>Test content</p>",
                        "author": "Test Author",
                        "display_author": "Test Author",
                        "published_at": "2024-01-01T00:00:00Z",
                        "published_at_display": "00:00",
                        "feed_title": "Test Feed",
                    }
                ]
            },
            "feeds": [
                {
                    "id": 1,
                    "title": "Test Feed",
                    "url": "https://example.com/feed.xml",
                    "site_url": "https://example.com",
                    "is_healthy": True,
                }
            ],
            "feed_links": {
                "atom": "/feed.atom",
                "rss": "/feed.rss",
                "opml": "/feeds.opml",
                "titles_only": "/titles",
            },
            "generated_at": "2024-01-01 00:00 UTC",
            "is_lite_mode": False,
            "show_admin_link": True,
            "logo": None,
            "submission": None,
            "related_sites": None,
            "footer_text": "Powered by Planet CF",
            "date_labels": {"January 1, 2024": "Wednesday, January 1, 2024"},
        }

    @pytest.mark.parametrize("theme", ["default", "planet-mozilla", "planet-python"])
    def test_index_template_renders_without_undefined_errors(self, theme, full_context):
        """Index template should render without UndefinedError for any theme."""
        html = render_template(TEMPLATE_INDEX, theme=theme, **full_context)
        assert "Test Planet" in html
        assert "Test Entry" in html

    @pytest.mark.parametrize("theme", ["default", "planet-mozilla", "planet-python"])
    def test_search_template_renders_without_undefined_errors(self, theme):
        """Search template should render without UndefinedError."""
        context = {
            "planet": {"name": "Test", "description": "Test", "link": "/"},
            "query": "test query",
            "results": [],
            "logo": None,  # Some themes expect logo
            "feed_links": {"rss": "/feed.rss"},  # Some themes expect feed_links
        }
        html = render_template(TEMPLATE_SEARCH, theme=theme, **context)
        assert "test query" in html

    @pytest.mark.parametrize("theme", ["default", "planet-mozilla", "planet-python"])
    def test_titles_template_renders_without_undefined_errors(self, theme, full_context):
        """Titles template should render without UndefinedError."""
        html = render_template(TEMPLATE_TITLES, theme=theme, **full_context)
        assert "Test Planet" in html
