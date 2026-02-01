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
    <link rel="icon" href="/static/favicon.ico" sizes="32x32">
    <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
    <link rel="stylesheet" href="/static/style.css">
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="{{ feed_links.atom or '/feed.atom' }}">
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="{{ feed_links.rss or '/feed.rss' }}">
</head>
<body{% if theme == 'planet-mozilla' %} class="theme-mozilla"{% endif %}>
    {% if theme == 'planet-mozilla' %}
    <nav class="mozilla-nav" aria-label="Mozilla corporate navigation">
        <div class="mozilla-nav-inner">
            <span class="mozilla-nav-label">Looking For:</span>
            <a href="https://www.mozilla.org/">mozilla.org</a>
            <a href="https://wiki.mozilla.org/">Wiki</a>
            <a href="https://developer.mozilla.org/">Developer Center</a>
            <a href="https://www.mozilla.org/firefox/">Firefox</a>
            <a href="https://www.thunderbird.net/">Thunderbird</a>
        </div>
    </nav>
    {% endif %}
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
            {% if feed_links %}
            <div class="sidebar-links">
                <a href="{{ feed_links.rss or '/feed.rss' }}">RSS</a>
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
        <p>{{ footer_text }}{% if show_admin_link %} · <a href="/admin" style="color: #999; font-size: 0.8em;">Admin</a>{% endif %} · <span class="hint">Press <kbd>?</kbd> for shortcuts</span></p>
        <p>Last update: {{ generated_at }}</p>
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
<body class="titles-only{% if theme == 'planet-mozilla' %} theme-mozilla{% endif %}">
    {% if theme == 'planet-mozilla' %}
    <nav class="mozilla-nav" aria-label="Mozilla corporate navigation">
        <div class="mozilla-nav-inner">
            <span class="mozilla-nav-label">Looking For:</span>
            <a href="https://www.mozilla.org/">mozilla.org</a>
            <a href="https://wiki.mozilla.org/">Wiki</a>
            <a href="https://developer.mozilla.org/">Developer Center</a>
            <a href="https://www.mozilla.org/firefox/">Firefox</a>
            <a href="https://www.thunderbird.net/">Thunderbird</a>
        </div>
    </nav>
    {% endif %}
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
            {% if feed_links %}
            <div class="sidebar-links">
                <a href="{{ feed_links.rss or '/feed.rss' }}">RSS</a>
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
        <p>Last update: {{ generated_at }}</p>
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
    display: flex;
    align-items: center;
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

.feeds li .feed-icon {
    display: flex;
    align-items: center;
    margin-right: 0.5rem;
}

.feeds li.healthy::before {
    content: '';
    flex-shrink: 0;
    width: 6px;
    height: 6px;
    background: var(--accent);
    border-radius: 50%;
    margin-right: 0.5rem;
}

.feeds li.unhealthy a:not(.feed-icon) {
    border-bottom: 1px dashed var(--text-primary);
}

.feeds li.unhealthy::before {
    content: '';
    flex-shrink: 0;
    width: 6px;
    height: 6px;
    background: var(--error);
    border-radius: 50%;
    margin-right: 0.5rem;
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

footer .hint {
    color: var(--text-muted);
    font-size: 0.8rem;
}

footer .hint kbd {
    display: inline-block;
    background: var(--bg-secondary);
    border: 1px solid var(--border-light);
    border-radius: 3px;
    padding: 0.1rem 0.35rem;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.75rem;
}

/* Search errors */
.search-error {
    background: var(--accent-light);
    border: 1px solid var(--accent-subtle);
    border-radius: 8px;
    padding: 1rem 1.5rem;
    margin-bottom: 1.5rem;
    color: var(--text-secondary);
}

.search-error p {
    margin: 0;
}

.search-notice {
    background: #f0f7ff;
    border: 1px solid #c9e0ff;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 1rem;
    color: var(--text-secondary);
    font-size: 0.9rem;
}

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

.shortcuts-panel .close-btn {
    margin-top: 1rem;
    width: 100%;
    padding: 0.5rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border-light);
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
    color: var(--text-secondary);
    transition: background 0.15s ease;
}

.shortcuts-panel .close-btn:hover {
    background: var(--bg-secondary);
}

.shortcuts-panel .close-btn:focus {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
}

/* Titles-only page styles */
.titles-only .view-toggle {
    margin-bottom: 1rem;
    font-size: 0.9em;
}

.titles-only .view-toggle a {
    color: var(--accent);
    text-decoration: none;
}

.titles-only .view-toggle a:hover {
    text-decoration: underline;
}

.titles-only .day {
    margin-bottom: 1rem;
}

.titles-only .day h2.date {
    margin-bottom: 0.5em;
    padding-bottom: 0.25em;
}

.titles-only .titles-list {
    list-style: none;
    margin: 0;
    padding: 0;
}

.titles-only .titles-list li {
    padding: 0.3em 0;
    border-bottom: 1px dotted var(--border-light);
    line-height: 1.4;
}

.titles-only .titles-list li:last-child {
    border-bottom: none;
}

.titles-only .entry-title {
    color: var(--accent);
    text-decoration: none;
}

.titles-only .entry-title:hover {
    text-decoration: underline;
}

.titles-only .entry-meta {
    font-size: 0.85em;
    color: var(--text-secondary);
    margin-left: 0.5em;
}

.titles-only .entry-meta .author {
    color: var(--text-primary);
}

