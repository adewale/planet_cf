# src/templates.py
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
    "default": {
        "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ planet.name }}</title>
    <link rel="icon" href="/static/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/style.css">
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="{{ feed_links.atom or '/feed.atom' }}">
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="{{ feed_links.rss or '/feed.rss' }}">
</head>
<body>
    <header>
        {% if logo %}
        <a href="/" class="logo-link">
            <img src="{{ logo.url }}" alt="{{ logo.alt }}" width="{{ logo.width }}" height="{{ logo.height }}" class="logo">
        </a>
        {% endif %}
        <div class="header-text">
            <h1><a href="/">{{ planet.name }}</a></h1>
            <p>{{ planet.description }}</p>
        </div>
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
                        <span class="author">{{ entry.display_author }}</span>
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
            {% if feed_links and (feed_links.sidebar_rss or feed_links.titles_only or feed_links.planet_planet) %}
            <div class="sidebar-links">
                {% if feed_links.sidebar_rss %}<a href="{{ feed_links.sidebar_rss }}">RSS</a>{% endif %}
                {% if feed_links.titles_only %}<a href="{{ feed_links.titles_only }}">titles only</a>{% endif %}
                {% if feed_links.planet_planet %}<a href="{{ feed_links.planet_planet }}">Planet Planet</a>{% endif %}
            </div>
            {% endif %}

            {% if not is_lite_mode %}
            <form action="/search" method="GET" class="search-form">
                <label class="search-label"><strong>Search</strong></label>
                <input type="search" name="q" placeholder="Search entries..." aria-label="Search entries">
                <button type="submit">Search</button>
            </form>
            {% endif %}

            <h2>Subscriptions</h2>
            <ul class="feeds">
                {% for feed in feeds %}
                <li class="{{ 'feed-inactive' if feed.is_inactive else ('healthy' if feed.is_healthy else 'unhealthy') }}"{% if feed.is_inactive %} title="Feed temporarily unavailable"{% endif %}>
                    {% if feed.url %}<a href="{{ feed.url }}" class="feed-icon" title="RSS Feed"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="6.18" cy="17.82" r="2.18"/><path d="M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56zm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"/></svg></a>{% endif %}
                    {% if feed.site_url %}<a href="{{ feed.site_url }}">{{ feed.title or 'Untitled' }}</a>{% else %}{{ feed.title or 'Untitled' }}{% endif %}
                </li>
                {% else %}
                <li>No feeds configured</li>
                {% endfor %}
            </ul>
            {% if submission %}
            <p class="submission-link"><a href="{{ submission.url }}">{{ submission.text }}</a></p>
            {% endif %}

            {% if related_sites %}
            {% for section in related_sites %}
            <h2 class="nav-level-one">{{ section.title }}</h2>
            <ul class="related-links nav-level-two">
                {% for link in section.links %}
                <li class="nav-level-three"><a href="{{ link.url }}">{{ link.name }}</a></li>
                {% endfor %}
            </ul>
            {% endfor %}
            {% endif %}
        </aside>
    </div>

    <footer>
        <p><a href="{{ feed_links.atom or '/feed.atom' }}">Atom</a> · <a href="{{ feed_links.rss or '/feed.rss' }}">RSS</a> · <a href="{{ feed_links.opml or '/feeds.opml' }}">OPML</a></p>
        <p>{{ footer_text }}{% if show_admin_link %} · <a href="/admin" style="color: #999; font-size: 0.8em;">Admin</a>{% endif %} · <span class="hint">Press <kbd>?</kbd> for shortcuts</span></p>
        <p>Last updated: {{ generated_at }}</p>
    </footer>

    <!-- Keyboard shortcuts help panel -->
    <div class="shortcuts-backdrop hidden" id="shortcuts-backdrop"></div>
    <div class="shortcuts-panel hidden" id="shortcuts-panel" role="dialog" aria-labelledby="shortcuts-title" aria-modal="true">
        <h3 id="shortcuts-title">Keyboard Shortcuts</h3>
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
        <button type="button" class="close-btn" id="close-shortcuts">Close</button>
    </div>

    <script src="/static/keyboard-nav.js"></script>
</body>
</html>
""",
        "titles.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ planet.name }} - Titles Only</title>
    <link rel="icon" href="/static/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/style.css">
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="{{ feed_links.atom or '/feed.atom' }}">
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="{{ feed_links.rss or '/feed.rss' }}">
</head>
<body class="titles-only">
    <header>
        {% if logo %}
        <a href="/" class="logo-link">
            <img src="{{ logo.url }}" alt="{{ logo.alt }}" width="{{ logo.width }}" height="{{ logo.height }}" class="logo">
        </a>
        {% endif %}
        <div class="header-text">
            <h1><a href="/">{{ planet.name }}</a></h1>
            <p>{{ planet.description }}</p>
        </div>
    </header>

    <div class="container">
        <main>
            <p class="view-toggle"><a href="/">View full content</a></p>
            {% for date, day_entries in entries_by_date.items() %}
            <section class="day">
                <h2 class="date">{{ date }}</h2>
                {% set current_author = namespace(value='') %}
                {% for entry in day_entries %}
                    {% if entry.display_author != current_author.value %}
                        {% set current_author.value = entry.display_author %}
                <h3 class="post"><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}">{{ entry.display_author or 'Unknown' }}</a></h3>
                    {% endif %}
                <h4 class="entry-title"><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
                <p class="entry-meta"><em>{% if entry.display_author %}by {{ entry.display_author }} at {% endif %}{{ entry.published_at_display }}</em></p>
                {% endfor %}
            </section>
            {% else %}
            <p>No entries yet.</p>
            {% endfor %}
        </main>

        <aside class="sidebar">
            {% if feed_links and (feed_links.sidebar_rss or feed_links.titles_only or feed_links.planet_planet) %}
            <div class="sidebar-links">
                {% if feed_links.sidebar_rss %}<a href="{{ feed_links.sidebar_rss }}">RSS</a>{% endif %}
                {% if feed_links.titles_only %}<a href="{{ feed_links.titles_only }}">titles only</a>{% endif %}
                {% if feed_links.planet_planet %}<a href="{{ feed_links.planet_planet }}">Planet Planet</a>{% endif %}
            </div>
            {% endif %}

            {% if not is_lite_mode %}
            <form action="/search" method="GET" class="search-form">
                <label class="search-label"><strong>Search</strong></label>
                <input type="search" name="q" placeholder="Search entries..." aria-label="Search entries">
                <button type="submit">Search</button>
            </form>
            {% endif %}

            <h2>Subscriptions</h2>
            <ul class="feeds">
                {% for feed in feeds %}
                <li class="{{ 'healthy' if feed.is_healthy else 'unhealthy' }}">
                    {% if feed.url %}<a href="{{ feed.url }}" class="feed-icon" title="RSS Feed"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="6.18" cy="17.82" r="2.18"/><path d="M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56zm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"/></svg></a>{% endif %}
                    {% if feed.site_url %}<a href="{{ feed.site_url }}">{{ feed.title or 'Untitled' }}</a>{% else %}{{ feed.title or 'Untitled' }}{% endif %}
                </li>
                {% else %}
                <li>No feeds configured</li>
                {% endfor %}
            </ul>
            {% if submission %}
            <p class="submission-link"><a href="{{ submission.url }}">{{ submission.text }}</a></p>
            {% endif %}

            {% if related_sites %}
            {% for section in related_sites %}
            <h2 class="nav-level-one">{{ section.title }}</h2>
            <ul class="related-links nav-level-two">
                {% for link in section.links %}
                <li class="nav-level-three"><a href="{{ link.url }}">{{ link.name }}</a></li>
                {% endfor %}
            </ul>
            {% endfor %}
            {% endif %}
        </aside>
    </div>

    <footer>
        <p><a href="{{ feed_links.atom or '/feed.atom' }}">Atom</a> · <a href="{{ feed_links.rss or '/feed.rss' }}">RSS</a> · <a href="{{ feed_links.opml or '/feeds.opml' }}">OPML</a></p>
        <p>{{ footer_text }}{% if show_admin_link %} · <a href="/admin" style="color: #999; font-size: 0.8em;">Admin</a>{% endif %}</p>
        <p>Last updated: {{ generated_at }}</p>
    </footer>
</body>
</html>
""",
        "search.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search Results - {{ planet.name }}</title>
    <link rel="icon" href="/static/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1><a href="/">{{ planet.name }}</a></h1>
        <p>Search Results</p>
    </header>

    <div class="container">
        <main class="search-page">
            {% if error %}
            <div class="search-error">
                <p>{{ error }}</p>
            </div>
            {% else %}
            <h2>Results for "{{ query }}"</h2>
            {% if words_truncated %}
            <p class="search-notice">Note: Your search was limited to the first {{ max_search_words }} words.</p>
            {% endif %}
            {% if results %}
            <ul class="search-results">
                {% for entry in results %}
                <li>
                    <h3><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h3>
                    <p class="meta">{{ entry.display_author }}</p>
                </li>
                {% endfor %}
            </ul>
            {% else %}
            <p>No results found for "{{ query }}"</p>
            {% endif %}
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

    <footer><p><a href="/">Back to {{ planet.name }}</a></p></footer>
</body>
</html>
""",
        "admin/dashboard.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin - {{ planet.name }}</title>
    <link rel="icon" href="/static/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
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
        "admin/error.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error - {{ planet.name }} Admin</title>
    <link rel="icon" href="/static/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
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
        .error-card {
            background: white;
            padding: 3rem;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 500px;
            width: 90%;
        }
        .icon { font-size: 3rem; margin-bottom: 1rem; }
        h1 { color: #333; margin-bottom: 0.5rem; font-size: 1.5rem; }
        .error-message {
            color: #666;
            margin-bottom: 2rem;
            line-height: 1.5;
        }
        .actions {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }
        .btn {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.875rem 1.5rem;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            font-size: 1rem;
            transition: background 0.2s, transform 0.1s;
        }
        .btn:hover { transform: translateY(-1px); }
        .btn-primary {
            background: #667eea;
            color: white;
        }
        .btn-primary:hover { background: #5a6fd6; }
        .btn-secondary {
            background: #f0f0f0;
            color: #333;
        }
        .btn-secondary:hover { background: #e0e0e0; }
        .footer { margin-top: 2rem; color: #999; font-size: 0.875rem; }
        .footer a { color: #667eea; text-decoration: none; }
    </style>
</head>
<body>
    <div class="error-card">
        <div class="icon">&#9888;</div>
        <h1>{{ title or 'Something went wrong' }}</h1>
        <p class="error-message">{{ message }}</p>

        <div class="actions">
            {% if back_url %}
            <a href="{{ back_url }}" class="btn btn-primary">&#8592; Go Back</a>
            {% endif %}
            <a href="/admin" class="btn btn-secondary">Admin Dashboard</a>
        </div>

        <p class="footer">
            <a href="/">&#8592; Back to {{ planet.name }}</a>
        </p>
    </div>
</body>
</html>
""",
        "admin/health.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Feed Health - {{ planet.name }}</title>
    <link rel="icon" href="/static/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/style.css">
    <style>
        body { max-width: 1200px; margin: 0 auto; padding: 0; }
        header { display: flex; justify-content: space-between; align-items: center; text-align: left; padding: 1rem 1.5rem; }
        header h1 { margin: 0; font-size: 1.5rem; }
        header h1::before { display: none; }
        .header-actions { display: flex; gap: 0.75rem; }
        .health-content { padding: 1rem 1.5rem; }
        .summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
        .summary-card { padding: 1rem; background: var(--bg-tertiary); border-radius: 8px; text-align: center; }
        .summary-card .count { font-size: 2rem; font-weight: bold; }
        .summary-card .label { font-size: 0.875rem; color: var(--text-muted); }
        .summary-card.healthy .count { color: var(--success); }
        .summary-card.warning .count { color: #f59e0b; }
        .summary-card.failing .count { color: var(--error); }
        .summary-card.inactive .count { color: var(--text-muted); }
        .health-table { width: 100%; border-collapse: collapse; background: var(--bg-primary); border-radius: 8px; overflow: hidden; }
        .health-table th, .health-table td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid var(--border-light); }
        .health-table th { background: var(--bg-tertiary); font-weight: 600; font-size: 0.875rem; }
        .health-table tr:last-child td { border-bottom: none; }
        .health-table tr:hover { background: var(--bg-secondary); }
        .status-badge { padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
        .status-badge.healthy { background: #d1fae5; color: #065f46; }
        .status-badge.warning { background: #fef3c7; color: #92400e; }
        .status-badge.failing { background: #fee2e2; color: #991b1b; }
        .status-badge.inactive { background: #e5e7eb; color: #6b7280; }
        .feed-title { font-weight: 600; }
        .feed-url { font-size: 0.75rem; color: var(--text-muted); word-break: break-all; max-width: 300px; }
        .error-text { font-size: 0.75rem; color: var(--error); max-width: 200px; word-break: break-word; }
        .time-ago { font-size: 0.875rem; color: var(--text-muted); }
        .actions-cell { white-space: nowrap; }
        .actions-cell form { display: inline; }
        .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.75rem; }
        .table-responsive { overflow-x: auto; }
        @media (max-width: 768px) {
            .feed-url { max-width: 150px; }
            .health-table th, .health-table td { padding: 0.5rem; font-size: 0.875rem; }
        }
    </style>
</head>
<body>
    <header>
        <h1><a href="/">{{ planet.name }}</a> <span style="color: var(--text-muted); font-weight: normal; font-size: 0.875rem;">Feed Health</span></h1>
        <div class="header-actions">
            <a href="/admin" class="btn">Back to Dashboard</a>
        </div>
    </header>

    <div class="health-content">
        <div class="summary-cards">
            <div class="summary-card">
                <div class="count">{{ total_feeds }}</div>
                <div class="label">Total Feeds</div>
            </div>
            <div class="summary-card healthy">
                <div class="count">{{ healthy_count }}</div>
                <div class="label">Healthy</div>
            </div>
            <div class="summary-card warning">
                <div class="count">{{ warning_count }}</div>
                <div class="label">Warning</div>
            </div>
            <div class="summary-card failing">
                <div class="count">{{ failing_count }}</div>
                <div class="label">Failing</div>
            </div>
            <div class="summary-card inactive">
                <div class="count">{{ inactive_count }}</div>
                <div class="label">Inactive</div>
            </div>
        </div>

        <div class="table-responsive">
            <table class="health-table">
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>Feed</th>
                        <th>Last Fetch</th>
                        <th>Last Entry</th>
                        <th>Failures</th>
                        <th>Entries</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for feed in feeds %}
                    <tr>
                        <td>
                            <span class="status-badge {{ feed.health_status }}">{{ feed.health_status }}</span>
                        </td>
                        <td>
                            <div class="feed-title">{{ feed.title or 'Untitled' }}</div>
                            <div class="feed-url">{{ feed.url }}</div>
                            {% if feed.fetch_error and feed.health_status == 'failing' %}
                            <div class="error-text">{{ feed.fetch_error }}</div>
                            {% endif %}
                        </td>
                        <td class="time-ago">{{ feed.last_fetch_at or 'Never' }}</td>
                        <td class="time-ago">{{ feed.last_entry_at or 'Never' }}</td>
                        <td>{{ feed.consecutive_failures or 0 }}</td>
                        <td>{{ feed.entry_count or 0 }}</td>
                        <td class="actions-cell">
                            {% if feed.health_status == 'failing' %}
                            <form action="/admin/dlq/{{ feed.id }}/retry" method="POST" style="display: inline;">
                                <button type="submit" class="btn btn-sm">Retry</button>
                            </form>
                            {% endif %}
                            {% if feed.is_active %}
                            <form action="/admin/feeds/{{ feed.id }}" method="POST" style="display: inline;">
                                <input type="hidden" name="_method" value="PUT">
                                <input type="hidden" name="is_active" value="0">
                                <button type="submit" class="btn btn-sm btn-danger" onclick="return confirm('Deactivate this feed?')">Deactivate</button>
                            </form>
                            {% else %}
                            <form action="/admin/feeds/{{ feed.id }}" method="POST" style="display: inline;">
                                <input type="hidden" name="_method" value="PUT">
                                <input type="hidden" name="is_active" value="1">
                                <button type="submit" class="btn btn-sm btn-success">Activate</button>
                            </form>
                            {% endif %}
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                            No feeds configured yet.
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
""",
        "admin/login.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - {{ planet.name }}</title>
    <link rel="icon" href="/static/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
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
    },
    "planet-python": {
        "index.html": """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
  <meta http-equiv="content-type" content="text/html; charset=utf-8" />
  <title>{{ planet.name }}</title>
  <link rel="stylesheet" type="text/css" href="/static/styles/screen-switcher-default.css" />
  <link rel="stylesheet" type="text/css" href="/static/styles/netscape4.css" />
  <link rel="stylesheet" type="text/css" media="print" href="/static/styles/print.css" />
  <link rel="alternate stylesheet" type="text/css" href="/static/styles/largestyles.css" title="Large" />
  <link rel="alternate stylesheet" type="text/css" href="/static/styles/defaultfonts.css" title="Default fonts" />
  <meta name="generator" content="PlanetCF" />
  <meta name="keywords" content="Python weblog blog blogs blogger weblogger aggregator rss" />
  <meta name="description" content="{{ planet.description or 'Recent postings from Python-related blogs.' }}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="alternate" type="application/rss+xml" title="RSS" href="{{ feed_links.rss or '/feed.rss' }}" />
  <link rel="alternate" type="application/atom+xml" title="Atom" href="{{ feed_links.atom or '/feed.atom' }}" />
  <link rel="icon" href="/static/favicon.ico" sizes="32x32" />
  <style>
    /* Make images responsive */
    img {
        border: 0;
        height: auto;
        max-width: 100%;
        display: block;
        padding-top: 5px;
        padding-bottom: 35px;
    }
  </style>
</head>

<body>
  <!-- Logo -->
  <h1 id="logoheader">
    <a href="/" id="logolink" accesskey="1"><img id="logo"
src="{{ logo.url or '/static/images/python-logo.gif' }}" alt="{{ logo.alt or 'homepage' }}" border="0" /></a>
  </h1>
  <!-- Skip to Navigation -->
  <div class="skiptonav"><a href="#left-hand-navigation" accesskey="2"><img src="/static/images/trans.gif" id="skiptonav" alt="skip to navigation" border="0" width="1" height="1" /></a></div>
  <div class="skiptonav"><a href="#content-body" accesskey="3"><img src="/static/images/trans.gif" id="skiptocontent" alt="skip to content" border="0" width="1" height="1" /></a></div>

  <div id="content-body">
    <main id="body-main">

<h1 class="pageheading">{{ planet.name }}</h1>

<p>Last update: {{ generated_at }}

{% for date, day_entries in entries_by_date.items() %}


<h2>{{ date_labels[date] }}</h2>

{% set current_author = namespace(value='') %}
{% for entry in day_entries %}
{% if entry.display_author != current_author.value %}
{% set current_author.value = entry.display_author %}

<hr /><h3 class="post"><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}" title="{{ entry.display_author }}">{{ entry.display_author or 'Unknown' }}</a></h3>

{% endif %}

<h4><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
<p>
{{ entry.content | safe }}</p>
<p>
<em><a href="{{ entry.url or '#' }}">{{ entry.published_at_display }}</a></em>
</p>

{% endfor %}
{% else %}
<p>No entries yet.</p>
{% endfor %}


    </main>
  </div>

  <div id="left-hand-navigation">
    <div id="menu">
      <ul class="level-one">
          <li>
          <ul class="level-two">
             <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS feed</a></li>
             <li><a href="/titles">Titles Only</a></li>
             <li><a href="http://www.planetplanet.org/">Powered by Planet!</a></li>
          </ul></li>
          <li>Other Python Planets
            <ul class="level-two">
              <li><a href="http://terri.toybox.ca/python-soc/">Python Summer of Code</a></li>
              <li><a href="http://www.afpy.org/planet/">Planet Python Francophone</a></li>
              <li><a href="http://planeta.python.org.ar/">Planet Python Argentina</a></li>
              <li><a href="http://planet.python.org.br/">Planet Python Brasil</a></li>
              <li><a href="http://pl.python.org/planeta/">Planet Python Poland</a></li>
            </ul></li>
          <li>Python Libraries
          <ul class="level-two">
            <li><a href="http://planet.laptop.org/">OLPC</a></li>
            <li><a href="http://planet.pysoy.org/">PySoy</a></li>
            <li><a href="http://planet.scipy.org/">SciPy</a></li>
            <li><a href="http://planet.sympy.org/">SymPy</a></li>
            <li><a href="http://planet.twistedmatrix.com/">Twisted</a></li>
          </ul></li>
          <li>Python/Web Planets
          <ul class="level-two">
            <li><a href="http://planet.cherrypy.org/">CherryPy</a></li>
            <li><a href="http://www.djangoproject.com/community/">Django Community</a></li>
            <li><a href="http://planet.plone.org/">Plone</a></li>
            <li><a href="http://planet.turbogears.org/">Turbogears</a></li>
          </ul></li>
          <li>Other Languages
          <ul class="level-two">
            <li><a href="http://planet.haskell.org/">Haskell</a></li>
            <li><a href="http://planet.lisp.org/">Lisp</a></li>
            <li><a href="http://planet.parrotcode.org/">Parrot</a></li>
            <li><a href="http://planet.perl.org/">Perl</a></li>
            <li><a href="http://planetruby.0x42.net/">Ruby</a></li>
          </ul></li>
          <li>Databases
          <ul class="level-two">
            <li><a href="http://www.planetmysql.org/">MySQL</a></li>
            <li><a href="http://planet.postgresql.org/">PostgreSQL</a></li>
          </ul></li>
          <li>Subscriptions
          <ul class="level-two">
<li><a href="{{ feed_links.opml or '/feeds.opml' }}">[OPML feed]</a></li>
{% for feed in feeds %}
<li{% if feed.is_inactive %} class="feed-inactive" title="Feed temporarily unavailable"{% endif %}><a href="{{ feed.site_url or feed.url or '#' }}" title="{{ feed.title }}">{{ feed.title or 'Untitled' }}</a>
</li>
{% else %}
<li>No feeds configured</li>
{% endfor %}

<li>
    <i>
    To request addition or removal,
    <a href="https://github.com/python/planet">open a PR or issue</a>
    </i>
</li>
          </ul></li>
      </ul>
    </div>
  </div>
</body>
</html>
""",
        "titles.html": """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
  <meta http-equiv="content-type" content="text/html; charset=utf-8" />
  <title>{{ planet.name }}</title>
  <link rel="stylesheet" type="text/css" href="/static/styles/screen-switcher-default.css" />
  <link rel="stylesheet" type="text/css" href="/static/styles/netscape4.css" />
  <link rel="stylesheet" type="text/css" media="print" href="/static/styles/print.css" />
  <link rel="alternate stylesheet" type="text/css" href="/static/styles/largestyles.css" title="Large" />
  <link rel="alternate stylesheet" type="text/css" href="/static/styles/defaultfonts.css" title="Default fonts" />
  <meta name="generator" content="PlanetCF" />
  <meta name="keywords" content="Python weblog blog blogs blogger weblogger aggregator rss" />
  <meta name="description" content="{{ planet.description or 'Recent postings from Python-related blogs.' }}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="alternate" type="application/rss+xml" title="RSS" href="{{ feed_links.rss or '/feed.rss' }}" />
  <link rel="alternate" type="application/atom+xml" title="Atom" href="{{ feed_links.atom or '/feed.atom' }}" />
  <link rel="icon" href="/static/favicon.ico" sizes="32x32" />
</head>

<body>
  <!-- Logo -->
  <h1 id="logoheader">
    <a href="/" id="logolink" accesskey="1"><img id="logo"
src="{{ logo.url or '/static/images/python-logo.gif' }}" alt="{{ logo.alt or 'homepage' }}" border="0" /></a>
  </h1>
  <!-- Skip to Navigation -->
  <div class="skiptonav"><a href="#left-hand-navigation" accesskey="2"><img src="/static/images/trans.gif" id="skiptonav" alt="skip to navigation" border="0" width="1" height="1" /></a></div>
  <div class="skiptonav"><a href="#content-body" accesskey="3"><img src="/static/images/trans.gif" id="skiptocontent" alt="skip to content" border="0" width="1" height="1" /></a></div>

  <div id="content-body">
    <main id="body-main">

<h1 class="pageheading">{{ planet.name }}</h1>

<p>Last update: {{ generated_at }}

{% for date, day_entries in entries_by_date.items() %}


<h2>{{ date_labels[date] }}</h2>

{% set current_author = namespace(value='') %}
{% for entry in day_entries %}
{% if entry.display_author != current_author.value %}
{% set current_author.value = entry.display_author %}

<hr /><h3 class="post"><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}" title="{{ entry.display_author }}">{{ entry.display_author or 'Unknown' }}</a></h3>

{% endif %}

<h4><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
<p>
<em><a href="{{ entry.url or '#' }}">{{ entry.published_at_display }}</a></em>
</p>

{% endfor %}
{% else %}
<p>No entries yet.</p>
{% endfor %}


    </main>
  </div>

  <div id="left-hand-navigation">
    <div id="menu">
      <ul class="level-one">
          <li>
          <ul class="level-two">
             <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS feed</a></li>
             <li><a href="/">Full content</a></li>
             <li><a href="http://www.planetplanet.org/">Powered by Planet!</a></li>
          </ul></li>
          <li>Subscriptions
          <ul class="level-two">
<li><a href="{{ feed_links.opml or '/feeds.opml' }}">[OPML feed]</a></li>
{% for feed in feeds %}
<li><a href="{{ feed.site_url or feed.url or '#' }}" title="{{ feed.title }}">{{ feed.title or 'Untitled' }}</a>
</li>
{% else %}
<li>No feeds configured</li>
{% endfor %}
          </ul></li>
      </ul>
    </div>
  </div>
</body>
</html>
""",
        "search.html": """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
  <meta http-equiv="content-type" content="text/html; charset=utf-8" />
  <title>Search Results - {{ planet.name }}</title>
  <link rel="stylesheet" type="text/css" href="/static/style.css" />
  <meta name="generator" content="PlanetCF" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="icon" href="/static/favicon.ico" sizes="32x32" />
</head>

<body>
  <!-- Logo -->
  <h1 id="logoheader">
    <a href="/" id="logolink" accesskey="1"><img id="logo"
src="{{ logo.url or '/static/images/python-logo.gif' }}" alt="{{ logo.alt or 'homepage' }}" border="0" /></a>
  </h1>
  <!-- Skip to Navigation -->
  <div class="skiptonav"><a href="#left-hand-navigation" accesskey="2"><img src="/static/images/trans.gif" id="skiptonav" alt="skip to navigation" border="0" width="1" height="1" /></a></div>
  <div class="skiptonav"><a href="#content-body" accesskey="3"><img src="/static/images/trans.gif" id="skiptocontent" alt="skip to content" border="0" width="1" height="1" /></a></div>

  <div id="content-body">
    <main id="body-main">

<h1 class="pageheading">Search Results</h1>

{% if error %}
<p style="color: #c00;">{{ error }}</p>
{% else %}
<h2>Results for "{{ query }}"</h2>
{% if words_truncated %}
<p><em>Note: Your search was limited to the first {{ max_search_words }} words.</em></p>
{% endif %}
{% if results %}
{% for entry in results %}

<hr /><h3 class="post"><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}" title="{{ entry.display_author }}">{{ entry.display_author or 'Unknown' }}</a></h3>

<h4><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
<p>
<em>{{ entry.published_at_display }}</em>
</p>

{% endfor %}
{% else %}
<p>No results found for "{{ query }}"</p>
{% endif %}
{% endif %}

    </main>
  </div>

  <div id="left-hand-navigation">
    <div id="menu">
      <ul class="level-one">
          <li>
          <ul class="level-two">
             <li><a href="/">Back to home</a></li>
             <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS feed</a></li>
          </ul></li>
      </ul>
      <form action="/search" method="get" style="margin: 1em;">
        <p>
          <input type="text" name="q" value="{{ query }}" style="width: 10em;" />
          <input type="submit" value="Search" />
        </p>
      </form>
    </div>
  </div>
</body>
</html>
""",
    },
    "planet-mozilla": {
        "index.html": """<?xml version="1.0"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
    <title>{{ planet.name }}</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <meta name="generator" content="PlanetCF"/>
    <meta name="description" content="Follow the pulse of the Mozilla project. Aggregated updates from the developers, designers, and volunteers building a better internet."/>
    <meta property="og:site_name" content="{{ planet.name }}"/>
    <meta property="og:title" content="{{ planet.name }}"/>
    <meta property="og:description" content="Follow the pulse of the Mozilla project. Aggregated updates from the developers, designers, and volunteers building a better internet."/>
    <meta property="og:image" content="{{ planet.link }}/static/img/planet_banner.png"/>
    <meta name="twitter:card" content="summary_large_image"/>
    <meta name="twitter:creator" content="@mozilla"/>
    <meta property="twitter:title" content="{{ planet.name }}"/>
    <meta property="twitter:image" content="{{ planet.link }}/static/img/planet_banner.png"/>
    <link href="/static/style.css" rel="stylesheet" type="text/css"/>
    <link href="/static/favicon.ico" rel="shortcut icon" type="image/png"/>
    <link rel="alternate" href="{{ feed_links.atom or '/feed.atom' }}" title="{{ planet.name }}" type="application/atom+xml"/>
</head>
<body>
    <div id="utility">
        <p><strong>Looking For</strong></p>
        <ul>
            <li><a href="https://www.mozilla.org/">mozilla.org</a></li>
            <li><a href="https://wiki.mozilla.org/">Wiki</a></li>
            <li><a href="https://developer.mozilla.org/">Developer Center</a></li>
            <li><a href="http://www.firefox.com/">Firefox</a></li>
            <li><a href="http://www.getthunderbird.com/">Thunderbird</a></li>
        </ul>
    </div>
    <div id="header">
        <div id="dino">
            <h1><a href="/" title="Back to home page">{{ planet.name }}</a></h1>
        </div>
    </div>
    <div class="main-container">
        <main class="main-content">
{% for date, day_entries in entries_by_date.items() %}
            <h2><time datetime="{{ date }}">{{ date_labels[date] }}</time></h2>
{% for entry in day_entries %}
            <article class="news">
                <h3><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}" title="{{ entry.display_author }}">{{ entry.display_author or 'Unknown' }}</a> — <a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h3>
                <div class="entry">
                    <div class="content">{{ entry.content | safe }}</div>
                </div>
                <div class="permalink"><a href="{{ entry.url or '#' }}">by {{ entry.display_author }} at <time datetime="{{ entry.published_at }}" title="GMT">{{ entry.published_at_display }}</time></a></div>
            </article>
{% endfor %}
{% else %}
            <p>No entries yet.</p>
{% endfor %}
        </main>
        <div class="sidebar-content">
            <div class="disclaimer">
                <h2>{{ planet.name }}</h2>
                <p>Collected here are the most recent blog posts from all over the Mozilla community.
                   The content here is unfiltered and uncensored, and represents the views of individual community members.
                   Individual posts are owned by their authors -- see original source for licensing information.</p>
            </div>
            <div class="feeds">
                <h2>Subscribe to Planet</h2>
                <p>Feeds:</p>
                <ul>
                    <li><a href="{{ feed_links.atom or '/feed.atom' }}">Atom</a></li>
                    <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS 2.0</a></li>
                    {% if feed_links.rss10 %}<li><a href="{{ feed_links.rss10 }}">RSS 1.0</a></li>{% endif %}
                </ul>
                <p></p>
                <p>Subscription list:</p>
                <ul>
                    {% if feed_links.foaf %}<li><a href="{{ feed_links.foaf }}">FOAF</a></li>{% endif %}
                    <li class="opml"><a href="{{ feed_links.opml or '/feeds.opml' }}">OPML</a></li>
                </ul>
                <p>Last update: <time datetime="{{ generated_at }}" title="GMT">{{ generated_at }}</time></p>
            </div>
            <div class="main">
                <h2>Other Planets</h2>
                <ul class="planets">
                    <li><a href="https://planet.mozilla.org/projects/">Projects</a></li>
                    <li><a href="https://planet.mozilla.org/participation/">Planet Participation</a></li>
                    <li><a href="https://planet.mozilla.org/thunderbird/">Planet Thunderbird</a></li>
                    <li><a href="https://quality.mozilla.org/">Planet QMO</a></li>
                    <li><a href="https://planet.mozilla.org/ateam/">Planet Automation</a></li>
                    <li><a href="https://planet.mozilla.org/research/">Mozilla Research</a></li>
                </ul>
                {% if not is_lite_mode %}
                <div id="sidebar">
                    <h2>Search</h2>
                    <form action="/search" method="GET">
                        <input name="q" type="search" placeholder="Search..."/>
                        <button type="submit">Search</button>
                    </form>
                </div>
                {% endif %}
                <h2>Subscriptions</h2>
                <ul class="subscriptions">
{% for feed in feeds %}
                    <li{% if feed.is_inactive %} class="feed-inactive" title="Feed temporarily unavailable"{% endif %}>
                        <a title="subscribe" href="{{ feed.url }}"><img src="/static/img/feed-icon-10x10.png" alt="(feed)" width="10" height="10"/></a>
                        <a href="{{ feed.site_url or feed.url or '#' }}"
                           {% if feed.message %}class="{{ 'active message' if feed.recent_entries else 'message' }}" title="{{ feed.message }}"
                           {% elif feed.recent_entries %}class="active" title="{{ feed.title }}"
                           {% else %}title="{{ feed.title }}"
                           {% endif %}>{{ feed.title or 'Untitled' }}</a>
                        {% if feed.recent_entries %}
                        <ul>
                            {% for entry in feed.recent_entries %}
                            <li><a href="{{ entry.url or '#' }}">{{ entry.title }}</a></li>
                            {% endfor %}
                        </ul>
                        {% endif %}
                    </li>
{% else %}
                    <li>No feeds configured</li>
{% endfor %}
                </ul>
            </div>
            <div class="bottom"></div>
        </div>
    </div>
    <div id="footer">
        <div id="footer-content">
            <p>{{ footer_text }}{% if show_admin_link %} | <a href="/admin">Admin</a>{% endif %}</p>
        </div>
    </div>
    <script>
    // Localize UTC dates to the user's timezone
    (function() {
        var times = document.querySelectorAll('time[datetime]');
        for (var i = 0; i < times.length; i++) {
            var el = times[i];
            var dt = el.getAttribute('datetime');
            if (!dt) continue;
            var d = new Date(dt.indexOf('T') === -1 && dt.indexOf('Z') === -1 ? dt + 'T00:00:00Z' : dt);
            if (isNaN(d.getTime())) continue;
            var parent = el.parentElement;
            if (parent && parent.tagName === 'H2') {
                el.textContent = d.toLocaleDateString(undefined, {weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'});
            } else {
                el.textContent = d.toLocaleString(undefined, {year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'});
            }
            el.setAttribute('title', dt + ' UTC');
        }
    })();
    </script>
</body>
</html>
""",
        "titles.html": """<?xml version="1.0"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
    <title>{{ planet.name }} - Titles Only</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <link href="/static/style.css" rel="stylesheet" type="text/css"/>
    <link href="/static/favicon.ico" rel="shortcut icon" type="image/png"/>
    <link rel="alternate" href="{{ feed_links.atom or '/feed.atom' }}" title="{{ planet.name }}" type="application/atom+xml"/>
</head>
<body>
    <div id="utility">
        <p><strong>Looking For</strong></p>
        <ul>
            <li><a href="https://www.mozilla.org/">mozilla.org</a></li>
            <li><a href="https://wiki.mozilla.org/">Wiki</a></li>
            <li><a href="https://developer.mozilla.org/">Developer Center</a></li>
            <li><a href="http://www.firefox.com/">Firefox</a></li>
            <li><a href="http://www.getthunderbird.com/">Thunderbird</a></li>
        </ul>
    </div>
    <div id="header">
        <div id="dino">
            <h1><a href="/" title="Back to home page">{{ planet.name }}</a></h1>
        </div>
    </div>
    <div class="main-container">
        <main class="main-content">
            <p><a href="/">View full content</a></p>
{% for date, day_entries in entries_by_date.items() %}
            <h2><time datetime="{{ date }}">{{ date_labels[date] }}</time></h2>
{% for entry in day_entries %}
            <article class="news">
                <h3><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}" title="{{ entry.display_author }}">{{ entry.display_author or 'Unknown' }}</a> — <a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h3>
                <div class="permalink"><a href="{{ entry.url or '#' }}">by {{ entry.display_author }} at <time datetime="{{ entry.published_at }}" title="GMT">{{ entry.published_at_display }}</time></a></div>
            </article>
{% endfor %}
{% else %}
            <p>No entries yet.</p>
{% endfor %}
        </main>
        <div class="sidebar-content">
            <div class="feeds">
                <h2>Subscribe to Planet</h2>
                <ul>
                    <li><a href="{{ feed_links.atom or '/feed.atom' }}">Atom</a></li>
                    <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS 2.0</a></li>
                    {% if feed_links.rss10 %}<li><a href="{{ feed_links.rss10 }}">RSS 1.0</a></li>{% endif %}
                </ul>
                <ul>
                    {% if feed_links.foaf %}<li><a href="{{ feed_links.foaf }}">FOAF</a></li>{% endif %}
                    <li class="opml"><a href="{{ feed_links.opml or '/feeds.opml' }}">OPML</a></li>
                </ul>
            </div>
            <div class="main">
                <h2>Subscriptions</h2>
                <ul class="subscriptions">
{% for feed in feeds %}
                    <li><a href="{{ feed.site_url or feed.url or '#' }}">{{ feed.title or 'Untitled' }}</a></li>
{% else %}
                    <li>No feeds configured</li>
{% endfor %}
                </ul>
            </div>
        </div>
    </div>
    <div id="footer">
        <div id="footer-content">
            <p>{{ footer_text }}{% if show_admin_link %} | <a href="/admin">Admin</a>{% endif %}</p>
            <p>Last updated: {{ generated_at }}</p>
        </div>
    </div>
    <script>
    // Localize UTC dates to the user's timezone
    (function() {
        var times = document.querySelectorAll('time[datetime]');
        for (var i = 0; i < times.length; i++) {
            var el = times[i];
            var dt = el.getAttribute('datetime');
            if (!dt) continue;
            var d = new Date(dt.indexOf('T') === -1 && dt.indexOf('Z') === -1 ? dt + 'T00:00:00Z' : dt);
            if (isNaN(d.getTime())) continue;
            var parent = el.parentElement;
            if (parent && parent.tagName === 'H2') {
                el.textContent = d.toLocaleDateString(undefined, {weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'});
            } else {
                el.textContent = d.toLocaleString(undefined, {year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'});
            }
            el.setAttribute('title', dt + ' UTC');
        }
    })();
    </script>
</body>
</html>
""",
        "search.html": """<?xml version="1.0"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
    <title>Search Results - {{ planet.name }}</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <link href="/static/style.css" rel="stylesheet" type="text/css"/>
    <link href="/static/favicon.ico" rel="shortcut icon" type="image/png"/>
</head>
<body>
    <div id="utility">
        <p><strong>Looking For</strong></p>
        <ul>
            <li><a href="https://www.mozilla.org/">mozilla.org</a></li>
            <li><a href="https://wiki.mozilla.org/">Wiki</a></li>
            <li><a href="https://developer.mozilla.org/">Developer Center</a></li>
            <li><a href="http://www.firefox.com/">Firefox</a></li>
            <li><a href="http://www.getthunderbird.com/">Thunderbird</a></li>
        </ul>
    </div>
    <div id="header">
        <div id="dino">
            <h1><a href="/" title="Back to home page">{{ planet.name }}</a></h1>
        </div>
    </div>
    <div class="main-container">
        <main class="main-content">
            <h2>Search Results</h2>
{% if error %}
            <div class="search-error">
                <p>{{ error }}</p>
            </div>
{% else %}
            <h3>Results for "{{ query }}"</h3>
{% if words_truncated %}
            <p><em>Note: Your search was limited to the first {{ max_search_words }} words.</em></p>
{% endif %}
{% if results %}
{% for entry in results %}
            <article class="news">
                <h3><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}" title="{{ entry.display_author }}">{{ entry.display_author or 'Unknown' }}</a> — <a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h3>
                <div class="permalink">by {{ entry.display_author }} at {{ entry.published_at_display }}</div>
            </article>
{% endfor %}
{% else %}
            <p>No results found for "{{ query }}"</p>
{% endif %}
{% endif %}
        </main>
        <div class="sidebar-content">
            <div class="main">
                <div id="sidebar">
                    <h2>Search</h2>
                    <form action="/search" method="GET">
                        <input name="q" type="search" value="{{ query }}" placeholder="Search..."/>
                        <button type="submit">Search</button>
                    </form>
                </div>
                <p><a href="/">Back to home</a></p>
            </div>
        </div>
    </div>
    <div id="footer">
        <div id="footer-content">
            <p><a href="/">Back to {{ planet.name }}</a></p>
        </div>
    </div>
</body>
</html>
""",
    },
    "_shared": {
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
        "feed.rss10.xml": """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="{{ planet.link }}">
    <title>{{ planet.name | e }}</title>
    <link>{{ planet.link }}</link>
    <description>{{ planet.description | e }}</description>
    <items>
      <rdf:Seq>
{% for entry in entries %}
        <rdf:li rdf:resource="{{ entry.url | e }}"/>
{% endfor %}
      </rdf:Seq>
    </items>
  </channel>
{% for entry in entries %}
  <item rdf:about="{{ entry.url | e }}">
    <title>{{ entry.title | e }}</title>
    <link>{{ entry.url | e }}</link>
    <dc:date>{{ entry.published_at_iso }}</dc:date>
    <dc:creator>{{ entry.author | e }}</dc:creator>
    <description><![CDATA[{{ entry.content_truncated }}]]></description>
  </item>
{% endfor %}
</rdf:RDF>
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
        "foafroll.xml": """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:foaf="http://xmlns.com/foaf/0.1/"
         xmlns:rss="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <foaf:Group>
    <foaf:name>{{ planet.name | e }}</foaf:name>
    <foaf:homepage rdf:resource="{{ planet.link }}"/>
{% for feed in feeds %}
    <foaf:member>
      <foaf:Agent>
        <foaf:name>{{ feed.title | e }}</foaf:name>
        <foaf:weblog rdf:resource="{{ feed.site_url | e }}"/>
        <foaf:member_weblog>
          <foaf:Document rdf:about="{{ feed.site_url | e }}">
            <dc:title>{{ feed.title | e }}</dc:title>
            <rss:channel rdf:resource="{{ feed.url | e }}"/>
          </foaf:Document>
        </foaf:member_weblog>
      </foaf:Agent>
    </foaf:member>
{% endfor %}
  </foaf:Group>
</rdf:RDF>
""",
    },
}


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
TEMPLATE_FOAFROLL = "foafroll.xml"

# =============================================================================
# Theme-specific Logos (for multi-instance deployments)
# =============================================================================
# Note: Theme CSS is now served via Cloudflare's ASSETS binding (static files).

THEME_LOGOS = {
    "planet-python": {
        "url": "/static/images/python-logo.gif",
        "width": "211",
        "height": "71",
        "alt": "Planet Python",
        "svg": """""",
    },
    "planet-mozilla": {
        "url": "/static/img/logo.png",
        "width": "222",
        "height": "44",
        "alt": "Planet Mozilla",
        "svg": """""",
    },
}
