# src/templates.py
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
    "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ planet.name }}</title>
    <link rel="stylesheet" href="/static/style.css">
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="/feed.atom">
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="/feed.rss">
</head>
<body>
    <header>
        <h1>{{ planet.name }}</h1>
        <p>{{ planet.description }}</p>
    </header>

    <div class="container">
        <main>
            {% for date, day_entries in entries_by_date.items() %}
            <section class="day">
                <h2 class="date">{{ date }}</h2>
                {% for entry in day_entries %}
                <article>
                    <h3><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h3>
                    <p class="meta">
                        <span class="author">{{ entry.author if entry.author and '@' not in entry.author else entry.feed_title }}</span>
                        {% if entry.published_at_display %}<span class="date-sep">·</span> <time datetime="{{ entry.published_at }}">{{ entry.published_at_display }}</time>{% endif %}
                    </p>
                    <div class="content">{{ entry.content | safe }}</div>
                </article>
                {% endfor %}
            </section>
            {% else %}
            <p>No entries yet.</p>
            {% endfor %}
        </main>

        <aside class="sidebar">
            <form action="/search" method="GET" class="search-form">
                <input type="search" name="q" placeholder="Search entries..." aria-label="Search entries">
                <button type="submit">Search</button>
            </form>

            <h2>Subscriptions</h2>
            <ul class="feeds">
                {% for feed in feeds %}
                <li class="{{ 'healthy' if feed.is_healthy else 'unhealthy' }}">
                    {% if feed.site_url %}<a href="{{ feed.site_url }}">{{ feed.title or 'Untitled' }}</a>{% else %}{{ feed.title or 'Untitled' }}{% endif %}
                </li>
                {% else %}
                <li>No feeds configured</li>
                {% endfor %}
            </ul>
        </aside>
    </div>

    <footer>
        <p><a href="/feed.atom">Atom</a> · <a href="/feed.rss">RSS</a> · <a href="/feeds.opml">OPML</a></p>
        <p>Powered by Planet CF · <a href="/admin" style="color: #999; font-size: 0.8em;">Admin</a></p>
        <p>Last updated: {{ generated_at }}</p>
    </footer>

    <!-- Keyboard shortcuts help panel -->
    <div class="shortcuts-backdrop hidden" id="shortcuts-backdrop"></div>
    <div class="shortcuts-panel hidden" id="shortcuts-panel">
        <h3>Keyboard Shortcuts</h3>
        <dl>
            <dt><kbd>j</kbd></dt>
            <dd>Next entry</dd>
            <dt><kbd>k</kbd></dt>
            <dd>Previous entry</dd>
            <dt><kbd>?</kbd></dt>
            <dd>Toggle this help</dd>
            <dt><kbd>Esc</kbd></dt>
            <dd>Close help</dd>
        </dl>
    </div>

    <script src="/static/keyboard-nav.js"></script>
