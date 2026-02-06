#!/usr/bin/env python3
"""
Build script to compile HTML/CSS templates into src/templates.py

This is necessary because Cloudflare Workers Python runs in WebAssembly
and doesn't have filesystem access for loading templates at runtime.

Usage:
    python scripts/build_templates.py
    python scripts/build_templates.py --theme planet-python
    python scripts/build_templates.py --theme dark
    python scripts/build_templates.py --example planet-mozilla

Options:
    --theme <name>    Use CSS from themes/<name>/style.css
    --example <name>  Use CSS from examples/<name>/theme/style.css

Theme resolution order:
  1. examples/<name>/theme/style.css (if --example is used)
  2. themes/<name>/style.css (if --theme is used)
  3. themes/default/style.css (fallback)

After editing any file in templates/, run this script to regenerate
src/templates.py, then deploy with `wrangler deploy`.
"""

import argparse
import sys
from pathlib import Path

# Directories relative to this script
PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "templates"
THEMES_DIR = PROJECT_ROOT / "themes"
EXAMPLES_DIR = PROJECT_ROOT / "examples"
OUTPUT_FILE = PROJECT_ROOT / "src" / "templates.py"

# Per-theme template directories (now under examples/)
THEME_TEMPLATE_DIRS = ["default", "planet-python", "planet-mozilla"]

# Template files that vary per theme (relative to theme dir)
THEMED_TEMPLATE_FILES = [
    "index.html",
    "titles.html",
    "search.html",
]

# Admin templates (only in default)
ADMIN_TEMPLATE_FILES = [
    "admin/dashboard.html",
    "admin/error.html",
    "admin/health.html",
    "admin/login.html",
]

# Shared template files (no theme variations, at TEMPLATE_DIR root)
SHARED_TEMPLATE_FILES = [
    "feed.atom.xml",
    "feed.rss.xml",
    "feed.rss10.xml",
    "feeds.opml",
]

CSS_FILE = "style.css"
KEYBOARD_NAV_JS_FILE = "keyboard-nav.js"


def read_template(path: Path) -> str:
    """Read a template file and return its contents."""
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def escape_for_python(content: str) -> str:
    """Escape content for embedding in a Python triple-quoted string."""
    # We use triple quotes, so we need to escape any triple quotes in content
    return content.replace('"""', r"\"\"\"")


def get_theme_css(
    theme: str | None, example: str | None = None, fallback: bool = True
) -> tuple[str, str]:
    """Get CSS content for the specified theme or example.

    Args:
        theme: Theme name (e.g., 'planet-python', 'dark') or None for default.
        example: Example name (e.g., 'planet-mozilla'). If provided, check
                 examples/<name>/theme/style.css first.
        fallback: If True (default), fall back to 'default' theme when specified
                  theme doesn't exist. If False, raise FileNotFoundError.

    Returns:
        Tuple of (css_content, source_description)

    Resolution order:
      1. examples/<example>/theme/style.css (if example is provided)
      2. themes/<theme>/style.css (if theme is provided)
      3. themes/default/style.css (fallback)
    """
    # First, check examples directory if example is specified
    if example:
        example_css_path = EXAMPLES_DIR / example / "theme" / "style.css"
        if example_css_path.exists():
            return example_css_path.read_text(
                encoding="utf-8"
            ), f"examples/{example}/theme/style.css"
        else:
            # List available examples for helpful message
            available_examples = [
                d.name
                for d in EXAMPLES_DIR.iterdir()
                if d.is_dir() and (d / "theme" / "style.css").exists()
            ]
            if fallback:
                print(
                    f"Warning: Example '{example}' theme not found at {example_css_path}\n"
                    f"  Available examples with themes: {', '.join(sorted(available_examples))}\n"
                    f"  Falling back to 'default' theme.",
                    file=sys.stderr,
                )
            else:
                raise FileNotFoundError(
                    f"Example '{example}' theme not found at {example_css_path}\n"
                    f"Available examples with themes: {', '.join(sorted(available_examples))}"
                )

    # Then check themes directory
    if theme and theme != "default":
        theme_css_path = THEMES_DIR / theme / "style.css"
        if theme_css_path.exists():
            return theme_css_path.read_text(encoding="utf-8"), f"themes/{theme}/style.css"
        else:
            # List available themes for helpful message
            available = [
                d.name for d in THEMES_DIR.iterdir() if d.is_dir() and (d / "style.css").exists()
            ]

            if fallback:
                # Smart default: Fall back to default theme
                print(
                    f"Warning: Theme '{theme}' not found at {theme_css_path}\n"
                    f"  Available themes: {', '.join(sorted(available))}\n"
                    f"  Falling back to 'default' theme.",
                    file=sys.stderr,
                )
                default_css_path = THEMES_DIR / "default" / "style.css"
                if default_css_path.exists():
                    return default_css_path.read_text(
                        encoding="utf-8"
                    ), "themes/default/style.css (fallback)"
                # Ultimate fallback: use templates/style.css
                return read_template(TEMPLATE_DIR / CSS_FILE), "templates/style.css (fallback)"
            else:
                raise FileNotFoundError(
                    f"Theme '{theme}' not found at {theme_css_path}\n"
                    f"Available themes: {', '.join(sorted(available))}"
                )
    # Default: use templates/style.css
    return read_template(TEMPLATE_DIR / CSS_FILE), "templates/style.css"


