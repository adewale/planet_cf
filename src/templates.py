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
    "index.html": """<!DOCTYPE html>
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
</html>""",
    "search.html": """<!DOCTYPE html>
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
</html>""",
    "admin/dashboard.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Admin - {{ planet.name }}</title>
    <style>
        body { font-family: system-ui; max-width: 900px; margin: 0 auto; padding: 1rem; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; border-bottom: 1px solid #ddd; padding-bottom: 1rem; }
        .user-info { display: flex; align-items: center; gap: 1rem; }
        .logout-btn { background: #dc3545; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; }
        .logout-btn:hover { background: #c82333; }
        .add-form { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; }
        .add-form input[type="url"] { flex: 1; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
        .add-form input[type="text"] { width: 200px; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
        .add-form button { background: #28a745; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; }
        .feed-list { list-style: none; padding: 0; }
        .feed-item { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; border: 1px solid #eee; margin-bottom: 0.5rem; border-radius: 4px; }
        .feed-info { flex: 1; }
        .feed-title { font-weight: bold; }
        .feed-url { color: #666; font-size: 0.9rem; }
        .feed-status { font-size: 0.8rem; }
        .feed-status.healthy { color: #28a745; }
        .feed-status.failing { color: #dc3545; }
        .delete-btn { background: #dc3545; color: white; border: none; padding: 0.25rem 0.5rem; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Admin Dashboard</h1>
        <div class="user-info">
            <span>Welcome, {{ admin.display_name or admin.github_username }}</span>
            <form action="/admin/logout" method="POST" style="margin: 0;">
                <button type="submit" class="logout-btn">Logout</button>
            </form>
        </div>
    </div>

    <h2>Add Feed</h2>
    <form action="/admin/feeds" method="POST" class="add-form">
        <input type="url" name="url" placeholder="https://example.com/feed.xml" required>
        <input type="text" name="title" placeholder="Feed title (optional)">
        <button type="submit">Add Feed</button>
    </form>

    <h2>Feeds ({{ feeds | length }})</h2>
    {% if feeds %}
    <ul class="feed-list">
        {% for feed in feeds %}
        <li class="feed-item">
            <div class="feed-info">
                <div class="feed-title">{{ feed.title or 'Untitled' }}</div>
                <div class="feed-url">{{ feed.url }}</div>
                <div class="feed-status {{ 'healthy' if feed.consecutive_failures < 3 else 'failing' }}">
                    {% if feed.consecutive_failures >= 3 %}Failing ({{ feed.consecutive_failures }} errors){% else %}Healthy{% endif %}
                </div>
            </div>
            <form action="/admin/feeds/{{ feed.id }}" method="POST" style="margin: 0;">
                <input type="hidden" name="_method" value="DELETE">
                <button type="submit" class="delete-btn" onclick="return confirm('Delete this feed?')">Delete</button>
            </form>
        </li>
        {% endfor %}
    </ul>
    {% else %}
    <p>No feeds yet. Add one above!</p>
    {% endif %}
</body>
</html>""",
    "admin/login.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - {{ planet.name }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .login-card {
            background: white;
            padding: 3rem;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 400px;
            width: 90%;
        }
        .logo { font-size: 3rem; margin-bottom: 1rem; }
        h1 { color: #333; margin-bottom: 0.5rem; font-size: 1.5rem; }
        .subtitle { color: #666; margin-bottom: 2rem; }
        .github-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.75rem;
            background: #24292e;
            color: white;
            padding: 0.875rem 1.5rem;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            font-size: 1rem;
            transition: background 0.2s;
        }
        .github-btn:hover { background: #1b1f23; }
        .github-btn svg { width: 20px; height: 20px; fill: currentColor; }
        .footer { margin-top: 2rem; color: #999; font-size: 0.875rem; }
        .footer a { color: #667eea; text-decoration: none; }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo">&#9741;</div>
        <h1>{{ planet.name }} Admin</h1>
        <p class="subtitle">Sign in to manage feeds and settings</p>

        <a href="/auth/github" class="github-btn">
            <svg viewBox="0 0 16 16">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
            </svg>
            Sign in with GitHub
        </a>

        <p class="footer">
            <a href="/">&#8592; Back to {{ planet.name }}</a>
        </p>
    </div>
</body>
</html>""",
}

# =============================================================================
# Template Names Constants
# =============================================================================

TEMPLATE_INDEX = "index.html"
TEMPLATE_SEARCH = "search.html"
TEMPLATE_ADMIN_DASHBOARD = "admin/dashboard.html"
TEMPLATE_ADMIN_LOGIN = "admin/login.html"


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