</body>
</html>
""",
    "search.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search Results - {{ planet.name }}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1><a href="/">{{ planet.name }}</a></h1>
        <p>Search Results</p>
    </header>

    <div class="container">
        <main class="search-page">
            <h2>Results for "{{ query }}"</h2>
            {% if results %}
            <ul class="search-results">
                {% for entry in results %}
                <li>
                    <h3><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h3>
                    <p class="meta">{{ entry.author if entry.author and '@' not in entry.author else entry.feed_title }}</p>
                </li>
                {% endfor %}
            </ul>
            {% else %}
            <p>No results found for "{{ query }}"</p>
            {% endif %}
        </main>

        <aside class="sidebar">
            <form action="/search" method="GET" class="search-form">
                <input type="search" name="q" placeholder="Search entries..." value="{{ query }}" aria-label="Search entries">
                <button type="submit">Search</button>
            </form>

            <p style="margin-top: 1rem;"><a href="/">← Back to home</a></p>
        </aside>
    </div>

    <footer><p><a href="/">Back to Planet CF</a></p></footer>
</body>
</html>
""",
    "admin/dashboard.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin - {{ planet.name }}</title>
    <link rel="stylesheet" href="/static/style.css">
    <style>
        /* Admin-specific overrides */
        body { max-width: 1000px; margin: 0 auto; padding: 0; }
        header { display: flex; justify-content: space-between; align-items: center; text-align: left; }
        header h1 { margin: 0; }
        header h1::before { display: none; }
        .header-actions { display: flex; align-items: center; gap: 0.75rem; }
        .user-info { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; }
        .admin-content { padding: 1rem 1.5rem; }
        .section { margin-bottom: 1.5rem; padding: 1rem; background: var(--bg-tertiary); border-radius: 8px; }
        .section h2 { margin-top: 0; margin-bottom: 1rem; font-size: 1.125rem; }
        .add-form { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .add-form input[type="url"] { flex: 1; min-width: 200px; padding: 0.5rem; border: 1px solid var(--border-light); border-radius: 4px; font-size: 0.875rem; }
        .add-form input[type="text"] { width: 200px; padding: 0.5rem; border: 1px solid var(--border-light); border-radius: 4px; font-size: 0.875rem; }
        .add-form input[type="file"] { padding: 0.5rem; font-size: 0.875rem; }
        .feed-list { list-style: none; padding: 0; margin: 0; }
        .feed-item { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: var(--bg-primary); border: 1px solid var(--border-light); margin-bottom: 0.5rem; border-radius: 4px; }
        .feed-info { flex: 1; }
        .feed-title { font-weight: bold; font-size: 0.9rem; display: flex; align-items: center; gap: 0.5rem; }
        .feed-title-text { cursor: pointer; }
        .feed-title-text:hover { text-decoration: underline; text-decoration-style: dotted; }
        .feed-title-input { font-weight: bold; font-size: 0.9rem; padding: 0.125rem 0.25rem; border: 1px solid var(--accent); border-radius: 3px; width: 200px; }
        .feed-title-input:focus { outline: none; box-shadow: 0 0 0 2px rgba(0, 113, 227, 0.2); }
        .feed-title-actions { display: none; gap: 0.25rem; }
        .feed-title-actions button { padding: 0.125rem 0.5rem; font-size: 0.75rem; }
        .feed-title.editing .feed-title-text { display: none; }
        .feed-title.editing .feed-title-input { display: inline-block; }
        .feed-title.editing .feed-title-actions { display: flex; }
        .feed-title .feed-title-input { display: none; }
        .feed-url { color: var(--text-muted); font-size: 0.8rem; word-break: break-all; }
        .feed-status { font-size: 0.75rem; margin-top: 0.25rem; }
        .feed-status.healthy { color: var(--success); }
        .feed-status.failing { color: var(--error); }
        .feed-status.disabled { color: var(--text-muted); }
        .feed-actions { display: flex; gap: 0.5rem; align-items: center; }
        .toggle { position: relative; display: inline-block; width: 44px; height: 22px; }
        .toggle input { opacity: 0; width: 0; height: 0; }
        .toggle-slider { position: absolute; cursor: pointer; inset: 0; background: var(--border-medium); border-radius: 22px; transition: 0.3s; }
        .toggle-slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: 0.3s; }
        .toggle input:checked + .toggle-slider { background: var(--success); }
        .toggle input:checked + .toggle-slider:before { transform: translateX(22px); }
        .tabs { display: flex; gap: 0.25rem; margin-bottom: 1rem; border-bottom: 2px solid var(--border-light); }
        .tab { padding: 0.5rem 1rem; cursor: pointer; border: none; background: none; font-size: 0.875rem; border-bottom: 2px solid transparent; margin-bottom: -2px; color: var(--text-secondary); }
        .tab:hover { color: var(--text-primary); }
        .tab.active { border-bottom-color: var(--accent); color: var(--accent); font-weight: 600; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .dlq-item, .audit-item { padding: 0.75rem; background: var(--bg-primary); border: 1px solid var(--border-light); margin-bottom: 0.5rem; border-radius: 4px; }
        .dlq-item { border-left: 3px solid var(--error); }
        .audit-item { border-left: 3px solid var(--text-muted); }
        .audit-action { font-weight: bold; color: var(--text-secondary); font-size: 0.9rem; }
        .audit-time { color: var(--text-muted); font-size: 0.75rem; }
        .audit-details { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }
        .empty-state { color: var(--text-muted); font-style: italic; padding: 1rem; text-align: center; }
        #dlq-list, #audit-list { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <header>
        <h1><a href="/">{{ planet.name }}</a> <span style="color: var(--text-muted); font-weight: normal; font-size: 0.875rem;">Admin</span></h1>
        <div class="header-actions">
            <form action="/admin/regenerate" method="POST" style="margin: 0;">
                <button type="submit" class="btn" title="Re-fetch all feeds now">Refresh Feeds</button>
            </form>
            <button id="reindex-btn" class="btn" title="Rebuild search index" onclick="rebuildSearchIndex()">Reindex</button>
            <div class="user-info">
                <span>{{ admin.display_name or admin.github_username }}</span>
                <form action="/admin/logout" method="POST" style="margin: 0;">
                    <button type="submit" class="btn btn-danger btn-sm">Logout</button>
                </form>
            </div>
        </div>
    </header>

    <div class="admin-content">

    <div class="tabs">
        <button class="tab active" data-tab="feeds">Feeds</button>
        <button class="tab" data-tab="import">Import OPML</button>
        <button class="tab" data-tab="dlq">Failed Feeds</button>
        <button class="tab" data-tab="audit">Audit Log</button>
    </div>

    <div id="feeds" class="tab-content active">
        <div class="section">
            <h2>Add Feed</h2>
            <form action="/admin/feeds" method="POST" class="add-form">
                <input type="url" name="url" placeholder="https://example.com/feed.xml" required>
                <input type="text" name="title" placeholder="Feed title (optional)">
                <button type="submit" class="btn btn-success">Add Feed</button>
            </form>
        </div>

        <div class="section">
            <h2>Feeds ({{ feeds | length }})</h2>
            {% if feeds %}
            <ul class="feed-list">
                {% for feed in feeds %}
                <li class="feed-item" data-feed-id="{{ feed.id }}">
                    <div class="feed-info">
                        <div class="feed-title" data-feed-id="{{ feed.id }}">
                            <span class="feed-title-text">{{ feed.title or 'Untitled' }}</span>
                            <input type="text" class="feed-title-input" value="{{ feed.title or '' }}" placeholder="Enter feed title">
                            <div class="feed-title-actions">
                                <button type="button" class="btn btn-success btn-sm save-title-btn">Save</button>
                                <button type="button" class="btn btn-sm cancel-title-btn">Cancel</button>
                            </div>
                        </div>
                        <div class="feed-url">{{ feed.url }}</div>
                        <div class="feed-status {% if not feed.is_active %}disabled{% elif feed.consecutive_failures >= 3 %}failing{% else %}healthy{% endif %}">
                            {% if not feed.is_active %}
                                Disabled
                            {% elif feed.consecutive_failures >= 3 %}
                                Failing ({{ feed.consecutive_failures }} errors)
                            {% else %}
                                Healthy
                            {% endif %}
                        </div>
                    </div>
                    <div class="feed-actions">
                        <label class="toggle" title="Enable/Disable feed">
                            <input type="checkbox" class="feed-toggle" data-feed-id="{{ feed.id }}" {% if feed.is_active %}checked{% endif %}>
                            <span class="toggle-slider"></span>
                        </label>
                        <form action="/admin/feeds/{{ feed.id }}" method="POST" style="margin: 0;">
                            <input type="hidden" name="_method" value="DELETE">
                            <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm('Delete this feed?')">Delete</button>
                        </form>
                    </div>
                </li>
                {% endfor %}
            </ul>
            {% else %}
            <p class="empty-state">No feeds yet. Add one above!</p>
            {% endif %}
        </div>
    </div>

    <div id="import" class="tab-content">
        <div class="section">
            <h2>Import OPML</h2>
            <p style="margin-bottom: 1rem; color: #666;">Upload an OPML file to import multiple feeds at once.</p>
            <form action="/admin/import-opml" method="POST" enctype="multipart/form-data" class="add-form">
                <input type="file" name="opml" accept=".opml,.xml" required>
                <button type="submit" class="btn btn-success">Import Feeds</button>
            </form>
        </div>
    </div>

    <div id="dlq" class="tab-content">
        <div class="section">
            <h2>Failed Feeds (Dead Letter Queue)</h2>
            <p style="margin-bottom: 1rem; color: #666;">Feeds that have failed 3 or more times consecutively.</p>
            <div id="dlq-list">
                <p class="empty-state">Loading...</p>
            </div>
        </div>
    </div>

    <div id="audit" class="tab-content">
        <div class="section">
            <h2>Audit Log</h2>
            <p style="margin-bottom: 1rem; color: #666;">Recent admin actions.</p>
            <div id="audit-list">
                <p class="empty-state">Loading...</p>
            </div>
        </div>
    </div>

    </div><!-- .admin-content -->

    <script src="/static/admin.js"></script>
</body>
</html>
""",
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
</html>
""",
    "feed.atom.xml": """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{{ planet.name | e }}</title>
  <subtitle>{{ planet.description | e }}</subtitle>
  <link href="{{ planet.link }}" rel="alternate"/>
  <link href="{{ planet.link }}/feed.atom" rel="self"/>
  <id>{{ planet.link }}/</id>
  <updated>{{ updated_at }}</updated>
{% for entry in entries %}
  <entry>
    <title>{{ entry.title | e }}</title>
    <link href="{{ entry.url | e }}" rel="alternate"/>
    <id>{{ entry.guid | e }}</id>
    <published>{{ entry.published_at }}Z</published>
    <author><name>{{ entry.author | e }}</name></author>
    <content type="html">{{ entry.content | e }}</content>
  </entry>
{% endfor %}
</feed>
""",
    "feed.rss.xml": """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{{ planet.name | e }}</title>
    <description>{{ planet.description | e }}</description>
    <link>{{ planet.link }}</link>
    <atom:link href="{{ planet.link }}/feed.rss" rel="self" type="application/rss+xml"/>
    <lastBuildDate>{{ last_build_date }}</lastBuildDate>
{% for entry in entries %}
    <item>
      <title>{{ entry.title | e }}</title>
      <link>{{ entry.url | e }}</link>
      <guid>{{ entry.guid | e }}</guid>
      <pubDate>{{ entry.published_at }}</pubDate>
      <author>{{ entry.author | e }}</author>
      <description><![CDATA[{{ entry.content_cdata }}]]></description>
    </item>
{% endfor %}
  </channel>
</rss>
""",
    "feeds.opml": """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head>
    <title>{{ planet.name }} Subscriptions</title>
    <dateCreated>{{ date_created }}</dateCreated>
    <ownerName>{{ owner_name | e }}</ownerName>
  </head>
  <body>
    <outline text="{{ planet.name }} Feeds" title="{{ planet.name }} Feeds">
{% for feed in feeds %}
      <outline type="rss" text="{{ feed.title | e }}" title="{{ feed.title | e }}" xmlUrl="{{ feed.url | e }}" htmlUrl="{{ feed.site_url | e }}"/>
{% endfor %}
    </outline>
  </body>
</opml>
""",
}

