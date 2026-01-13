# src/templates.py
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
    "index.html": '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ planet.name }}</title>
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="/feed.atom">
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="/feed.rss">
    <style>
        body { font-family: system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 1rem; }
        header { border-bottom: 1px solid #ddd; margin-bottom: 1rem; }
        .search-form { margin: 1rem 0; }
        .search-form input { padding: 0.5rem; width: 200px; }
        .search-form button { padding: 0.5rem 1rem; }
        .container { display: flex; gap: 2rem; }
        main { flex: 1; }
        aside { width: 250px; }
        article { margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #eee; }
        article h3 { margin-bottom: 0.25rem; }
        .meta { color: #666; font-size: 0.9rem; }
        .feeds li { margin: 0.5rem 0; }
        .feeds .healthy { color: green; }
        .feeds .unhealthy { color: red; }
        footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #ddd; text-align: center; color: #666; }
    </style>
</head>
<body>
    <header>
        <h1>{{ planet.name }}</h1>
        <p>{{ planet.description }}</p>
        <form action="/search" method="GET" class="search-form">
            <input type="search" name="q" placeholder="Search entries..." aria-label="Search entries">
            <button type="submit">Search</button>
        </form>
    </header>

    <div class="container">
        <main>
            {% for date, day_entries in entries_by_date.items() %}
            <section class="day">
                <h2 class="date">{{ date }}</h2>
                {% for entry in day_entries %}
                <article>
                    <header>
                        <h3><a href="{{ entry.url }}">{{ entry.title }}</a></h3>
                        <p class="meta">
                            <span class="author">{{ entry.author or entry.feed_title }}</span>
                            <time datetime="{{ entry.published_at }}">{{ entry.published_at_formatted }}</time>
                        </p>
                    </header>
                    <div class="content">{{ entry.content | safe }}</div>
                </article>
                {% endfor %}
            </section>
            {% else %}
            <p>No entries yet. Add some feeds to get started!</p>
            {% endfor %}
        </main>

        <aside class="sidebar">
            <h2>Subscriptions</h2>
            <ul class="feeds">
                {% for feed in feeds %}
                <li class="{{ 'healthy' if feed.is_healthy else 'unhealthy' }}">
                    <a href="{{ feed.site_url }}">{{ feed.title }}</a>
                </li>
                {% else %}
                <li>No feeds configured</li>
                {% endfor %}
            </ul>
        </aside>
    </div>

    <footer>
        <p><a href="/feed.atom">Atom</a> · <a href="/feed.rss">RSS</a> · <a href="/feeds.opml">OPML</a></p>
        <p>Powered by Planet CF</p>
        <p>Last updated: {{ generated_at }}</p>
    </footer>
</body>
</html>''',

    "search.html": '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search Results - {{ planet.name }}</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 1rem; }
        .search-form input { padding: 0.5rem; width: 200px; }
        .search-form button { padding: 0.5rem 1rem; }
        .search-results li { margin: 1rem 0; }
        .meta { color: #666; font-size: 0.9rem; }
    </style>
</head>
<body>
    <header>
        <h1><a href="/">{{ planet.name }}</a></h1>
        <form action="/search" method="GET" class="search-form">
            <input type="search" name="q" placeholder="Search entries..." value="{{ query }}">
            <button type="submit">Search</button>
        </form>
    </header>

    <main class="search-page">
        <h2>Search Results for "{{ query }}"</h2>
        {% if results %}
        <ul class="search-results">
            {% for entry in results %}
            <li>
                <h3><a href="{{ entry.url }}">{{ entry.title }}</a></h3>
                <p class="meta">{{ entry.author or entry.feed_title }}</p>
            </li>
            {% endfor %}
        </ul>
        {% else %}
        <p>No results found for "{{ query }}"</p>
        {% endif %}
    </main>

    <footer><p><a href="/">Back to Planet CF</a></p></footer>
</body>
</html>''',

    "admin/dashboard.html": '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Admin - {{ planet.name }}</title>
    <style>body { font-family: system-ui; max-width: 900px; margin: 0 auto; padding: 1rem; }</style>
</head>
<body>
    <h1>Admin Dashboard</h1>
    <p>Welcome, {{ user.name }}</p>
    <h2>Feeds</h2>
    <ul>{% for feed in feeds %}<li>{{ feed.title }} - {{ feed.url }}</li>{% endfor %}</ul>
</body>
</html>'''
}

# =============================================================================
# Template Names Constants
# =============================================================================

TEMPLATE_INDEX = "index.html"
TEMPLATE_SEARCH = "search.html"
TEMPLATE_ADMIN_DASHBOARD = "admin/dashboard.html"


# =============================================================================
# Template Loader
# =============================================================================

class DictLoader(BaseLoader):
    """Load templates from a dictionary."""

    def __init__(self, templates: dict[str, str]):
        self.templates = templates

    def get_source(self, environment: Environment, template: str) -> tuple[str, str, callable]:
        if template not in self.templates:
            raise TemplateNotFound(template)
        return self.templates[template], template, lambda: True


# =============================================================================
# Shared Jinja2 Environment
# =============================================================================

_jinja_env: Environment | None = None


def _create_environment(loader: BaseLoader | None = None) -> Environment:
    """Create a Jinja2 environment with appropriate settings."""
    if loader is None:
        loader = DictLoader(_EMBEDDED_TEMPLATES)

    return Environment(
        loader=loader,
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def get_jinja_env() -> Environment:
    """Get the shared Jinja2 environment."""
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = _create_environment()
    return _jinja_env


def reset_jinja_env() -> None:
    """Reset the shared Jinja2 environment (for testing)."""
    global _jinja_env
    _jinja_env = None


def set_jinja_env(env: Environment) -> None:
    """Set a custom Jinja2 environment (for testing)."""
    global _jinja_env
    _jinja_env = env


# =============================================================================
# Template Rendering Helpers
# =============================================================================

def render_template(template_name: str, **context) -> str:
    """Render a template with the given context."""
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)


def render_string(template_string: str, **context) -> str:
    """Render a template string with the given context."""
    env = get_jinja_env()
    template = env.from_string(template_string)
    return template.render(**context)