def build_templates(theme: str | None = None, example: str | None = None):
    """Generate src/templates.py from template files.

    Args:
        theme: Optional theme name. If provided, CSS is loaded from
               themes/<name>/style.css instead of templates/style.css.
        example: Optional example name. If provided, CSS is loaded from
               examples/<name>/theme/style.css first.
    """

    # Read all templates organized by theme
    themed_templates: dict[str, dict[str, str]] = {}

    # Read theme-specific templates from examples/<theme>/templates/
    for theme_name in THEME_TEMPLATE_DIRS:
        theme_dir = EXAMPLES_DIR / theme_name / "templates"
        if not theme_dir.exists():
            print(f"Warning: Theme directory not found: {theme_dir}", file=sys.stderr)
            continue

        themed_templates[theme_name] = {}

        # Read themed templates
        for template_file in THEMED_TEMPLATE_FILES:
            template_path = theme_dir / template_file
            if template_path.exists():
                themed_templates[theme_name][template_file] = read_template(template_path)

        # Admin templates only in default
        if theme_name == "default":
            for template_file in ADMIN_TEMPLATE_FILES:
                template_path = theme_dir / template_file
                if template_path.exists():
                    themed_templates[theme_name][template_file] = read_template(template_path)

    # Read shared templates (no theme variations)
    shared_templates: dict[str, str] = {}
    for template_file in SHARED_TEMPLATE_FILES:
        template_path = TEMPLATE_DIR / template_file
        if template_path.exists():
            shared_templates[template_file] = read_template(template_path)

    # Read CSS (from example, theme, or default)
    css_content, css_source = get_theme_css(theme, example)

    # Read keyboard navigation JS
    keyboard_nav_js = read_template(TEMPLATE_DIR / KEYBOARD_NAV_JS_FILE)

    # Generate Python code
    output = '''# src/templates.py
# AUTO-GENERATED - DO NOT EDIT DIRECTLY
# Edit files in templates/ and run: python scripts/build_templates.py
"""
Template loading and rendering utilities for Planet CF.

This module provides:
- A shared Jinja2 Environment for rendering templates
- Embedded templates for Workers environment compatibility
- Per-theme template support with fallback chain
- Helper functions for common rendering patterns
"""

from jinja2 import BaseLoader, Environment, TemplateNotFound

# =============================================================================
# Embedded Templates (for Workers environment)
# =============================================================================
# Structure:
#   _EMBEDDED_TEMPLATES[theme_name][template_name] = template_content
#   _EMBEDDED_TEMPLATES["_shared"][template_name] = shared_template_content

_EMBEDDED_TEMPLATES = {
'''

    # Add themed templates
    for theme_name, templates in themed_templates.items():
        output += f'    "{theme_name}": {{\n'
        for name, content in templates.items():
            escaped = escape_for_python(content)
            output += f'        "{name}": """{escaped}""",\n'
        output += "    },\n"

    # Add shared templates
    output += '    "_shared": {\n'
    for name, content in shared_templates.items():
        escaped = escape_for_python(content)
        output += f'        "{name}": """{escaped}""",\n'
    output += "    },\n"

    output += '''}

STATIC_CSS = """'''
    output += escape_for_python(css_content)
    output += '''"""

KEYBOARD_NAV_JS = """'''
    output += escape_for_python(keyboard_nav_js)
    output += '''"""

'''

    # Add the rest of the module (loader, environment, helpers)
    output += '''
# =============================================================================
# Admin JavaScript (for Workers environment)
# =============================================================================


ADMIN_JS = """
// Admin dashboard functionality

// XSS protection helper
function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', function() {
    // Tab switching
    document.querySelectorAll('.tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            var target = this.dataset.tab;
            document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
            this.classList.add('active');
            document.getElementById(target).classList.add('active');
            if (target === 'dlq') loadDLQ();
            if (target === 'audit') loadAuditLog();
        });
    });

    // Feed toggles
    document.querySelectorAll('.feed-toggle').forEach(function(toggle) {
        toggle.addEventListener('change', function() {
            var feedId = this.dataset.feedId;
            var isActive = this.checked;
            fetch('/admin/feeds/' + feedId + '/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: isActive })
            });
        });
    });

    // Feed title editing
    document.querySelectorAll('.feed-title-text').forEach(function(titleText) {
        titleText.addEventListener('click', function() {
            var container = this.closest('.feed-title');
            container.classList.add('editing');
            var input = container.querySelector('.feed-title-input');
            input.focus();
            input.select();
        });
    });

    document.querySelectorAll('.save-title-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var container = this.closest('.feed-title');
            var feedId = container.dataset.feedId;
            var input = container.querySelector('.feed-title-input');
            var titleText = container.querySelector('.feed-title-text');
            var newTitle = input.value.trim();

            fetch('/admin/feeds/' + feedId, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    titleText.textContent = newTitle || 'Untitled';
                    container.classList.remove('editing');
                } else {
                    alert('Failed to update title');
                }
            })
            .catch(function() {
                alert('Failed to update title');
            });
        });
    });

    document.querySelectorAll('.cancel-title-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var container = this.closest('.feed-title');
            var input = container.querySelector('.feed-title-input');
            var titleText = container.querySelector('.feed-title-text');
            input.value = titleText.textContent === 'Untitled' ? '' : titleText.textContent;
            container.classList.remove('editing');
        });
    });

    // Handle Enter/Escape in title input
    document.querySelectorAll('.feed-title-input').forEach(function(input) {
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.closest('.feed-title').querySelector('.save-title-btn').click();
            }
            if (e.key === 'Escape') {
                this.closest('.feed-title').querySelector('.cancel-title-btn').click();
            }
        });
    });
});

function loadDLQ() {
    fetch('/admin/dlq')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var list = document.getElementById('dlq-list');
            if (!data.feeds || data.feeds.length === 0) {
                list.innerHTML = '<p class="empty-state">No failed feeds</p>';
                return;
            }
            list.innerHTML = data.feeds.map(function(f) {
                return '<div class="dlq-item">' +
                    '<strong>' + escapeHtml(f.title || 'Untitled') + '</strong><br>' +
                    '<small>' + escapeHtml(f.url) + '</small><br>' +
                    '<small>Failures: ' + f.consecutive_failures + '</small>' +
                    '<form action="/admin/dlq/' + f.id + '/retry" method="POST" style="margin-top:0.5rem">' +
                    '<button type="submit" class="btn btn-sm btn-warning">Retry</button></form>' +
                    '</div>';
            }).join('');
        });
}

function loadAuditLog() {
    fetch('/admin/audit')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var list = document.getElementById('audit-list');
            if (!data.entries || data.entries.length === 0) {
                list.innerHTML = '<p class="empty-state">No audit entries</p>';
                return;
            }
            list.innerHTML = data.entries.map(function(e) {
                return '<div class="audit-item">' +
                    '<span class="audit-action">' + escapeHtml(e.action) + '</span> ' +
                    '<span class="audit-time">' + escapeHtml(e.created_at) + '</span>' +
                    (e.details ? '<div class="audit-details">' + escapeHtml(e.details) + '</div>' : '') +
                    '</div>';
            }).join('');
        });
}

function rebuildSearchIndex() {
    var btn = document.getElementById('reindex-btn');
    var originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Rebuilding...';
    btn.style.opacity = '0.7';

    fetch('/admin/reindex', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        btn.disabled = false;
        btn.style.opacity = '1';
        if (data.success) {
            btn.textContent = 'Done! (' + data.indexed + ' indexed)';
            setTimeout(function() { btn.textContent = originalText; }, 3000);
        } else {
            btn.textContent = 'Error: ' + (data.error || 'Unknown');
            setTimeout(function() { btn.textContent = originalText; }, 3000);
        }
    })
    .catch(function(err) {
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.textContent = 'Error';
        setTimeout(function() { btn.textContent = originalText; }, 3000);
    });
}
"""


# =============================================================================
# Template Loader and Environment
# =============================================================================


class EmbeddedLoader(BaseLoader):
    """Jinja2 loader that loads templates from embedded strings with theme fallback."""

    def __init__(self, theme: str = "default"):
        """Initialize loader with a theme.

        Args:
            theme: Theme name to use for template lookup.
                   Falls back to "default" then "_shared".
        """
        self.theme = theme

    def get_source(self, environment, template):
        """Get template source with fallback chain.

        Lookup order:
          1. _EMBEDDED_TEMPLATES[theme][template]
          2. _EMBEDDED_TEMPLATES["default"][template]
          3. _EMBEDDED_TEMPLATES["_shared"][template]
        """
        # Try theme-specific template
        if self.theme in _EMBEDDED_TEMPLATES and template in _EMBEDDED_TEMPLATES[self.theme]:
            source = _EMBEDDED_TEMPLATES[self.theme][template]
            return source, f"{self.theme}/{template}", lambda: True

        # Fall back to default theme
        if (
            self.theme != "default"
            and "default" in _EMBEDDED_TEMPLATES
            and template in _EMBEDDED_TEMPLATES["default"]
        ):
            source = _EMBEDDED_TEMPLATES["default"][template]
            return source, f"default/{template}", lambda: True

        # Fall back to shared templates
        if "_shared" in _EMBEDDED_TEMPLATES and template in _EMBEDDED_TEMPLATES["_shared"]:
            source = _EMBEDDED_TEMPLATES["_shared"][template]
            return source, f"_shared/{template}", lambda: True

        raise TemplateNotFound(template)


# Cache of Jinja2 environments per theme
_jinja_envs: dict[str, Environment] = {}


def get_jinja_env(theme: str = "default") -> Environment:
    """Get or create a Jinja2 environment for the given theme.

    Args:
        theme: Theme name (e.g., "planet-python", "planet-mozilla", "default")

    Returns:
        Configured Jinja2 Environment with theme-aware template loader.
    """
    if theme not in _jinja_envs:
        _jinja_envs[theme] = Environment(loader=EmbeddedLoader(theme), autoescape=True)
    return _jinja_envs[theme]


def render_template(name: str, theme: str = "default", **context) -> str:
    """Render a template with the given context.

    Args:
        name: Template name (e.g., "index.html", "admin/dashboard.html")
        theme: Theme to use for template lookup (default: "default")
        **context: Template context variables

    Returns:
        Rendered template as string.
    """
    env = get_jinja_env(theme)
    template = env.get_template(name)
    return template.render(**context)


# Template name constants for type safety
TEMPLATE_INDEX = "index.html"
TEMPLATE_TITLES = "titles.html"
TEMPLATE_SEARCH = "search.html"
TEMPLATE_ADMIN_DASHBOARD = "admin/dashboard.html"
TEMPLATE_ADMIN_ERROR = "admin/error.html"
TEMPLATE_ADMIN_LOGIN = "admin/login.html"
TEMPLATE_FEED_HEALTH = "admin/health.html"
TEMPLATE_FEED_ATOM = "feed.atom.xml"
TEMPLATE_FEED_RSS = "feed.rss.xml"
TEMPLATE_FEED_RSS10 = "feed.rss10.xml"
TEMPLATE_FEEDS_OPML = "feeds.opml"

# =============================================================================
# Theme-specific CSS and Logos (for multi-instance deployments)
# =============================================================================

THEME_CSS = {
'''

    # Add theme-specific CSS from examples
    example_themes = {
        "planet-cloudflare": EXAMPLES_DIR / "planet-cloudflare" / "theme" / "style.css",
        "planet-python": EXAMPLES_DIR / "planet-python" / "theme" / "style.css",
        "planet-mozilla": EXAMPLES_DIR / "planet-mozilla" / "theme" / "style.css",
    }
    for theme_name, css_path in example_themes.items():
        if css_path.exists():
            theme_css_content = css_path.read_text(encoding="utf-8")
            output += f'    "{theme_name}": """{escape_for_python(theme_css_content)}""",\n'

    output += """}

THEME_LOGOS = {
"""

    # Add theme-specific logos from examples
    # For visual fidelity, we use actual downloaded images (served via THEME_ASSETS)
    # but also keep SVG fallback for legacy support
    logo_configs = {
        "planet-python": {
            "svg_path": EXAMPLES_DIR / "planet-python" / "static" / "python-logo.svg",
            "url": "/static/images/python-logo.gif",  # Original path from planetpython.org
            "width": "211",
            "height": "71",
            "alt": "Planet Python",
        },
        "planet-mozilla": {
            "svg_path": EXAMPLES_DIR / "planet-mozilla" / "static" / "mozilla-logo.svg",
            "url": "/static/img/logo.png",  # Original path from planet.mozilla.org
            "width": "222",
            "height": "44",
            "alt": "Planet Mozilla",
        },
    }
    for theme_name, config in logo_configs.items():
        svg_path = config["svg_path"]
        svg_content = ""
        if svg_path.exists():
            svg_content = svg_path.read_text(encoding="utf-8")
        output += f'''    "{theme_name}": {{
        "url": "{config["url"]}",
        "width": "{config["width"]}",
        "height": "{config["height"]}",
        "alt": "{config["alt"]}",
        "svg": """{escape_for_python(svg_content)}""",
    }},
'''

    output += """}

# Static assets are served via Cloudflare's ASSETS binding.
# Each example has an assets/ directory configured in wrangler.jsonc.
THEME_ASSETS = {}
"""

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(output, encoding="utf-8")

    # Count templates
    total_templates = sum(len(t) for t in themed_templates.values()) + len(shared_templates)

    print(f"Generated {OUTPUT_FILE}")
    print(f"  - {len(themed_templates)} themes: {', '.join(themed_templates.keys())}")
    print(f"  - {total_templates} total templates")
    print(f"  - {len(shared_templates)} shared templates")
    print(f"  - {len(css_content)} bytes of CSS from {css_source}")