STATIC_CSS = """/* Planet CF Styles - Generated from templates/style.css */
:root {
    /* Accent color - used sparingly */
    --accent: #f6821f;
    --accent-dark: #e5731a;
    --accent-light: #fff7ed;
    --accent-subtle: #fed7aa;

    /* Neutral tones */
    --text-primary: #111827;
    --text-secondary: #374151;
    --text-muted: #6b7280;

    /* Backgrounds */
    --bg-primary: #ffffff;
    --bg-secondary: #f9fafb;
    --bg-tertiary: #f3f4f6;

    /* Borders */
    --border-light: #e5e7eb;
    --border-medium: #d1d5db;
    --border-accent: var(--accent);

    /* Code blocks */
    --code-bg: #1f2937;
    --code-text: #f3f4f6;

    /* Semantic colors */
    --success: #059669;
    --error: #dc2626;

    /* Shadows */
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.07);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 18px;
    line-height: 1.8;
    color: var(--text-primary);
    background: var(--bg-secondary);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

/* Headings use bold serif for elegance */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Palatino Linotype', 'Book Antiqua', Palatino, Georgia, serif;
    font-weight: 700;
}

/* UI elements use clean sans-serif */
.search-form, .sidebar, footer, .meta, button, .day h2 {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

header {
    background: var(--bg-primary);
    border-bottom: 1px solid var(--border-light);
    padding: 0.5rem 1.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}

header h1 {
    margin: 0;
    font-weight: 600;
    font-size: 1.125rem;
    letter-spacing: -0.01em;
    color: var(--text-primary);
}

header p {
    color: var(--text-muted);
    font-size: 0.8rem;
    margin: 0;
}

header p::before {
    content: '·';
    margin-right: 0.5rem;
    color: var(--border-medium);
}

header a {
    color: var(--text-primary);
    text-decoration: none;
}

header a:hover {
    color: var(--accent);
}

.search-form {
    margin-bottom: 1.5rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border-light);
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
}

.search-form input {
    padding: 0.75rem 1rem;
    border: 1px solid var(--border-light);
    border-radius: 6px;
    width: 100%;
    box-sizing: border-box;
    font-size: 0.9rem;
    background: var(--bg-secondary);
    transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.search-form input:focus {
    outline: none;
    border-color: var(--accent);
    background: var(--bg-primary);
    box-shadow: 0 0 0 3px var(--accent-light);
}

.search-form button {
    padding: 0.75rem 1rem;
    background: var(--bg-primary);
    color: var(--text-secondary);
    border: 1px solid var(--border-medium);
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.9rem;
    width: 100%;
    transition: all 0.15s ease;
}

.search-form button:hover {
    background: var(--bg-secondary);
    border-color: var(--accent-subtle);
    color: var(--text-primary);
}

.search-form button:active {
    transform: scale(0.98);
}

.container {
    display: grid;
    grid-template-columns: 1fr 300px;
    gap: 2rem;
    max-width: 1200px;
    margin: 2rem auto;
    padding: 0 1rem;
}

main { min-width: 0; }

.day { margin-bottom: 2.5rem; }
.day h2 {
    color: var(--text-muted);
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding-bottom: 0.5rem;
    margin-bottom: 1.25rem;
    border-bottom: 1px solid var(--border-light);
}

article {
    background: var(--bg-primary);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
    scroll-margin-top: 1rem;
}

article:hover {
    box-shadow: var(--shadow-md);
    border-color: var(--border-medium);
}

article h3 {
    margin-bottom: 0.625rem;
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.35;
}

article h3 a {
    color: var(--text-primary);
    text-decoration: none;
    transition: color 0.15s ease;
}

article h3 a:hover {
    color: var(--accent);
}

article header {
    background: transparent;
    border-bottom: none;
    padding: 0;
    text-align: left;
}

.meta {
    color: var(--text-muted);
    font-size: 0.875rem;
    margin-bottom: 1rem;
}

.meta .author {
    color: var(--text-secondary);
    font-weight: 500;
}

.meta .date-sep {
    color: var(--text-muted);
    margin: 0 0.25rem;
}

.meta time {
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}

/* Content security: prevent foreign content from breaking layout */
.content {
    overflow-wrap: break-word;
    word-wrap: break-word;
    word-break: break-word;
    color: var(--text-secondary);
    font-size: 1.0625rem;
    line-height: 1.85;
}

.content p { margin-bottom: 1.25rem; }
.content p:last-child { margin-bottom: 0; }

.content img {
    max-width: 100%;
    height: auto;
    max-height: 600px;
    object-fit: contain;
    border-radius: 6px;
    margin: 1rem 0;
}

.content pre, .content code {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.875rem;
}

.content code {
    background: var(--bg-tertiary);
    color: var(--accent-dark);
    padding: 0.15rem 0.4rem;
    border-radius: 4px;
}

.content pre {
    background: var(--code-bg);
    color: var(--code-text);
    padding: 1.25rem;
    border-radius: 8px;
    overflow-x: auto;
    max-width: 100%;
    margin: 1rem 0;
}

.content pre code {
    background: transparent;
    color: inherit;
    padding: 0;
}

.content table {
    display: block;
    overflow-x: auto;
    max-width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
    font-size: 0.925rem;
}

.content th, .content td {
    border: 1px solid var(--border-light);
    padding: 0.75rem 1rem;
    text-align: left;
}

.content th {
    background: var(--bg-tertiary);
    font-weight: 600;
    color: var(--text-primary);
}

.content blockquote {
    border-left: 3px solid var(--border-medium);
    margin: 1.25rem 0;
    padding: 0.75rem 1.25rem;
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    border-radius: 0 6px 6px 0;
    font-style: italic;
}

.content a {
    color: var(--accent);
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.15s ease;
    word-break: break-all;
}

.content a:hover { border-bottom-color: var(--accent); }

.content h1, .content h2, .content h3, .content h4 {
    color: var(--text-primary);
    font-weight: 600;
    margin: 1.5rem 0 0.75rem 0;
    line-height: 1.3;
}

.content h1 { font-size: 1.5rem; }
.content h2 { font-size: 1.3rem; }
.content h3 { font-size: 1.15rem; }
.content h4 { font-size: 1rem; }

.content ul, .content ol {
    margin: 1rem 0;
    padding-left: 1.5rem;
}

.content li { margin-bottom: 0.5rem; }

.content iframe, .content object, .content embed {
    display: none !important;
}

.sidebar {
    background: var(--bg-primary);
    border: 1px solid var(--border-light);
    padding: 1.5rem;
    border-radius: 10px;
    height: fit-content;
    position: sticky;
    top: 1rem;
    box-shadow: var(--shadow-sm);
}

.sidebar h2 {
    margin-bottom: 1rem;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
}

.feeds { list-style: none; }

.feeds li {
    padding: 0.625rem 0;
    border-bottom: 1px solid var(--border-light);
    font-size: 0.925rem;
}

.feeds li:last-child { border-bottom: none; }

.feeds li a {
    color: var(--text-secondary);
    text-decoration: none;
    transition: color 0.15s ease;
}

.feeds li a:hover { color: var(--accent); }

.feeds li.healthy::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    background: var(--success);
    border-radius: 50%;
    margin-right: 0.5rem;
    vertical-align: middle;
}

.feeds li.unhealthy { color: var(--error); }

.feeds li.unhealthy::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 6px;
    background: var(--error);
    border-radius: 50%;
    margin-right: 0.5rem;
    vertical-align: middle;
}

footer {
    text-align: center;
    padding: 2.5rem 2rem;
    background: var(--bg-tertiary);
    margin-top: 3rem;
    border-top: 1px solid var(--border-light);
}

footer p {
    color: var(--text-muted);
    font-size: 0.9rem;
    margin-bottom: 0.5rem;
}

footer a {
    color: var(--accent);
    text-decoration: none;
    transition: color 0.15s ease;
}

footer a:hover { color: var(--accent-dark); }

/* Search results */
.search-results { list-style: none; }

.search-results li {
    background: var(--bg-primary);
    border: 1px solid var(--border-light);
    border-radius: 10px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.2s ease;
}

.search-results li:hover { box-shadow: var(--shadow-md); }

.search-results h3 {
    margin-bottom: 0.5rem;
    font-weight: 600;
}

.search-results h3 a {
    color: var(--text-primary);
    text-decoration: none;
    transition: color 0.15s ease;
}

.search-results h3 a:hover { color: var(--accent); }

/* Admin table styles */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
}

th, td {
    padding: 0.75rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--border-light);
}

th {
    background: var(--bg-tertiary);
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 0.875rem;
}

button {
    padding: 0.625rem 1.25rem;
    background: var(--bg-primary);
    color: var(--accent);
    border: 2px solid var(--accent);
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.95rem;
    transition: background 0.15s ease, color 0.15s ease;
}

button:hover {
    background: var(--accent);
    color: white;
}

/* Button variants */
.btn {
    padding: 0.625rem 1.25rem;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.95rem;
    border: none;
    transition: opacity 0.15s ease;
}
.btn:hover { opacity: 0.9; }
.btn-sm { padding: 0.375rem 0.75rem; font-size: 0.8rem; }
.btn-success { background: var(--success); color: white; }
.btn-danger { background: var(--error); color: white; }
.btn-warning { background: #f59e0b; color: white; }

/* Keyboard navigation */
article.selected {
    outline: 2px solid var(--accent);
    outline-offset: 4px;
}

.shortcuts-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 999;
}

.shortcuts-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: var(--bg-primary);
    border: 1px solid var(--border-medium);
    border-radius: 10px;
    padding: 1.5rem 2rem;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    min-width: 280px;
}

.shortcuts-panel h3 {
    margin: 0 0 1rem 0;
    font-size: 1rem;
    color: var(--text-primary);
}

.shortcuts-panel dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.5rem 1rem;
    margin: 0;
}

.shortcuts-panel dt {
    text-align: right;
}

.shortcuts-panel dd {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.shortcuts-panel kbd {
    display: inline-block;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-light);
    border-radius: 4px;
    padding: 0.15rem 0.5rem;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.8rem;
    color: var(--text-primary);
}

.hidden {
    display: none !important;
}

/* Responsive */
@media (max-width: 768px) {
    header {
        padding: 0.5rem 1rem;
        flex-direction: column;
        gap: 0.125rem;
    }
    header h1 { font-size: 1rem; }
    header p { font-size: 0.75rem; }
    header p::before { display: none; }
    .container {
        grid-template-columns: 1fr;
        gap: 1.5rem;
        margin: 1.5rem auto;
    }
    .sidebar { position: static; }
    .search-form {
        flex-direction: column;
        align-items: stretch;
    }
    .search-form input { width: 100%; }
    article { padding: 1.25rem; }
}
"""

