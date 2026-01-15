#!/usr/bin/env python3
"""
Build script to compile HTML/CSS templates into src/templates.py

This is necessary because Cloudflare Workers Python runs in WebAssembly
and doesn't have filesystem access for loading templates at runtime.

Usage:
    python scripts/build_templates.py

After editing any file in templates/, run this script to regenerate
src/templates.py, then deploy with `wrangler deploy`.
"""

from pathlib import Path

# Template directory relative to this script
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_FILE = Path(__file__).parent.parent / "src" / "templates.py"

# Template files to include (relative to TEMPLATE_DIR)
TEMPLATE_FILES = [
    "index.html",
    "search.html",
    "admin/dashboard.html",
    "admin/login.html",
    "feed.atom.xml",
    "feed.rss.xml",
    "feeds.opml",
]

CSS_FILE = "style.css"


def read_template(name: str) -> str:
    """Read a template file and return its contents."""
    path = TEMPLATE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def escape_for_python(content: str) -> str:
    """Escape content for embedding in a Python triple-quoted string."""
    # We use triple quotes, so we need to escape any triple quotes in content
    return content.replace('"""', r"\"\"\"")


def build_templates():
    """Generate src/templates.py from template files."""

    # Read all templates
    templates = {}
    for name in TEMPLATE_FILES:
        templates[name] = read_template(name)

    # Read CSS
    css_content = read_template(CSS_FILE)

    # Generate Python code
    output = '''# src/templates.py
# AUTO-GENERATED - DO NOT EDIT DIRECTLY
# Edit files in templates/ and run: python scripts/build_templates.py
"""
Template loading and rendering utilities for Planet CF.

This module provides:
- A shared Jinja2 Environment for rendering templates
- Embedded templates for Workers environment compatibility
- Helper functions for common rendering patterns
"""

from jinja2 import BaseLoader, Environment, TemplateNotFound

# =============================================================================
# Embedded Templates (for Workers environment)
# =============================================================================

_EMBEDDED_TEMPLATES = {
'''

    # Add each template
    for name, content in templates.items():
        escaped = escape_for_python(content)
        output += f'    "{name}": """{escaped}""",\n'

    output += '''}

STATIC_CSS = """'''
    output += escape_for_python(css_content)
    output += '''"""

'''

    # Add the rest of the module (loader, environment, helpers)
    output += '''
# =============================================================================
# Admin JavaScript (for Workers environment)
# =============================================================================

ADMIN_JS = """
// Admin dashboard functionality
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
                    '<strong>' + (f.title || 'Untitled') + '</strong><br>' +
                    '<small>' + f.url + '</small><br>' +
                    '<small>Failures: ' + f.consecutive_failures + '</small>' +
                    '<form action="/admin/feeds/' + f.id + '/retry" method="POST" style="margin-top:0.5rem">' +
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
                    '<span class="audit-action">' + e.action + '</span> ' +
                    '<span class="audit-time">' + e.created_at + '</span>' +
                    (e.details ? '<div class="audit-details">' + e.details + '</div>' : '') +
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
    """Jinja2 loader that loads templates from embedded strings."""

    def get_source(self, environment, template):
        if template in _EMBEDDED_TEMPLATES:
            source = _EMBEDDED_TEMPLATES[template]
            return source, template, lambda: True
        raise TemplateNotFound(template)


# Shared Jinja2 environment
_jinja_env = Environment(loader=EmbeddedLoader(), autoescape=True)


def render_template(name: str, **context) -> str:
    """Render a template with the given context."""
    template = _jinja_env.get_template(name)
    return template.render(**context)


# Template name constants for type safety
TEMPLATE_INDEX = "index.html"
TEMPLATE_SEARCH = "search.html"
TEMPLATE_ADMIN_DASHBOARD = "admin/dashboard.html"
TEMPLATE_ADMIN_LOGIN = "admin/login.html"
TEMPLATE_FEED_ATOM = "feed.atom.xml"
TEMPLATE_FEED_RSS = "feed.rss.xml"
TEMPLATE_FEEDS_OPML = "feeds.opml"
'''

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(output, encoding="utf-8")
    print(f"Generated {OUTPUT_FILE}")
    print(f"  - {len(templates)} templates")
    print(f"  - {len(css_content)} bytes of CSS")


if __name__ == "__main__":
    build_templates()