def list_available_themes() -> list[str]:
    """Return list of available theme names."""
    if not THEMES_DIR.exists():
        return []
    return sorted(
        [d.name for d in THEMES_DIR.iterdir() if d.is_dir() and (d / "style.css").exists()]
    )


def list_available_examples() -> list[str]:
    """Return list of available example names with themes."""
    if not EXAMPLES_DIR.exists():
        return []
    return sorted(
        [
            d.name
            for d in EXAMPLES_DIR.iterdir()
            if d.is_dir() and (d / "theme" / "style.css").exists()
        ]
    )


def main():
    """Parse arguments and build templates."""
    available_themes = list_available_themes()
    available_examples = list_available_examples()

    theme_help = (
        f"Theme to use for CSS. Loads CSS from themes/<name>/style.css. "
        f"Available: {', '.join(available_themes) if available_themes else 'none found'}"
    )
    example_help = (
        f"Example to use for CSS. Loads CSS from examples/<name>/theme/style.css. "
        f"Available: {', '.join(available_examples) if available_examples else 'none found'}"
    )

    parser = argparse.ArgumentParser(
        description="Build HTML/CSS templates into src/templates.py for Cloudflare Workers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default CSS from templates/style.css
  python scripts/build_templates.py

  # Use Planet Python theme from themes/
  python scripts/build_templates.py --theme planet-python

  # Use Planet Mozilla example from examples/
  python scripts/build_templates.py --example planet-mozilla

  # Use dark theme
  python scripts/build_templates.py --theme dark
""",
    )
    parser.add_argument(
        "--theme",
        "-t",
        metavar="NAME",
        help=theme_help,
    )
    parser.add_argument(
        "--example",
        "-e",
        metavar="NAME",
        help=example_help,
    )
    parser.add_argument(
        "--list-themes",
        action="store_true",
        help="List available themes and examples and exit",
    )

    args = parser.parse_args()

    if args.list_themes:
        print("Available themes (themes/<name>/style.css):")
        for theme in available_themes:
            print(f"  - {theme}")
        print("\nAvailable examples (examples/<name>/theme/style.css):")
        for example in available_examples:
            print(f"  - {example}")
        return

    try:
        build_templates(theme=args.theme, example=args.example)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