KEYBOARD_NAV_JS = """// Keyboard navigation for browsing entries
(function() {
    const articles = document.querySelectorAll('article');
    const panel = document.getElementById('shortcuts-panel');
    const backdrop = document.getElementById('shortcuts-backdrop');
    let current = -1;

    function select(index) {
        // Guard: no articles to navigate
        if (articles.length === 0) return;

        // Remove selection from current article
        if (current >= 0 && articles[current]) {
            articles[current].classList.remove('selected');
        }

        // Clamp index to valid range
        current = Math.max(0, Math.min(index, articles.length - 1));

        // Select and scroll to new article
        articles[current].classList.add('selected');
        articles[current].scrollIntoView({ block: 'start', behavior: 'smooth' });
    }

    function toggleHelp() {
        if (panel && backdrop) {
            panel.classList.toggle('hidden');
            backdrop.classList.toggle('hidden');
        }
    }

    function closeHelp() {
        if (panel && backdrop) {
            panel.classList.add('hidden');
            backdrop.classList.add('hidden');
        }
    }

    if (backdrop) {
        backdrop.addEventListener('click', closeHelp);
    }

    document.addEventListener('keydown', function(e) {
        // Ignore if typing in input/textarea
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        if (e.key === 'j') {
            e.preventDefault();
            select(current + 1);
        }
        if (e.key === 'k') {
            e.preventDefault();
            // Don't go before first article
            if (current > 0) {
                select(current - 1);
            } else if (current === -1) {
                // First keypress with k: select last article
                select(articles.length - 1);
            }
        }
        if (e.key === '?') {
            e.preventDefault();
            toggleHelp();
        }
        if (e.key === 'Escape') {
            closeHelp();
        }
    });
})();
"""


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
                method: 'POST',
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
