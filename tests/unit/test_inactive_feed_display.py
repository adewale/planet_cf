"""Tests for inactive feed display behavior.

Verifies that is_active controls fetching only, not display.
Inactive feeds should remain visible in the sidebar with a visual indicator,
and their cached entries should still appear in the main content area.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestInactiveFeedDisplayQueries:
    """Verify that display queries do NOT filter by is_active."""

    def _get_main_source(self):
        return (PROJECT_ROOT / "src" / "main.py").read_text()

    def test_sidebar_query_includes_inactive_feeds(self):
        """Sidebar feeds query must NOT filter by is_active."""
        source = self._get_main_source()
        # Find the sidebar feeds query (SELECT ... FROM feeds ... ORDER BY title)
        # It should include is_active in SELECT but NOT in WHERE
        sidebar_match = re.search(
            r"# Get feeds for sidebar.*?ORDER BY title",
            source,
            re.DOTALL,
        )
        assert sidebar_match, "Could not find sidebar feeds query"
        query = sidebar_match.group()
        assert "is_active" in query, "Sidebar query should SELECT is_active"
        assert "WHERE is_active = 1" not in query, (
            "Sidebar query must NOT filter by is_active = 1. "
            "Inactive feeds should be visible with a CSS indicator."
        )

    def test_entries_query_includes_inactive_feeds(self):
        """Main entries query must NOT filter by f.is_active."""
        source = self._get_main_source()
        # Find the main entries CTE query
        entries_match = re.search(
            r"WITH ranked AS.*?LIMIT \?",
            source,
            re.DOTALL,
        )
        assert entries_match, "Could not find main entries query"
        # Get just the first CTE (not the fallback)
        query = entries_match.group()
        assert "f.is_active = 1" not in query, (
            "Entries query must NOT filter by f.is_active = 1. "
            "Cached entries from inactive feeds should still be displayed."
        )

    def test_recent_entries_query_no_is_active_filter(self):
        """_get_recent_entries() (Atom/RSS) must NOT filter by is_active."""
        source = self._get_main_source()
        match = re.search(
            r"async def _get_recent_entries.*?\.all\(\)",
            source,
            re.DOTALL,
        )
        assert match, "Could not find _get_recent_entries method"
        query = match.group()
        assert "is_active" not in query, "_get_recent_entries must NOT filter by is_active."

    def test_opml_export_includes_all_feeds(self):
        """OPML export must include inactive feeds."""
        source = self._get_main_source()
        match = re.search(
            r"async def _export_opml.*?\.all\(\)",
            source,
            re.DOTALL,
        )
        assert match, "Could not find _export_opml method"
        query = match.group()
        assert "is_active" not in query, "OPML export must NOT filter by is_active."

    def test_scheduler_still_filters_by_is_active(self):
        """Regression: scheduler enqueue query MUST keep WHERE is_active = 1."""
        source = self._get_main_source()
        match = re.search(
            r"# Get all active feeds from D1.*?\.all\(\)",
            source,
            re.DOTALL,
        )
        assert match, "Could not find scheduler feeds query"
        query = match.group()
        assert "WHERE is_active = 1" in query, (
            "Scheduler query MUST filter by is_active = 1. "
            "Only active feeds should be enqueued for fetching."
        )


class TestInactiveFeedTemplates:
    """Verify templates render inactive feeds with correct CSS class."""

    def test_default_theme_has_feed_inactive_class(self):
        """Default theme template should render feed-inactive class."""
        template = (PROJECT_ROOT / "examples" / "default" / "templates" / "index.html").read_text()
        assert "feed-inactive" in template
        assert "is_inactive" in template

    def test_planet_python_has_feed_inactive_class(self):
        """Planet Python template should render feed-inactive class."""
        template = (
            PROJECT_ROOT / "examples" / "planet-python" / "templates" / "index.html"
        ).read_text()
        assert "feed-inactive" in template

    def test_planet_mozilla_has_feed_inactive_class(self):
        """Planet Mozilla template should render feed-inactive class."""
        template = (
            PROJECT_ROOT / "examples" / "planet-mozilla" / "templates" / "index.html"
        ).read_text()
        assert "feed-inactive" in template

    def test_compiled_templates_have_feed_inactive(self):
        """Compiled templates.py should contain feed-inactive for all themes."""
        templates = (PROJECT_ROOT / "src" / "templates.py").read_text()
        # Should appear at least 3 times (once per theme)
        count = templates.count("feed-inactive")
        assert count >= 3, f"Expected feed-inactive in at least 3 themes, found {count} occurrences"


class TestInactiveFeedCSS:
    """Verify all theme CSS files have .feed-inactive rule."""

    CSS_FILES = [
        "assets/static/style.css",
        "examples/default/assets/static/style.css",
        "examples/planet-cloudflare/assets/static/style.css",
        "examples/test-planet/assets/static/style.css",
        "examples/planet-python/assets/static/style.css",
        "examples/planet-mozilla/assets/static/style.css",
    ]

    def test_all_theme_css_has_feed_inactive(self):
        """Every theme CSS file must contain a .feed-inactive rule."""
        for css_path in self.CSS_FILES:
            full_path = PROJECT_ROOT / css_path
            assert full_path.exists(), f"CSS file not found: {css_path}"
            content = full_path.read_text()
            assert "feed-inactive" in content, f"{css_path} is missing .feed-inactive CSS rule"

    def test_feed_inactive_uses_opacity(self):
        """The .feed-inactive rule should use opacity for visual dimming."""
        for css_path in self.CSS_FILES:
            content = (PROJECT_ROOT / css_path).read_text()
            if "feed-inactive" in content:
                # Find the rule block
                match = re.search(r"\.feed-inactive\s*\{[^}]*\}", content)
                if match:
                    assert "opacity" in match.group(), (
                        f"{css_path}: .feed-inactive rule should use opacity"
                    )
