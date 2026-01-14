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
        main { flex: 1; min-width: 0; }  /* min-width: 0 prevents flex overflow */
        aside { width: 250px; flex-shrink: 0; }
        article { margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #eee; }
        article h3 { margin-bottom: 0.25rem; }
        .meta { color: #666; font-size: 0.9rem; }
        .feeds li { margin: 0.5rem 0; }
        .feeds .healthy { color: green; }
        .feeds .unhealthy { color: red; }
        footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #ddd; text-align: center; color: #666; }

        /* Content security: prevent foreign content from breaking layout */
        .content {
            overflow-wrap: break-word;      /* Break long words/URLs */
            word-wrap: break-word;          /* Fallback for older browsers */
            word-break: break-word;         /* Additional fallback */
        }
        .content img {
            max-width: 100%;                /* Images constrained to container */
            height: auto;                   /* Maintain aspect ratio */
            max-height: 600px;              /* Prevent extremely tall images */
            object-fit: contain;            /* Scale within bounds */
            border-radius: 4px;
        }
        .content pre, .content code {
            overflow-x: auto;               /* Horizontal scroll for code */
            max-width: 100%;
            background: #f5f5f5;
            padding: 0.5rem;
            border-radius: 4px;
        }
        .content pre {
            padding: 1rem;
        }
        .content table {
            display: block;                 /* Enable overflow handling */
            overflow-x: auto;               /* Horizontal scroll for wide tables */
            max-width: 100%;
            border-collapse: collapse;
        }
        .content th, .content td {
            border: 1px solid #ddd;
            padding: 0.5rem;
        }
        .content blockquote {
            border-left: 3px solid #ddd;
            margin-left: 0;
            padding-left: 1rem;
            color: #666;
        }
        .content a {
            word-break: break-all;          /* Break long URLs in links */
        }
        .content iframe, .content object, .content embed {
            display: none !important;       /* Extra defense: hide any that slip through */
        }
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
                        <h3><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h3>
                        <p class="meta">
                            <span class="author">{{ entry.author or entry.feed_title }}</span>
                            <time datetime="{{ entry.published_at }}" title="{{ entry.published_at_formatted }}">{{ entry.published_at_relative }}</time>
                        </p>
                    </header>
                    <div class="content">{{ entry.content | safe }}</div>
                </article>
                {% endfor %}
            </section>
            {% else %}
            <p>No entries yet.</p>
            {% endfor %}
        </main>

        <aside class="sidebar">
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
                <h3><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h3>
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
        body { font-family: system-ui; max-width: 1000px; margin: 0 auto; padding: 1rem; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; border-bottom: 1px solid #ddd; padding-bottom: 1rem; }
        .header-actions { display: flex; align-items: center; gap: 1rem; }
        .user-info { display: flex; align-items: center; gap: 0.5rem; }
        .btn { border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; font-size: 0.875rem; }
        .btn-primary { background: #007bff; color: white; }
        .btn-primary:hover { background: #0056b3; }
        .btn-success { background: #28a745; color: white; }
        .btn-success:hover { background: #218838; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-danger:hover { background: #c82333; }
        .btn-warning { background: #ffc107; color: #212529; }
        .btn-warning:hover { background: #e0a800; }
        .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.8rem; }
        .section { margin-bottom: 2rem; padding: 1rem; background: #f8f9fa; border-radius: 8px; }
        .section h2 { margin-top: 0; margin-bottom: 1rem; font-size: 1.25rem; }
        .add-form { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .add-form input[type="url"] { flex: 1; min-width: 200px; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
        .add-form input[type="text"] { width: 200px; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
        .add-form input[type="file"] { padding: 0.5rem; }
        .feed-list { list-style: none; padding: 0; margin: 0; }
        .feed-item { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: white; border: 1px solid #dee2e6; margin-bottom: 0.5rem; border-radius: 4px; }
        .feed-info { flex: 1; }
        .feed-title { font-weight: bold; }
        .feed-url { color: #666; font-size: 0.85rem; word-break: break-all; }
        .feed-status { font-size: 0.8rem; margin-top: 0.25rem; }
        .feed-status.healthy { color: #28a745; }
        .feed-status.failing { color: #dc3545; }
        .feed-status.disabled { color: #6c757d; }
        .feed-actions { display: flex; gap: 0.5rem; align-items: center; }
        .toggle { position: relative; display: inline-block; width: 50px; height: 24px; }
        .toggle input { opacity: 0; width: 0; height: 0; }
        .toggle-slider { position: absolute; cursor: pointer; inset: 0; background: #ccc; border-radius: 24px; transition: 0.3s; }
        .toggle-slider:before { position: absolute; content: ""; height: 18px; width: 18px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: 0.3s; }
        .toggle input:checked + .toggle-slider { background: #28a745; }
        .toggle input:checked + .toggle-slider:before { transform: translateX(26px); }
        .tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; border-bottom: 2px solid #dee2e6; }
        .tab { padding: 0.5rem 1rem; cursor: pointer; border: none; background: none; font-size: 0.9rem; border-bottom: 2px solid transparent; margin-bottom: -2px; }
        .tab.active { border-bottom-color: #007bff; color: #007bff; font-weight: bold; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .dlq-item, .audit-item { padding: 0.75rem; background: white; border: 1px solid #dee2e6; margin-bottom: 0.5rem; border-radius: 4px; }
        .dlq-item { border-left: 4px solid #dc3545; }
        .audit-item { border-left: 4px solid #6c757d; }
        .audit-action { font-weight: bold; color: #495057; }
        .audit-time { color: #6c757d; font-size: 0.8rem; }
        .audit-details { font-size: 0.85rem; color: #666; margin-top: 0.25rem; }
        .empty-state { color: #6c757d; font-style: italic; padding: 1rem; text-align: center; }
        #dlq-list, #audit-list { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Admin Dashboard</h1>
        <div class="header-actions">
            <form action="/admin/regenerate" method="POST" style="margin: 0;">
                <button type="submit" class="btn btn-primary" title="Re-fetch all feeds now">Refresh All Feeds</button>
            </form>
            <div class="user-info">
                <span>{{ admin.display_name or admin.github_username }}</span>
                <form action="/admin/logout" method="POST" style="margin: 0;">
                    <button type="submit" class="btn btn-danger btn-sm">Logout</button>
                </form>
            </div>
        </div>
    </div>

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
                <li class="feed-item">
                    <div class="feed-info">
                        <div class="feed-title">{{ feed.title or 'Untitled' }}</div>
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

    <script src="/static/admin.js"></script>
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
</feed>""",
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
</rss>""",
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
</opml>""",
}

# =============================================================================
# Static Assets (CSS and JavaScript)
# =============================================================================

STATIC_CSS = """
/* Planet CF Styles */
:root {
    --primary-color: #f38020;
    --text-color: #333;
    --bg-color: #fff;
    --sidebar-bg: #f5f5f5;
    --border-color: #ddd;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
    background: var(--bg-color);
}

header {
    background: var(--primary-color);
    color: white;
    padding: 2rem;
    text-align: center;
}

header h1 { margin-bottom: 0.5rem; }
header a { color: white; }

.search-form {
    margin-top: 1rem;
    display: flex;
    justify-content: center;
    gap: 0.5rem;
}

.search-form input {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 4px;
    width: 300px;
}

.search-form button {
    padding: 0.5rem 1rem;
    background: white;
    color: var(--primary-color);
    border: none;
    border-radius: 4px;
    cursor: pointer;
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

.day { margin-bottom: 2rem; }
.day h2 {
    border-bottom: 2px solid var(--primary-color);
    padding-bottom: 0.5rem;
    margin-bottom: 1rem;
}

article {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

article h3 { margin-bottom: 0.5rem; }
article h3 a { color: var(--primary-color); text-decoration: none; }
article h3 a:hover { text-decoration: underline; }

.meta {
    color: #666;
    font-size: 0.9rem;
    margin-bottom: 1rem;
}

.content {
    overflow-wrap: break-word;
}

.content img {
    max-width: 100%;
    height: auto;
}

.content pre {
    background: #f5f5f5;
    padding: 1rem;
    overflow-x: auto;
    border-radius: 4px;
}

.sidebar {
    background: var(--sidebar-bg);
    padding: 1.5rem;
    border-radius: 8px;
    height: fit-content;
    position: sticky;
    top: 1rem;
}

.sidebar h2 {
    margin-bottom: 1rem;
    font-size: 1.1rem;
}

.feeds {
    list-style: none;
}

.feeds li {
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border-color);
}

.feeds li.unhealthy { color: #c00; }
.feeds .last-updated {
    display: block;
    font-size: 0.8rem;
    color: #666;
}

footer {
    text-align: center;
    padding: 2rem;
    background: #f5f5f5;
    margin-top: 2rem;
}

footer a { color: var(--primary-color); }

/* Search results */
.search-results {
    list-style: none;
}

.search-results li {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1rem;
}

.search-results h3 { margin-bottom: 0.5rem; }
.search-results .score { margin-left: 1rem; color: #666; }

/* Admin styles */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
}

th, td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

th { background: var(--sidebar-bg); }
tr.unhealthy { background: #fee; }

.add-feed-form {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
}

.add-feed-form input {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
}

.add-feed-form input[type="url"] { flex: 1; }

button {
    padding: 0.5rem 1rem;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

button:hover { opacity: 0.9; }

/* Responsive */
@media (max-width: 768px) {
    .container {
        grid-template-columns: 1fr;
    }
    .sidebar {
        position: static;
    }
    .search-form input { width: 200px; }
}
"""

ADMIN_JS = """
// Admin Dashboard JavaScript
// Served from /static/admin.js to comply with Content Security Policy

function showTab(tabId) {
    // Remove active class from all tabs and content
    document.querySelectorAll('.tab').forEach(function(t) {
        t.classList.remove('active');
    });
    document.querySelectorAll('.tab-content').forEach(function(c) {
        c.classList.remove('active');
    });

    // Add active class to selected tab and content
    var tabs = document.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) {
        if (tabs[i].getAttribute('data-tab') === tabId) {
            tabs[i].classList.add('active');
            break;
        }
    }
    document.getElementById(tabId).classList.add('active');

    // Load data for specific tabs
    if (tabId === 'dlq') loadDLQ();
    if (tabId === 'audit') loadAuditLog();
}

function toggleFeed(feedId, isActive) {
    fetch('/admin/feeds/' + feedId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: isActive ? 1 : 0 })
    }).then(function(r) {
        if (!r.ok) alert('Failed to update feed');
    }).catch(function(err) {
        alert('Error updating feed: ' + err.message);
    });
}

function loadDLQ() {
    fetch('/admin/dlq')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var container = document.getElementById('dlq-list');
            if (!data.failed_feeds || data.failed_feeds.length === 0) {
                container.innerHTML = '<p class="empty-state">' +
                    'No failed feeds. All feeds are healthy!</p>';
                return;
            }
            var html = '';
            for (var i = 0; i < data.failed_feeds.length; i++) {
                var f = data.failed_feeds[i];
                html += '<div class="dlq-item">';
                html += '<div><strong>' + escapeHtml(f.title || 'Untitled') + '</strong></div>';
                html += '<div style="font-size:0.85rem;color:#666;word-break:break-all;">';
                html += escapeHtml(f.url) + '</div>';
                html += '<div style="font-size:0.8rem;color:#dc3545;margin-top:0.25rem;">';
                html += escapeHtml(String(f.consecutive_failures)) + ' consecutive failures';
                html += (f.fetch_error ? ' - ' + escapeHtml(f.fetch_error) : '');
                html += '</div>';
                html += '<form action="/admin/dlq/' + encodeURIComponent(f.id) + '/retry" method="POST" ';
                html += 'style="margin-top:0.5rem;">';
                html += '<button type="submit" class="btn btn-warning btn-sm">Retry</button>';
                html += '</form></div>';
            }
            container.innerHTML = html;
        })
        .catch(function(err) {
            document.getElementById('dlq-list').innerHTML = '<p class="empty-state" ' +
                'style="color:#dc3545;">Error loading: ' + escapeHtml(err.message || 'Unknown error') + '</p>';
        });
}

function loadAuditLog() {
    fetch('/admin/audit')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var container = document.getElementById('audit-list');
            if (!data.audit_log || data.audit_log.length === 0) {
                container.innerHTML = '<p class="empty-state">No audit log entries yet.</p>';
                return;
            }
            var html = '';
            for (var i = 0; i < data.audit_log.length; i++) {
                var a = data.audit_log[i];
                var details = {};
                try {
                    if (a.details) details = JSON.parse(a.details);
                } catch (e) {}
                var detailParts = [];
                for (var key in details) {
                    if (details.hasOwnProperty(key)) {
                        detailParts.push(key + ': ' + details[key]);
                    }
                }
                var detailStr = detailParts.join(', ');
                html += '<div class="audit-item">';
                html += '<div class="audit-action">' + escapeHtml(a.action) + '</div>';
                html += '<div class="audit-time">' + escapeHtml(a.created_at) + ' by ';
                html += escapeHtml(a.display_name || a.github_username || 'Unknown');
                html += '</div>';
                if (detailStr) {
                    html += '<div class="audit-details">' + escapeHtml(detailStr) + '</div>';
                }
                html += '</div>';
            }
            container.innerHTML = html;
        })
        .catch(function(err) {
            document.getElementById('audit-list').innerHTML = '<p class="empty-state" ' +
                'style="color:#dc3545;">Error loading: ' + escapeHtml(err.message || 'Unknown error') + '</p>';
        });
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize tab click handlers when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    var tabs = document.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].addEventListener('click', function() {
            var tabId = this.getAttribute('data-tab');
            if (tabId) showTab(tabId);
        });
    }

    // Initialize toggle handlers
    var toggles = document.querySelectorAll('.feed-toggle');
    for (var j = 0; j < toggles.length; j++) {
        toggles[j].addEventListener('change', function() {
            var feedId = this.getAttribute('data-feed-id');
            toggleFeed(feedId, this.checked);
        });
    }
});
"""

# =============================================================================
# Template Names Constants
# =============================================================================

TEMPLATE_INDEX = "index.html"
TEMPLATE_SEARCH = "search.html"
TEMPLATE_ADMIN_DASHBOARD = "admin/dashboard.html"
TEMPLATE_ADMIN_LOGIN = "admin/login.html"
TEMPLATE_FEED_ATOM = "feed.atom.xml"
TEMPLATE_FEED_RSS = "feed.rss.xml"
TEMPLATE_FEEDS_OPML = "feeds.opml"


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
