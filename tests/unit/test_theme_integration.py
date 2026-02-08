# tests/unit/test_theme_integration.py
"""
Tests to ensure the theme system is properly integrated.

These tests verify that:
1. Each theme's templates are included in the generated templates.py
2. The render_template function accepts and uses the theme parameter
3. Theme-specific templates render different HTML than default
4. Templates receive all required variables
"""

from pathlib import Path

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


# =============================================================================
# Static Assets Integrity Tests
# =============================================================================
# These tests prevent the CSS divergence bug that shipped wrong stylesheets.
# Two CSS files existed for planet-cloudflare (theme/style.css vs
# assets/static/style.css) with different content. Static Assets silently
# served the wrong one. These tests ensure that can never happen again.


class TestStaticAssetsIntegrity:
    """Verify static asset files exist and are consistent across instances."""

    PROJECT_ROOT = Path(__file__).parent.parent.parent

    # Every instance with a wrangler.jsonc that has an assets binding
    # must have these files in its assets/static/ directory.
    REQUIRED_STATIC_FILES = ["style.css", "keyboard-nav.js"]

    def _get_instance_dirs(self):
        """Return list of (name, path) for all deployable instances."""
        instances = []
        # Root instance (planetcf)
        root_wrangler = self.PROJECT_ROOT / "wrangler.jsonc"
        if root_wrangler.exists():
            instances.append(("root", self.PROJECT_ROOT))
        # Example instances
        examples_dir = self.PROJECT_ROOT / "examples"
        for wrangler in sorted(examples_dir.glob("*/wrangler.jsonc")):
            instances.append((wrangler.parent.name, wrangler.parent))
        return instances

    def _has_assets_binding(self, instance_dir):
        """Check if a wrangler.jsonc has an assets binding."""
        wrangler = instance_dir / "wrangler.jsonc"
        content = wrangler.read_text()
        return '"ASSETS"' in content

    def test_every_instance_has_style_css(self):
        """Every instance with an assets binding must have assets/static/style.css."""
        for name, path in self._get_instance_dirs():
            if not self._has_assets_binding(path):
                continue
            style = path / "assets" / "static" / "style.css"
            assert style.exists(), (
                f"Instance '{name}' has ASSETS binding but no assets/static/style.css. "
                f"Static Assets will return 404 for /static/style.css."
            )

    def test_default_theme_instances_have_keyboard_nav_js(self):
        """Instances using the default theme must have keyboard-nav.js.

        Replica themes (planet-python, planet-mozilla) don't include keyboard
        navigation because the original sites have no JavaScript at all.
        """
        # Instances that use the default theme and should have keyboard-nav.js
        default_theme_instances = ["root", "default", "planet-cloudflare", "test-planet"]
        for name, path in self._get_instance_dirs():
            if not self._has_assets_binding(path):
                continue
            js = path / "assets" / "static" / "keyboard-nav.js"
            if name in default_theme_instances:
                assert js.exists(), (
                    f"Instance '{name}' uses default theme but has no "
                    f"assets/static/keyboard-nav.js."
                )
            else:
                assert not js.exists(), (
                    f"Instance '{name}' is a replica theme and should NOT have "
                    f"keyboard-nav.js (the originals have no keyboard navigation)."
                )

    def test_no_divergent_theme_css(self):
        """If both theme/style.css and assets/static/style.css exist, they must match.

        Guards against leftover theme/ directories that could cause confusion.
        assets/static/style.css is the only file served by Workers Static Assets.
        """
        for name, path in self._get_instance_dirs():
            theme_css = path / "theme" / "style.css"
            assets_css = path / "assets" / "static" / "style.css"
            if theme_css.exists() and assets_css.exists():
                theme_content = theme_css.read_text()
                assets_content = assets_css.read_text()
                assert theme_content == assets_content, (
                    f"Instance '{name}': theme/style.css and assets/static/style.css "
                    f"have DIFFERENT content! Only assets/static/style.css is served "
                    f"by Workers Static Assets. Either sync them or delete theme/style.css."
                )

    def test_root_assets_match_planet_cloudflare(self):
        """Root assets/ must match examples/planet-cloudflare/assets/ for shared files.

        Root wrangler.jsonc deploys 'planetcf' using assets/ at the repo root.
        examples/planet-cloudflare/ has its own assets/. If both have style.css,
        they must match — otherwise updating one and forgetting the other
        silently deploys different CSS.
        """
        root_static = self.PROJECT_ROOT / "assets" / "static"
        pcf_static = self.PROJECT_ROOT / "examples" / "planet-cloudflare" / "assets" / "static"
        if not root_static.exists() or not pcf_static.exists():
            pytest.skip("One of root/planet-cloudflare assets dirs missing")

        for filename in ["style.css", "admin.js", "keyboard-nav.js"]:
            root_file = root_static / filename
            pcf_file = pcf_static / filename
            if root_file.exists() and pcf_file.exists():
                assert root_file.read_text() == pcf_file.read_text(), (
                    f"root assets/static/{filename} differs from "
                    f"examples/planet-cloudflare/assets/static/{filename}. "
                    f"Root wrangler.jsonc uses THEME='planet-cloudflare' but serves "
                    f"from assets/ at repo root, not examples/planet-cloudflare/assets/."
                )

    def test_default_theme_instances_match_canonical_css(self):
        """Instances using the default theme must have CSS matching templates/style.css.

        This prevents the bug where the canonical CSS (733 lines) diverged from
        the deployed CSS (333 lines), causing missing styles for keyboard shortcuts,
        search results, admin buttons, and content formatting.
        """
        canonical = self.PROJECT_ROOT / "templates" / "style.css"
        if not canonical.exists():
            pytest.skip("templates/style.css not found")
        canonical_content = canonical.read_text()

        # Instances that use the default theme CSS (no custom templates/style.css)
        default_theme_instances = [
            self.PROJECT_ROOT / "assets" / "static" / "style.css",  # root deployment
            self.PROJECT_ROOT / "examples" / "default" / "assets" / "static" / "style.css",
            self.PROJECT_ROOT
            / "examples"
            / "planet-cloudflare"
            / "assets"
            / "static"
            / "style.css",
            self.PROJECT_ROOT / "examples" / "test-planet" / "assets" / "static" / "style.css",
        ]

        for css_path in default_theme_instances:
            if css_path.exists():
                assert css_path.read_text() == canonical_content, (
                    f"{css_path.relative_to(self.PROJECT_ROOT)} differs from "
                    f"templates/style.css (the canonical source). "
                    f"Run: cp templates/style.css {css_path.relative_to(self.PROJECT_ROOT)}"
                )

    def test_css_files_are_not_empty(self):
        """CSS files must have actual content, not be empty placeholders."""
        for name, path in self._get_instance_dirs():
            css = path / "assets" / "static" / "style.css"
            if css.exists():
                content = css.read_text().strip()
                assert len(content) > 100, (
                    f"Instance '{name}': assets/static/style.css is suspiciously small "
                    f"({len(content)} chars). Expected a real stylesheet."
                )

    def test_css_has_valid_structure(self):
        """CSS files must contain valid CSS structure (not Python or HTML)."""
        for name, path in self._get_instance_dirs():
            css = path / "assets" / "static" / "style.css"
            if css.exists():
                content = css.read_text()
                # Should not contain Python artifacts
                assert "def " not in content, (
                    f"Instance '{name}': style.css contains 'def ' — "
                    f"looks like Python was written to a CSS file."
                )
                assert "import " not in content, (
                    f"Instance '{name}': style.css contains 'import ' — "
                    f"looks like Python was written to a CSS file."
                )
                # Should contain CSS
                assert "{" in content and "}" in content, (
                    f"Instance '{name}': style.css has no CSS rule blocks."
                )

    def test_admin_js_consistent_across_instances(self):
        """admin.js must be identical across all instances that have it.

        There is one canonical admin.js (static/admin.js at repo root).
        All copies in assets/static/ must match it.
        """
        canonical = self.PROJECT_ROOT / "static" / "admin.js"
        if not canonical.exists():
            pytest.skip("static/admin.js not found")
        canonical_content = canonical.read_text()

        for name, path in self._get_instance_dirs():
            admin_js = path / "assets" / "static" / "admin.js"
            if admin_js.exists():
                assert admin_js.read_text() == canonical_content, (
                    f"Instance '{name}': assets/static/admin.js differs from "
                    f"static/admin.js (the canonical source). They must match."
                )

    def test_keyboard_nav_js_consistent_across_instances(self):
        """keyboard-nav.js must be identical across all instances.

        There is one canonical keyboard-nav.js (templates/keyboard-nav.js).
        All copies in assets/static/ must match it.
        """
        canonical = self.PROJECT_ROOT / "templates" / "keyboard-nav.js"
        if not canonical.exists():
            pytest.skip("templates/keyboard-nav.js not found")
        canonical_content = canonical.read_text()

        for name, path in self._get_instance_dirs():
            kb_js = path / "assets" / "static" / "keyboard-nav.js"
            if kb_js.exists():
                assert kb_js.read_text() == canonical_content, (
                    f"Instance '{name}': assets/static/keyboard-nav.js differs from "
                    f"templates/keyboard-nav.js (the canonical source). They must match."
                )