.titles-only .entry-meta .date-sep {
    margin: 0 0.25em;
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
    const closeBtn = document.getElementById('close-shortcuts');
    let current = -1;
    let previousFocus = null;

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

    function openHelp() {
        if (panel && backdrop) {
            previousFocus = document.activeElement;
            panel.classList.remove('hidden');
            backdrop.classList.remove('hidden');
            // Focus the close button for accessibility
            if (closeBtn) closeBtn.focus();
        }
    }

    function closeHelp() {
        if (panel && backdrop) {
            panel.classList.add('hidden');
            backdrop.classList.add('hidden');
            // Restore focus
            if (previousFocus && previousFocus.focus) {
                previousFocus.focus();
            }
            previousFocus = null;
        }
    }

    function toggleHelp() {
        if (panel && !panel.classList.contains('hidden')) {
            closeHelp();
        } else {
            openHelp();
        }
    }

    function isHelpOpen() {
        return panel && !panel.classList.contains('hidden');
    }

    if (backdrop) {
        backdrop.addEventListener('click', closeHelp);
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', closeHelp);
    }

    // Focus trap: keep focus within modal when open
    if (panel) {
        panel.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                // Only element to focus is the close button
                if (closeBtn) {
                    e.preventDefault();
                    closeBtn.focus();
                }
            }
        });
    }

    document.addEventListener('keydown', function(e) {
        // Ignore if typing in input/textarea (unless in modal)
        if (!isHelpOpen() && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;

        // When modal is open, only handle Escape and ?
        if (isHelpOpen()) {
            if (e.key === 'Escape' || e.key === '?') {
                e.preventDefault();
                closeHelp();
            }
            return;
        }

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
            openHelp();
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
TEMPLATE_TITLES = "titles.html"
TEMPLATE_SEARCH = "search.html"
TEMPLATE_ADMIN_DASHBOARD = "admin/dashboard.html"
TEMPLATE_ADMIN_ERROR = "admin/error.html"
TEMPLATE_ADMIN_LOGIN = "admin/login.html"
TEMPLATE_FEED_ATOM = "feed.atom.xml"
TEMPLATE_FEED_RSS = "feed.rss.xml"
TEMPLATE_FEEDS_OPML = "feeds.opml"

# =============================================================================
# Theme-specific CSS and Logos (for multi-instance deployments)
# =============================================================================

THEME_CSS = {
    "planet-python": """/* Planet Python Theme - EXACT recreation of planetpython.org */
/* Source: https://github.com/python/planet/blob/main/static/styles/styles.css */
/* Key features: LEFT sidebar, Georgia headings, #366D9C blue, minimal styling */

* {
    box-sizing: border-box;
}

HTML, body {
    margin: 0;
    padding: 0;
    font-family: Arial, Verdana, Geneva, "Bitstream Vera Sans", Helvetica, sans-serif;
    font-size: 103%;
    color: #000;
    background-color: #FFF;
}

IMG {
    border: 0;
}

/* Headings - Georgia serif family */
h1, h2, h3, h4, h5 {
    font-family: Georgia, "Bitstream Vera Serif", "New York", Palatino, serif;
    font-weight: normal;
    line-height: 1em;
}

h1 {
    font-size: 160%;
    color: #234764;
    margin: 0.7em 0;
    text-decoration: none;
}

h1 a {
    color: #234764;
    text-decoration: none;
}

h2 {
    font-size: 140%;
    color: #366D9C;
    margin: 0.7em 0;
}

h3 {
    font-size: 135%;
    font-style: italic;
    color: #366D9C;
    margin: 0.4em 0 0 0;
}

h4 {
    font-size: 125%;
    color: #366D9C;
    margin: 0.4em 0 0 0;
}

/* Links - Python.org style */
a:link {
    color: #00A;
    text-decoration: none;
}

a:visited {
    color: #551A8B;
    text-decoration: none;
}

a:hover {
    color: #00A;
    text-decoration: underline;
}

/* Logo Header - Exact python.org style */
header {
    border: 0;
    margin: 0;
    padding: 1px;
    z-index: 1;
    background-color: #F7F7F7;
    background-repeat: repeat-x;
    border-bottom: 1px solid #999999;
    height: 84px;
}

header .logo-link {
    display: block;
}

header .logo {
    width: 211px;
    height: 71px;
    margin-top: 10px;
    margin-left: 3%;
    border: 0;
}

header .header-text {
    display: none; /* Original site shows logo only */
}

header h1,
header p {
    display: none; /* Hide text header - logo only */
}

/* Container - LEFT sidebar layout */
.container {
    position: relative;
    width: 93.9%;
    margin-left: 3.0%;
    font-size: 75%;
    min-width: 660px;
    display: flex;
    flex-direction: row;
    padding-top: 20px;
}

/* Sidebar - Left position - #menu in original */
.sidebar {
    width: 16em;
    flex-shrink: 0;
    order: -1; /* Force left side */
    padding: 0;
    margin: 0;
    font-size: 75%; /* Original #menu font-size: 75% */
}

.sidebar h2 {
    font-family: Arial, Verdana, Geneva, "Bitstream Vera Sans", Helvetica, sans-serif;
    font-size: 77%;
    font-weight: bold;
    color: #4C5B6B;
    padding: 0.4em 0 0 1.5em;
    margin: 0.2em 0 0.3em 0;
    background: none;
    border: none;
    text-transform: none;
}

.sidebar h2 a {
    color: #4C5B6B;
    text-decoration: none;
    font-weight: bold;
}

.sidebar h2 a:hover {
    color: black;
    text-decoration: underline;
}

/* Sidebar links (RSS, titles-only) */
.sidebar-links {
    margin-bottom: 1em;
    padding-left: 1.5em;
    font-size: 100%;
}

.sidebar-links a {
    margin-right: 10px;
    color: #00A;
}

.sidebar-links a:visited {
    color: #551A8B;
}

/* Search form - hide for authenticity */
.search-form {
    display: none;
}

/* Feeds list - Menu style with borders */
.feeds {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: 100%;
}

.feeds li {
    display: inline;
}

.feeds li a {
    display: block;
    border: 1px solid #DADADA;
    padding: 2px 2px 2px 4px;
    margin: 0 0 4px 1.4em;
    width: 12em;
    font-family: Verdana, Geneva, "Bitstream Vera Sans", Helvetica, sans-serif;
    color: #4B5A6A;
    background-color: #F5F5F5;
    text-transform: uppercase;
    text-decoration: none;
    font-size: 100%;
}

.feeds li a:hover {
    color: black;
    text-decoration: underline;
}

/* Remove health indicators - not in original */
.feeds li.healthy::before,
.feeds li.unhealthy::before {
    display: none;
    content: none;
}

/* RSS icon in sidebar - hide for authenticity */
.feeds li .feed-icon {
    display: none;
}

/* Submission link */
.submission-link {
    margin-top: 1em;
    padding-left: 1.5em;
    font-size: 100%;
    border: none;
}

.submission-link a {
    color: #00A;
}

/* Navigation sections - Level hierarchy */
.nav-level-one,
h2.nav-level-one {
    font-family: Arial, Verdana, Geneva, "Bitstream Vera Sans", Helvetica, sans-serif;
    font-size: 77%;
    font-weight: bold;
    color: #4C5B6B;
    padding: 0.4em 0 0 1.5em;
    margin: 0.2em 0 0.3em 0;
    background: none;
    border: none;
    text-transform: none;
}

.nav-level-two,
ul.nav-level-two,
.related-links {
    list-style: none;
    margin: 0;
    padding: 0;
    margin-bottom: 7px;
}

.nav-level-two li,
.related-links li {
    display: inline;
}

.nav-level-two li a,
.related-links li a {
    background-color: transparent;
    display: block;
    border: 0;
    border-top: 1px solid #DDD;
    padding: 0.1em;
    margin: 0 3em 0px 1.5em;
    color: #3C4B7B;
    background: none;
    width: 11em;
    font-family: Arial, Verdana, Geneva, "Bitstream Vera Sans", Helvetica, sans-serif;
    text-transform: none;
    text-decoration: none;
}

.nav-level-two li a:hover,
.related-links li a:hover {
    text-decoration: underline;
    color: black;
}

.nav-level-two li a:visited,
.related-links li a:visited {
    color: #4C3B5B;
}

.nav-level-three,
li.nav-level-three {
    margin-left: 0;
}

.nav-level-three a {
    display: block;
    border: 0;
    padding: 0.1em;
    margin: 0 3em 0px 1.8em;
    padding-left: 1em;
    color: #5E72A5;
    background-image: none;
    width: 10em;
    font-family: Arial, Verdana, Geneva, "Bitstream Vera Sans", Helvetica, sans-serif;
    font-size: 95%;
}

.nav-level-three a:hover {
    text-decoration: underline;
    color: black;
}

/* Main content area - #body-main in original */
main {
    padding: 0 0.55em 40px 0;
    line-height: 1.4em;
    font-family: Arial, Verdana, Geneva, "Bitstream Vera Sans", Helvetica, sans-serif;
    margin-left: 3em; /* Original uses margin-left: 19em but we use flex layout */
    flex: 1;
    min-width: 0;
    font-size: 100%;
}

/* Day headers */
.day {
    margin-bottom: 1.5em;
}

.day h2 {
    font-size: 140%;
    font-weight: normal;
    margin-bottom: 0.5em;
    padding: 0;
    border: none;
}

.day h2.date {
    font-family: Georgia, "Bitstream Vera Serif", "New York", Palatino, serif;
    font-size: 140%;
    color: #366D9C;
    font-weight: normal;
    font-style: normal;
}

/* Articles */
article {
    margin-bottom: 1.5em;
    padding-bottom: 1em;
    border-bottom: none;
}

article h3 {
    font-family: Georgia, "Bitstream Vera Serif", "New York", Palatino, serif;
    font-size: 135%;
    font-weight: normal;
    font-style: italic;
    color: #366D9C;
    margin: 0.4em 0 0 0;
}

article h3 a {
    color: #00A;
    text-decoration: none;
}

article h3 a:visited {
    color: #551A8B;
}

article h3 a:hover {
    text-decoration: underline;
}

/* Article header reset */
article header {
    background: transparent;
    border: none;
    height: auto;
    min-height: auto;
    padding: 0;
    display: block;
}

/* Author/meta information */
.meta {
    font-size: 100%;
    color: #000;
    margin-bottom: 0.5em;
}

.meta .author {
    color: #000;
    font-weight: normal;
}

.meta .author a {
    color: #00A;
}

.meta .date-sep {
    margin: 0 3px;
}

/* Content area */
.content {
    font-size: 100%;
    line-height: 1.4em;
    color: #000;
}

.content p {
    margin: 0 0 1em 0;
}

.content p:last-child {
    margin-bottom: 0;
}

.content img {
    max-width: 100%;
    height: auto;
    border: 0;
}

.content a:link {
    color: #00A;
    text-decoration: none;
}

.content a:visited {
    color: #551A8B;
    text-decoration: none;
}

.content a:hover {
    text-decoration: underline;
}

.content ul, .content ol {
    margin-left: 1em;
    padding-left: 0;
}

.content li {
    margin-bottom: 0.3em;
}

.content code {
    font-family: "Courier New", Courier, monospace;
    font-size: 100%;
}

.content pre {
    font-family: "Courier New", Courier, monospace;
    font-size: 115%;
    background: #E0E0FF;
    padding: 10px;
    overflow-x: auto;
    margin: 1em 0;
}

.content pre code {
    background: transparent;
    padding: 0;
}

.content blockquote {
    margin-left: 1em;
    padding-left: 1em;
    border-left: 1px solid #CCC;
}

.content table {
    border-collapse: collapse;
    margin: 1em 0;
}

.content th, .content td {
    border: 1px solid #DADADA;
    padding: 5px;
}

/* Footer */
footer {
    margin: 3em 0 0 0;
    padding: 1em 0;
    border-top: 1px dotted #CCC;
    bottom: 0;
    font-size: 90%;
    position: relative;
    clear: both;
    background: #FFF;
    text-align: center;
    color: #000;
}

footer a:visited, footer a:link {
    color: #666;
    display: inline;
}

footer a:hover {
    color: #333;
    display: inline;
}

footer p {
    margin: 0.5em 0;
}

footer kbd {
    font-family: "Courier New", Courier, monospace;
    font-size: 100%;
}

/* Horizontal rule separators */
hr {
    border: none;
    border-top: 1px solid #DADADA;
    margin: 1em 0;
}

/* Keyboard shortcuts panel */
.shortcuts-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 999;
}

.shortcuts-backdrop.hidden {
    display: none;
}

.shortcuts-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #FFF;
    border: 1px solid #000;
    padding: 15px;
    z-index: 1000;
    min-width: 250px;
}

.shortcuts-panel.hidden {
    display: none;
}

.shortcuts-panel h3 {
    font-size: 14px;
    font-weight: bold;
    margin-bottom: 10px;
    padding-bottom: 5px;
    border-bottom: 1px solid #DADADA;
    font-style: normal;
}

.shortcuts-panel dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 5px 10px;
}

.shortcuts-panel dt {
    text-align: right;
}

.shortcuts-panel kbd {
    font-family: "Courier New", Courier, monospace;
    background: #f5f5f5;
    border: 1px solid #DADADA;
    padding: 2px 5px;
}

.shortcuts-panel .close-btn {
    margin-top: 10px;
    background: #f5f5f5;
    border: 1px solid #999999;
    padding: 5px 10px;
    cursor: pointer;
}

.shortcuts-panel .close-btn:hover {
    background: #e5e5e5;
}

/* Responsive - Stack on small screens */
@media (max-width: 700px) {
    .container {
        flex-direction: column;
        width: 95%;
        margin-left: 2.5%;
        min-width: auto;
    }

    .sidebar {
        width: 100%;
        order: 1;
        margin-top: 2em;
        border-top: 1px solid #DADADA;
        padding-top: 1em;
    }

    main {
        margin-left: 0;
    }

    header .logo {
        max-width: 150px;
        height: auto;
    }
}

/* Titles-only page styles */
.titles-only .view-toggle {
    margin-bottom: 1em;
    padding-left: 1.5em;
}

.titles-only .day {
    margin-bottom: 1em;
}

.titles-only h3.post {
    font-family: Georgia, "Bitstream Vera Serif", serif;
    font-size: 135%;
    font-style: italic;
    color: #366D9C;
    margin-top: 0.5em;
    margin-bottom: 3px;
}

.titles-only h4.entry-title {
    font-size: 100%;
    font-weight: normal;
    margin: 3px 0;
}

.titles-only h4.entry-title a {
    color: #00A;
}

.titles-only p.entry-meta {
    font-size: 100%;
    color: #000;
    margin: 0 0 0.5em 0;
}

/* Print styles */
@media print {
    .sidebar, .search-form, footer {
        display: none;
    }

    .container {
        display: block;
    }

    header {
        border-bottom: 1px solid black;
    }

    article {
        page-break-inside: avoid;
    }
}
""",
    "planet-mozilla": """/* Planet Mozilla Theme - EXACT recreation of planet.mozilla.org */
/* Key features: RIGHT sidebar, #455372 dark header, #148cb5 teal links, square bullets */

* {
    box-sizing: border-box;
    line-height: 1.4; /* Original: line-height: 1.4 on * */
    padding: 0;
}

ul, ol {
    padding-left: 22px; /* Original: padding-left: 22px */
}

body {
    font-family: Helvetica, Arial, Verdana, sans-serif;
    font-size: 13px;
    line-height: 1.4;
    color: #000;
    background: #fff;
    margin: 0;
    padding: 0;
}

/* Links - Mozilla teal/purple scheme */
a:link {
    color: #148cb5;
    text-decoration: none;
}

a:visited {
    color: #636;
}

a:hover {
    text-decoration: underline !important;
    color: #148cb5 !important;
}

a:active {
    color: #000;
}

/* Headings */
h1 {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 24px;
    font-weight: normal;
    letter-spacing: -2px;
    text-transform: lowercase;
    color: white;
    margin: 0;
    padding: 0;
}

h2 {
    font-family: Georgia, Times, "Times New Roman", serif;
    font-size: 1.75em;
    font-weight: normal;
    color: #b72822;
    margin-bottom: 0; /* Original: margin-bottom: 0 */
}

h3 {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 120%;
    font-weight: bold;
    margin-top: 10px; /* Original: margin-top: 10px */
    border-bottom: 1px solid #ccc;
}

h3 a {
    text-decoration: none;
    color: black;
}

h4 {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 100%;
    font-weight: bold;
    margin: 0 0 0 15px;
    clear: both;
    border-bottom: 1px solid #ccc;
}

/* Mozilla "Looking For" Navigation Bar at top */
.mozilla-nav {
    background: transparent;
    padding: 0 0 10px 0;
    font-family: "Trebuchet MS", sans-serif;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border-bottom: none;
    margin-bottom: 10px;
}

.mozilla-nav-inner {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}

.mozilla-nav-label {
    color: #666;
    font-weight: bold;
}

.mozilla-nav a {
    color: #148cb5;
    text-decoration: none;
}

.mozilla-nav a:visited {
    color: #636;
}

.mozilla-nav a:hover {
    text-decoration: underline !important;
    color: #148cb5 !important;
}

/* Header - Dark slate blue banner */
header {
    background: #455372;
    padding: 20px;
    border-bottom: none;
    border-radius: 0;
    margin-bottom: 1em;
}

header .logo-link {
    display: inline-block;
}

header .logo {
    height: 30px;
    width: auto;
    display: none; /* Original Mozilla doesn't show logo in header */
}

header .header-text {
    display: block;
}

header h1 {
    font-size: 24px;
    font-weight: normal;
    letter-spacing: -2px;
    text-transform: lowercase;
    margin: 0;
    padding: 0;
    background: transparent;
    display: inline;
}

header h1 a {
    color: #fff;
    text-decoration: none;
}

header h1 a:hover {
    color: #ccc;
    text-decoration: none !important;
}

header p {
    display: none; /* Hide description in header */
}

/* Container Layout - Content with right margin for sidebar */
.container {
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: row;
    gap: 20px;
}

/* Main content wrapper - .main-content in original */
.main-content {
    margin-left: 116px; /* Original: margin-left: 116px */
    margin-right: 260px; /* Original: margin-right: 260px */
}

/* Main content area - Takes most space, leaves room for sidebar */
main {
    flex: 1;
    min-width: 0;
    margin-right: 0;
}

/* Sidebar - HIDDEN for Mozilla (original has no sidebar) */
.sidebar {
    display: none; /* Original Planet Mozilla has single-column layout */
}

.sidebar h2 {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 150%;
    font-weight: bold;
    color: black;
    border-bottom: none;
    padding-left: 5px;
    margin-left: 0;
    margin-top: 0;
}

/* Sidebar links */
.sidebar-links {
    margin-bottom: 1em;
    font-size: 100%;
    padding-left: 5px;
}

.sidebar-links a {
    margin-right: 10px;
    color: #148cb5;
}

.sidebar-links a:visited {
    color: #636;
}

/* Search form - Mozilla style with rounded corners */
.search-form {
    margin-bottom: 1.5em;
    padding: 10px;
    margin-left: 20px;
    background: #e4ecec;
    -moz-border-radius: 1em;
    -webkit-border-radius: 1em;
    border-radius: 1em;
}

.search-form .search-label {
    display: block;
    font-weight: bold;
    margin-bottom: 5px;
    font-size: 12px;
}

.search-form input {
    width: 100%;
    padding: 5px;
    border: 1px solid #ccc;
    font-size: 12px;
    margin-bottom: 5px;
}

.search-form input:focus {
    outline: 1px solid #148cb5;
    border-color: #148cb5;
}

.search-form button {
    padding: 5px 10px;
    background: #f5f5f5;
    border: 1px solid #ccc;
    cursor: pointer;
    font-size: 11px;
}

.search-form button:hover {
    background: #e5e5e5;
}

/* Sidebar boxes - Mozilla style with rounded corners */
.sidebar > div,
.sidebar .sidebar-section {
    padding: 10px;
    margin-top: 0;
    margin-right: 0;
    margin-left: 20px;
    margin-bottom: 10px;
    background: transparent;
    -moz-border-radius: 1em;
    -webkit-border-radius: 1em;
    border-radius: 1em;
}

/* Feeds list - Square bullets like original */
.feeds {
    list-style-type: square;
    padding-left: 2em;
    margin-left: 0;
    font-size: 11px;
}

.feeds li {
    padding: 2px 0;
    border-bottom: none;
}

.feeds li:hover {
    color: grey;
}

/* Remove health indicators */
.feeds li.healthy::before,
.feeds li.unhealthy::before {
    display: none;
    content: none;
}

.feeds li a {
    color: #148cb5;
}

.feeds li a:visited {
    color: #636;
}

/* Hide RSS icon */
.feeds li .feed-icon {
    display: none;
}

/* Submission link */
.submission-link {
    margin-top: 1em;
    font-size: 11px;
    padding: 0 5px;
    border: none;
}

.submission-link a {
    color: #148cb5;
}

/* Navigation sections */
.nav-level-one,
h2.nav-level-one {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 150%;
    font-weight: bold;
    color: black;
    border-bottom: none;
    padding-left: 5px;
    margin-left: 0;
    margin-top: 1em;
    margin-bottom: 0.5em;
    background: none;
    text-transform: none;
}

.nav-level-two,
ul.nav-level-two,
.related-links {
    list-style-type: square;
    padding-left: 2em;
    margin-left: 0;
    font-size: 11px;
}

.nav-level-two li,
.related-links li {
    padding: 2px 0;
    border-bottom: none;
}

.nav-level-two li:hover,
.related-links li:hover {
    color: grey;
}

.nav-level-three,
li.nav-level-three {
    margin-left: 0;
}

/* Day headers - Date grouping with bottom border */
.day {
    margin-bottom: 2em;
}

.day h2 {
    font-family: Georgia, Times, "Times New Roman", serif;
    font-size: 1.75em;
    font-weight: normal;
    color: #b72822;
    border-bottom: 1px solid #ccc;
    margin-bottom: 0.5em;
    padding-bottom: 5px;
}

.day h2.date {
    font-family: Georgia, Times, "Times New Roman", serif;
    font-size: 1.75em;
    color: #b72822;
    font-weight: normal;
}

/* Articles / Entries - .entry in original */
article,
div.entry,
.entry {
    margin-left: 15px; /* Original: margin: 0 0 0 15px via .entry */
}

/* News styles from original */
.news .permalink {
    text-align: right; /* Original: text-align: right */
}

.news img {
    max-width: 100% !important; /* Original: max-width: 100% !important */
}

article:last-child {
    border-bottom: none;
}

article h3 {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 120%;
    font-weight: bold;
    margin-bottom: 3px;
    clear: both;
    border-bottom: 1px solid #ccc;
}

article h3 a {
    color: #148cb5;
    text-decoration: none;
}

article h3 a:visited {
    color: #636;
}

article h3 a:hover {
    text-decoration: underline !important;
}

/* Article header reset */
article header {
    background: transparent;
    border: none;
    border-radius: 0;
    min-height: auto;
    padding: 0;
    margin: 0;
    display: block;
}

/* Author/meta information */
.meta {
    font-size: 11px;
    color: #666;
    margin-bottom: 0.5em;
}

.meta .author {
    font-weight: bold;
    color: #333;
}

.meta .author a {
    color: #148cb5;
}

.meta .date-sep {
    margin: 0 5px;
    color: #999;
}

.entry .date {
    margin-top: 0.5em;
    text-align: right;
}

/* Content area */
.content {
    font-size: 13px;
    line-height: 1.6;
    color: #000;
}

.content p {
    margin: 0 0 1em 0;
}

.content p:first-child {
    margin-top: 0;
}

.content p:last-child {
    margin-bottom: 0;
}

.content img {
    max-width: 100%;
    height: auto;
    margin: 0.5em 0;
}

.content img.face {
    float: right;
    margin-top: -3em;
}

.content a {
    color: #148cb5;
    text-decoration: none;
}

.content a:visited {
    color: #636;
}

.content a:hover {
    text-decoration: underline !important;
    color: #148cb5 !important;
}

.content ul, .content ol {
    margin: 0.5em 0 0.5em 2em;
}

.content li {
    margin-bottom: 0.3em;
}

.content code {
    font-family: Monaco, Consolas, "Courier New", monospace;
    font-size: 12px;
    background: #f5f5f5;
    padding: 2px 4px;
}

.content pre {
    font-family: Monaco, Consolas, "Courier New", monospace;
    font-size: 11px;
    background: #f5f5f5;
    border: 1px solid #ddd;
    padding: 10px;
    overflow-x: auto;
    margin: 1em 0;
}

.content pre code {
    background: transparent;
    padding: 0;
}

.content blockquote {
    margin: 1em 0 1em 1em;
    padding-left: 1em;
    border-left: 3px solid #ccc;
    color: #666;
    font-style: italic;
}

.content table {
    border-collapse: collapse;
    margin: 1em 0;
}

.content th, .content td {
    border: 1px solid #ddd;
    padding: 5px 8px;
}

.content th {
    background: #f5f5f5;
}

video {
    max-width: 80%;
    border: 1px solid lightgray;
    border-radius: 10px;
}

/* Horizontal rules */
hr {
    height: 1px;
    border: none;
    color: #ccc;
    background-color: #ccc;
    margin: 2em auto;
    width: 50%;
}

/* Footer - Dark background, centered text */
footer,
#footer {
    margin: 2em 0;
    padding: 1em 0;
    text-align: center;
    clear: both;
    margin-top: 1em;
    margin-right: 0;
    font-size: 11px;
    color: #999999;
    background-color: #2a2a2a;
    border-radius: 0;
    border-top: none;
}

footer ul,
#footer ul {
    margin: 0;
    padding: 0;
    list-style: none;
}

footer li,
#footer li {
    display: inline;
    padding: 0 20px 0 0;
    margin: 0;
    white-space: nowrap;
}

footer p,
#footer p {
    color: #999;
    margin: 0.6em 0;
}

footer a,
#footer a {
    color: #999;
}

footer a:hover,
#footer a:hover {
    color: #ccc;
    text-decoration: underline !important;
}

footer span, footer a,
#footer span, #footer a {
    white-space: nowrap;
    padding: 0 1em;
}

footer p span, footer p a,
#footer p span, #footer p a {
    white-space: nowrap;
    padding: 0 0.3em;
}

footer span a,
#footer span a {
    padding: 0;
}

footer kbd {
    font-family: Monaco, Consolas, "Courier New", monospace;
    font-size: 11px;
    background: #444;
    color: #ccc;
    border: 1px solid #666;
    padding: 2px 4px;
    border-radius: 2px;
}

/* Keyboard shortcuts panel */
.shortcuts-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 999;
}

.shortcuts-backdrop.hidden {
    display: none;
}

.shortcuts-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #fff;
    border: 1px solid #333;
    padding: 20px;
    z-index: 1000;
    min-width: 280px;
    -moz-border-radius: 12px;
    -webkit-border-radius: 12px;
    border-radius: 12px;
    box-shadow: 0 5px 20px rgba(0, 0, 0, 0.3);
}

.shortcuts-panel.hidden {
    display: none;
}

.shortcuts-panel h3 {
    font-size: 16px;
    font-weight: bold;
    margin-bottom: 15px;
    padding-bottom: 10px;
    border-bottom: 1px solid #ddd;
}

.shortcuts-panel dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 15px;
}

.shortcuts-panel dt {
    text-align: right;
}

.shortcuts-panel kbd {
    font-family: Monaco, Consolas, "Courier New", monospace;
    font-size: 12px;
    background: #f5f5f5;
    border: 1px solid #ccc;
    padding: 3px 6px;
    border-radius: 2px;
}

.shortcuts-panel .close-btn {
    margin-top: 15px;
    background: #455372;
    color: #fff;
    border: none;
    padding: 8px 15px;
    cursor: pointer;
    -moz-border-radius: 6px;
    -webkit-border-radius: 6px;
    border-radius: 6px;
}

.shortcuts-panel .close-btn:hover {
    background: #374461;
}

/* Remove decorative elements from Mozilla header */
.theme-mozilla header::after,
.theme-mozilla header::before {
    display: none;
}

/* Responsive */
@media (max-width: 768px) {
    body {
        margin: 10px;
    }

    .container {
        flex-direction: column;
    }

    .sidebar {
        width: 100%;
        order: 1;
        margin-top: 2em;
        padding-top: 1em;
        border-top: 1px solid #ccc;
    }

    .sidebar > div,
    .sidebar .sidebar-section,
    .search-form {
        margin-left: 0;
    }

    .mozilla-nav-inner {
        justify-content: center;
    }

    header {
        text-align: center;
    }
}

@media (max-width: 480px) {
    .mozilla-nav-label {
        display: none;
    }

    header h1 {
        font-size: 18px;
    }
}

/* Titles-only page styles */
.titles-only .view-toggle {
    margin-bottom: 1em;
    font-size: 12px;
}

.titles-only .day {
    margin-bottom: 1.5em;
}

.titles-only h3.post {
    font-size: 120%;
    font-weight: bold;
    margin-top: 0.5em;
    margin-bottom: 3px;
}

.titles-only h4.entry-title {
    font-size: 13px;
    font-weight: normal;
    margin: 3px 0;
}

.titles-only h4.entry-title a {
    color: #148cb5;
}

.titles-only p.entry-meta {
    font-size: 11px;
    color: #666;
    margin: 0 0 0.5em 0;
}

/* Print styles */
@media print {
    .sidebar, .search-form, footer, .mozilla-nav {
        display: none;
    }

    .container {
        display: block;
    }

    header {
        background: white;
        color: black;
        border-bottom: 2px solid black;
        border-radius: 0;
    }

    header h1, header h1 a {
        color: black;
    }

    article {
        page-break-inside: avoid;
    }

    a {
        color: black;
    }
}
""",
}

THEME_LOGOS = {
    "planet-python": {
        "url": "/static/logo.gif",
        "width": "211",
        "height": "71",
        "alt": "Planet Python",
        "svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 211 71" width="211" height="71">
  <!-- Official Python Logo - Two intertwined snakes forming a plus shape -->
  <!-- Colors: Blue #366D9C and Yellow #FFDB4C -->
  <defs>
    <linearGradient id="blueGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#5A9FD4"/>
      <stop offset="100%" style="stop-color:#366D9C"/>
    </linearGradient>
    <linearGradient id="yellowGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#FFDB4C"/>
      <stop offset="100%" style="stop-color:#FFD43B"/>
    </linearGradient>
  </defs>

  <!-- Blue snake (top-left, curves down-right) -->
  <path fill="url(#blueGradient)" d="
    M35.5 5.5
    C35.5 2.5 33 0 30 0
    L15.5 0
    C7 0 0 7 0 15.5
    L0 30
    C0 33 2.5 35.5 5.5 35.5
    L25 35.5
    C28 35.5 30.5 38 30.5 41
    L30.5 50
    L20 50
    L20 35.5
    L5.5 35.5
    C2.5 35.5 0 33 0 30
    L0 15.5
    C0 7 7 0 15.5 0
    L30 0
    C33 0 35.5 2.5 35.5 5.5
    L35.5 20
    L30.5 20
    L30.5 5.5
    C30.5 4 29 2.5 27.5 2.5
    L15.5 2.5
    C8.5 2.5 2.5 8.5 2.5 15.5
    L2.5 27.5
    C2.5 29 4 30.5 5.5 30.5
    L25 30.5
    C30.5 30.5 35.5 35.5 35.5 41
    L35.5 55
    L30.5 55
    L30.5 41
    C30.5 38 28 35.5 25 35.5
    L20 35.5
    L20 50
    L30.5 50
    L30.5 41
    L35.5 41
    Z
  " transform="translate(5, 5)"/>

  <!-- Simplified Python logo mark -->
  <g transform="translate(5, 5)">
    <!-- Blue half (top) -->
    <path fill="url(#blueGradient)" d="
      M30.2 0
      C18.8 0 17.5 5 17.5 5
      L17.5 13
      L30.5 13
      L30.5 15
      L11 15
      C11 15 0 13.8 0 30.5
      C0 47.2 9.6 46.5 9.6 46.5
      L15.5 46.5
      L15.5 38.2
      C15.5 38.2 15.1 28.5 25 28.5
      L37.8 28.5
      C37.8 28.5 47 28.7 47 19.8
      L47 6.8
      C47 6.8 48.4 0 30.2 0
      M22.1 6.5
      C23.8 6.5 25.2 7.9 25.2 9.6
      C25.2 11.3 23.8 12.7 22.1 12.7
      C20.4 12.7 19 11.3 19 9.6
      C19 7.9 20.4 6.5 22.1 6.5
    "/>

    <!-- Yellow half (bottom) -->
    <path fill="url(#yellowGradient)" d="
      M47.8 15
      C47.8 15 47 15 47 15
      L47 23.3
      C47 23.3 47.4 33 37.5 33
      L24.7 33
      C24.7 33 15.5 32.8 15.5 41.7
      L15.5 54.7
      C15.5 54.7 14.1 61.5 32.3 61.5
      C43.7 61.5 45 56.5 45 56.5
      L45 48.5
      L32 48.5
      L32 46.5
      L51.5 46.5
      C51.5 46.5 62.5 47.7 62.5 31
      C62.5 14.3 52.9 15 52.9 15
      L47.8 15
      M40.4 55
      C38.7 55 37.3 53.6 37.3 51.9
      C37.3 50.2 38.7 48.8 40.4 48.8
      C42.1 48.8 43.5 50.2 43.5 51.9
      C43.5 53.6 42.1 55 40.4 55
    " transform="translate(0, 0)"/>
  </g>

  <!-- "Python" text -->
  <text x="80" y="42" font-family="'Source Sans Pro', Arial, sans-serif" font-size="28" font-weight="600" fill="#646464">
    <tspan fill="#366D9C">Py</tspan><tspan fill="#FFDB4C">thon</tspan>
  </text>
</svg>
""",
    },
    "planet-mozilla": {
        "url": "/static/logo.png",
        "width": "222",
        "height": "44",
        "alt": "Planet Mozilla",
        "svg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 112 32" width="112" height="32">
  <!-- Mozilla wordmark logo - White on transparent -->
  <title>Mozilla</title>
  <g fill="#ffffff">
    <!-- M -->
    <path d="M2.5 6.5h5.3l4.2 13.8L16.2 6.5h5.3v19h-3.4V10.9l-4.5 14.6h-3.2L5.9 10.9v14.6H2.5V6.5z"/>
    <!-- o -->
    <path d="M25.9 14.8c0-4.6 3.2-7.3 7.2-7.3s7.2 2.7 7.2 7.3v3.9c0 4.6-3.2 7.3-7.2 7.3s-7.2-2.7-7.2-7.3v-3.9zm3.4 4c0 2.5 1.5 4.1 3.8 4.1s3.8-1.6 3.8-4.1v-4.1c0-2.5-1.5-4.1-3.8-4.1s-3.8 1.6-3.8 4.1v4.1z"/>
    <!-- z -->
    <path d="M43.5 7.5h12.4v2.7l-8.3 13.5h8.5v2.8H43.2v-2.7l8.3-13.5h-8V7.5z"/>
    <!-- i -->
    <path d="M58.8 2.5h3.4v4h-3.4v-4zm0 5h3.4v18h-3.4v-18z"/>
    <!-- l -->
    <path d="M66.2 2.5h3.4v23h-3.4v-23z"/>
    <!-- l -->
    <path d="M73.6 2.5h3.4v23h-3.4v-23z"/>
    <!-- a -->
    <path d="M81 14.5c0-4.5 2.9-7 6.8-7 3.9 0 6.5 2.3 6.5 6.3v11.7h-3.1v-2.2c-.9 1.6-2.5 2.5-4.6 2.5-2.8 0-5-1.7-5-4.7 0-3.1 2.4-4.8 6.1-4.8h3.2v-1c0-2-1.1-3.4-3.4-3.4-2.1 0-3.3 1.2-3.4 3.1H81.1l-.1-1.5zm9.9 3.6h-2.7c-2.1 0-3.3.8-3.3 2.4 0 1.5 1.1 2.4 2.9 2.4 2.4 0 4.1-1.5 4.1-3.9v-.9z"/>
  </g>
  <!-- The "://" decoration commonly seen with Mozilla branding -->
  <g fill="#b72822">
    <text x="95" y="24" font-family="Georgia, serif" font-size="16" font-weight="bold">://</text>
  </g>
</svg>
""",
    },
}

# Embedded theme assets as base64 data URIs for visual fidelity
THEME_ASSETS = {
    "planet-python": {
        "logo": "data:image/gif;base64,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",
    },
    "planet-mozilla": {
        "logo": "data:image/png;base64,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",
        "header_bg": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAgAAZABkAAD/7AARRHVja3kAAQAEAAAAWgAA/+4AJkFkb2JlAGTAAAAAAQMAFQQDBgoNAAABzwAAAfsAAAI7AAACaf/bAIQAAQEBAQEBAQEBAQIBAQECAgIBAQICAgICAgICAgMCAwMDAwIDAwQEBAQEAwUFBQUFBQcHBwcHCAgICAgICAgICAEBAQECAgIFAwMFBwUEBQcICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI/8IAEQgAZQACAwERAAIRAQMRAf/EAJwAAQEAAwAAAAAAAAAAAAAAAAADBgcJAQEAAwEAAAAAAAAAAAAAAAAAAQYHCBAAAQMFAQAAAAAAAAAAAAAAEDAEFQACEiIDFhEAAQIHAAAAAAAAAAAAAAAAAZEyABAwMdHhAhIAAgIDAAAAAAAAAAAAAAAAEDBBodECMhMAAAUCBwEAAAAAAAAAAAAAABAwEfHwIQFRYZGhwdHh/9oADAMBAAIRAxEAAAHm+TAAAANhZ71nlFW26kx//9oACAEBAAEFAs7koluNa//aAAgBAgABBQJKW6H/2gAIAQMAAQUCS8G0P//aAAgBAgIGPwJUH//aAAgBAwIGPwJXW1YP/9oACAEBAQY/AnGk/tRiVym4/9oACAEBAwE/IZbFRG3zA//aAAgBAgMBPyFLS5elYf/aAAgBAwMBPyFKZIuP/9oADAMBAAIRAxEAABCgAAACnf/aAAgBAQMBPxCku1fzT//aAAgBAgMBPxBKCIakj//aAAgBAwMBPxB1Mb5K2H//2Q==",
        "header_dino": "data:image/jpeg;base64,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",
        "feed_icon": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAMAAABhq6zVAAAABGdBTUEAAK/INwWK6QAAABl0RVh0U29mdHdhcmUAQWRvYmUgSW1hZ2VSZWFkeXHJZTwAAAD/UExURdlyKd5yMOF4MeiGNemHNdteKt1jK99qMOBpLOFuNONvLuNyNeOAU+VzLuV2NuZ6M+d2MOh5MOh7N+l+N+t+MuuAMeuAOeuDOeyHPu2aY+6FM+6GOu6HOu6mfe+GNPCLO/CNQPCdZfGKNPGMPPGPOfGVTfGxivKPPPOONvOPNvOkZvO2i/SSPfSTPfScT/S8mPWVO/WWPvaUN/abRParaPeXOPeZP/eydfiYOPi5gfjEmvjFmvmrXfmxavnHmvqbOfq3dvq4dvq9g/rl2PudOvujRvuuXvuvX/u6d/u/g/zAg/3q2f3v5f3w5v3x5v7nzv7y5v7z5v748v/58////wfSbk0AAAAFdFJOUzDv7+/vprtoDgAAAI9JREFUCB0FwVELgjAQAODd3XYztdQeQvo1Qv//rfeIgggkGurSeW59HyhstKGMdboKYsEQCY2tOoIKL2pxk7HG/agGL7beI7phoQbbMMTCuq9fNfFZyTyWx6dHzOxtgnJ5ciGCvMthlMNrboOg5lO+vZkeTdzQWIl9r8xHaQHducF7CTEmoXjPtjUlpSCkP9saQ08zzj08AAAAAElFTkSuQmCC",
        "bullet": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAQAAAAEBAMAAABb34NNAAAAJFBMVEW92OJ0iJG91+KFl56ClZ5qfIR0h49peoK81+G+2OJebnYJERfu9vKuAAAAFElEQVQIHWOYtYiheitD9kaGZgcAG+oETJeFk0UAAAAASUVORK5CYII=",
        "world": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAYAAABWdVznAAAABGdBTUEAAK/INwWK6QAAAaRpQ0NQSUNDIFByb2ZpbGUAAHgBrZI7SMNAGMf/iYgi1cUnihBEqkOUoosFEWoGKxWsRfCxpUmshZqG5Kw6OjgKBSfFwQc4iTiJYyenbgVBEEF0cRAEwUUkfpdDKii4eHCX3/3ve+S77wC5pDtOTgawYjM3NTGuzC8sKnU3qEcXiTR0w3NiyeSU2P22vl1D4nplgMfy4+rD5nTPFcs+7W4+b1d+8/imhVxKCEgtpLVkBPdzTgse5bzGHEY2Sc7Gsm4S04TqzqY04iJxU0bwAee04HPOBSPDfUvEEdvM2sQvxCOm5RmAzHMxw3HJRt4n7uX105cGSwBj3UBNuaotesDpCdAermr9HUDrHHA5XNVeZ4I7kdrK3tLwUBBOCo0DtXe+/xoG6naAj6Lvvx/5/scx5bgFSrax6hYCW/pJOQr8tRe1ieiiB8S8F0E/frKoP7CPAIdxYK4BSGwBe/dA3xnQfAEkG4HZKOSRx68p7irw69T0XDbt6swyFf5ctHwu73qObljB8f8tzFqnngBa3tlws5llpsTodVmqMmkbg6oyFIlE8Qk3BXczyiXR/gAAAAlwSFlzAAALEwAACxMBAJqcGAAAAhFJREFUGBkFwc1Lk3EAwPHv83uezc1n785Zak7TNUOMsDAi6mgE1a0QD0FCQtG9f6JbRJ2LLt26VEZQhygj0yinrlnTtZq6Fzefue152fP0+UgAAGef93vHYuenY52R29jyWNtBEdjpSrP4OF1aefL+eqoOIAFce30xkgiPPEiGRqbHIyfEvu5Da8gY7Rob2iKFWubFamF17s2Nj7vy1PyUOh4cfnRp5MLMyeikZNt+tlsu6raPQs1PwIkTj3hGa9p2snZOfyn6lPD1RDA+0+HpYdnYJW+0qLTc/C5Z/KpUyctZOkI2A/7+q3Hp0E2lT43eTYSH2GiVCcmDaHU3q/8sNLuC0feZeucOB1WZM9FBvinrc8Itu0YtIVja+05Fr7NZMSlpNaK9GkVXnZymsZX/gyK5cSxpSMFBsqwmTitI/sAhtSmwTA+7WZVu+RRqzcDWP9CO6pimKYlGq/WzbZh0E6By0MQwHBxPkHwhRHZJpVnsJCqHaeh1DF3Pyf1XevHK3ss+YbKt5ZCsI5iWiiwUXB1ZVP8iCb/FRjHHcnb9vmxOkPYK9+hwuOd4LBCj3e5GsmTctk2X+oVjwTKSAp/SP+YX1r7ek8tvy4Y1Kd7tVWtJYTnJofBhAgJ6/ToDXVUyhQwLa6n55Ux2tvFsvyQBAHAH3+noxK0uX2jWMqWjQoCQrK2/pZ2nK6n1h7xiH+A/1vfxSHYY5ggAAAAASUVORK5CYII=",
    },
}
