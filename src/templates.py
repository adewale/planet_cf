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
        "index.html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
    <meta http-equiv="content-type" content="text/html; charset=utf-8" />
    <title>{{ planet.name }}</title>
    <link rel="stylesheet" type="text/css" href="/static/style.css" />
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="{{ feed_links.atom or '/feed.atom' }}" />
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="{{ feed_links.rss or '/feed.rss' }}" />
    <link rel="icon" href="/static/favicon.ico" sizes="32x32" />
</head>
<body>
    <!-- Logo -->
    <h1 id="logoheader">
        <a href="/" id="logolink" accesskey="1">
            {% if logo %}
            <img id="logo" src="{{ logo.url }}" alt="{{ logo.alt }}" />
            {% else %}
            {{ planet.name }}
            {% endif %}
        </a>
    </h1>

    <div id="content-body">
        <div id="body-main">
            <h1 class="pageheading">{{ planet.name }}</h1>
            <p>Last update: {{ generated_at }}</p>

            {% for date, day_entries in entries_by_date.items() %}
            <h2>{{ date }}</h2>
            {% set current_author = namespace(value='') %}
            {% for entry in day_entries %}
                {% if entry.display_author != current_author.value %}
                    {% set current_author.value = entry.display_author %}
            <hr /><h3 class="post"><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}" title="{{ entry.display_author }}">{{ entry.display_author or 'Unknown' }}</a></h3>
                {% endif %}
            <h4><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
            <div class="content">{{ entry.content | safe }}</div>
            {% endfor %}
            {% else %}
            <p>No entries yet.</p>
            {% endfor %}
        </div>

        <div id="left-hand-navigation">
            <div id="menu">
                <ul class="level-one">
                    <li>
                        <ul class="level-two">
                            <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS feed</a></li>
                            {% if feed_links.titles_only %}<li><a href="{{ feed_links.titles_only }}">Titles Only</a></li>{% endif %}
                        </ul>
                    </li>
                </ul>

                {% if related_sites %}
                {% for section in related_sites %}
                <h4>{{ section.title }}</h4>
                <ul class="level-two">
                    {% for link in section.links %}
                    <li><a href="{{ link.url }}">{{ link.name }}</a></li>
                    {% endfor %}
                </ul>
                {% endfor %}
                {% endif %}

                <h4><a href="{{ feed_links.opml or '/feeds.opml' }}">Subscriptions</a></h4>
                <ul class="level-two">
                    {% for feed in feeds %}
                    <li><a href="{{ feed.site_url or feed.url or '#' }}" title="{{ feed.title }}">{{ feed.title or 'Untitled' }}</a></li>
                    {% else %}
                    <li>No feeds configured</li>
                    {% endfor %}
                </ul>

                {% if submission %}
                <p style="margin-left: 1.5em;"><a href="{{ submission.url }}">{{ submission.text }}</a></p>
                {% endif %}
            </div>
        </div>
    </div>

    <div id="footer">
        <p>
            <a href="{{ feed_links.atom or '/feed.atom' }}">Atom</a> |
            <a href="{{ feed_links.rss or '/feed.rss' }}">RSS</a> |
            <a href="{{ feed_links.opml or '/feeds.opml' }}">OPML</a>
        </p>
        <p>{{ footer_text }}{% if show_admin_link %} | <a href="/admin">Admin</a>{% endif %}</p>
    </div>

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
        "titles.html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
    <meta http-equiv="content-type" content="text/html; charset=utf-8" />
    <title>{{ planet.name }} - Titles Only</title>
    <link rel="stylesheet" type="text/css" href="/static/style.css" />
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="{{ feed_links.atom or '/feed.atom' }}" />
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="{{ feed_links.rss or '/feed.rss' }}" />
    <link rel="icon" href="/static/favicon.ico" sizes="32x32" />
</head>
<body>
    <!-- Logo -->
    <h1 id="logoheader">
        <a href="/" id="logolink" accesskey="1">
            {% if logo %}
            <img id="logo" src="{{ logo.url }}" alt="{{ logo.alt }}" />
            {% else %}
            {{ planet.name }}
            {% endif %}
        </a>
    </h1>

    <div id="content-body">
        <div id="body-main">
            <h1 class="pageheading">{{ planet.name }} - Titles Only</h1>
            <p><a href="/">View full content</a></p>

            {% for date, day_entries in entries_by_date.items() %}
            <h2>{{ date }}</h2>
            {% set current_author = namespace(value='') %}
            {% for entry in day_entries %}
                {% if entry.display_author != current_author.value %}
                    {% set current_author.value = entry.display_author %}
            <h3 class="post"><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}">{{ entry.display_author or 'Unknown' }}</a></h3>
                {% endif %}
            <h4><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
            <p><em>{% if entry.display_author %}by {{ entry.display_author }} at {% endif %}{{ entry.published_at_display }}</em></p>
            {% endfor %}
            {% else %}
            <p>No entries yet.</p>
            {% endfor %}
        </div>

        <div id="left-hand-navigation">
            <div id="menu">
                <ul class="level-one">
                    <li>
                        <ul class="level-two">
                            <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS feed</a></li>
                            <li><a href="/">Full content</a></li>
                        </ul>
                    </li>
                </ul>

                <h4><a href="{{ feed_links.opml or '/feeds.opml' }}">Subscriptions</a></h4>
                <ul class="level-two">
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
        <p>
            <a href="{{ feed_links.atom or '/feed.atom' }}">Atom</a> |
            <a href="{{ feed_links.rss or '/feed.rss' }}">RSS</a> |
            <a href="{{ feed_links.opml or '/feeds.opml' }}">OPML</a>
        </p>
        <p>{{ footer_text }}{% if show_admin_link %} | <a href="/admin">Admin</a>{% endif %}</p>
        <p>Last updated: {{ generated_at }}</p>
    </div>
</body>
</html>
""",
        "search.html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
    <meta http-equiv="content-type" content="text/html; charset=utf-8" />
    <title>Search Results - {{ planet.name }}</title>
    <link rel="stylesheet" type="text/css" href="/static/style.css" />
    <link rel="icon" href="/static/favicon.ico" sizes="32x32" />
</head>
<body>
    <!-- Logo -->
    <h1 id="logoheader">
        <a href="/" id="logolink" accesskey="1">
            {% if logo %}
            <img id="logo" src="{{ logo.url }}" alt="{{ logo.alt }}" />
            {% else %}
            {{ planet.name }}
            {% endif %}
        </a>
    </h1>

    <div id="content-body">
        <div id="body-main">
            <h1 class="pageheading">Search Results</h1>
            {% if error %}
            <div class="search-error">
                <p>{{ error }}</p>
            </div>
            {% else %}
            <h2>Results for "{{ query }}"</h2>
            {% if words_truncated %}
            <p><em>Note: Your search was limited to the first {{ max_search_words }} words.</em></p>
            {% endif %}
            {% if results %}
            <ul>
                {% for entry in results %}
                <li>
                    <h4><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
                    <p><em>by {{ entry.display_author }}</em></p>
                </li>
                {% endfor %}
            </ul>
            {% else %}
            <p>No results found for "{{ query }}"</p>
            {% endif %}
            {% endif %}
        </div>

        <div id="left-hand-navigation">
            <div id="menu">
                <form action="/search" method="get">
                    <p style="margin-left: 1.5em;">
                        <input type="text" name="q" value="{{ query }}" style="width: 10em;" />
                        <input type="submit" value="Search" />
                    </p>
                </form>
                <p style="margin-left: 1.5em;"><a href="/">Back to home</a></p>
            </div>
        </div>
    </div>

    <div id="footer">
        <p><a href="/">Back to {{ planet.name }}</a></p>
    </div>
</body>
</html>
""",
    },
    "planet-mozilla": {
        "index.html": """<?xml version="1.0"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{{ planet.name }}</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <meta name="description" content="{{ planet.description }}"/>
    <link href="/static/style.css" rel="stylesheet" type="text/css"/>
    <link href="/static/favicon.ico" rel="shortcut icon" type="image/x-icon"/>
    <link rel="alternate" href="{{ feed_links.atom or '/feed.atom' }}" title="{{ planet.name }}" type="application/atom+xml"/>
</head>
<body>
    <div id="utility">
        <p><strong>Looking For</strong></p>
        <ul>
            <li><a href="https://www.mozilla.org/">mozilla.org</a></li>
            <li><a href="https://wiki.mozilla.org/">Wiki</a></li>
            <li><a href="https://developer.mozilla.org/">Developer Center</a></li>
            <li><a href="https://www.mozilla.org/firefox/">Firefox</a></li>
            <li><a href="https://www.thunderbird.net/">Thunderbird</a></li>
        </ul>
    </div>

    <div id="header">
        <div id="dino">
            <h1><a href="/" title="Back to home page">{{ planet.name }}</a></h1>
        </div>
    </div>

    <div class="main-container">
        <div class="main-content">
            {% for date, day_entries in entries_by_date.items() %}
            <h2><time datetime="{{ date }}">{{ date }}</time></h2>
            {% for entry in day_entries %}
            <article class="news {{ entry.display_author | lower | replace(' ', '-') }}">
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
        </div>

        <div class="sidebar-content">
            <div class="disclaimer">
                <h2>{{ planet.name }}</h2>
                <p>Collected here are the most recent blog posts from the community.
                   The content here is unfiltered and uncensored, and represents the views of individual community members.</p>
            </div>

            <div class="feeds">
                <h2>Subscribe to Planet</h2>
                <p>Feeds:</p>
                <ul>
                    <li><a href="{{ feed_links.atom or '/feed.atom' }}">Atom</a></li>
                    <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS 2.0</a></li>
                </ul>
                <p>Subscription list:</p>
                <ul>
                    <li class="opml"><a href="{{ feed_links.opml or '/feeds.opml' }}">OPML</a></li>
                </ul>
                <p>Last update: <time datetime="{{ generated_at }}" title="GMT">{{ generated_at }}</time></p>
            </div>

            <div class="main">
                {% if related_sites %}
                {% for section in related_sites %}
                <h2>{{ section.title }}</h2>
                <ul class="planets">
                    {% for link in section.links %}
                    <li><a href="{{ link.url }}">{{ link.name }}</a></li>
                    {% endfor %}
                </ul>
                {% endfor %}
                {% endif %}

                {% if not is_lite_mode %}
                <div id="sidebar">
                    <h2>Search</h2>
                    <form action="/search" method="GET" class="search-form">
                        <input name="q" type="search" placeholder="Search..."/>
                        <button type="submit">Search</button>
                    </form>
                </div>
                {% endif %}

                <h2>Subscriptions</h2>
                <ul class="subscriptions">
                    {% for feed in feeds %}
                    <li><a href="{{ feed.site_url or feed.url or '#' }}" title="{{ feed.title }}">{{ feed.title or 'Untitled' }}</a></li>
                    {% else %}
                    <li>No feeds configured</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>

    <div id="footer">
        <div id="footer-content">
            <p>
                {{ footer_text }}
                {% if show_admin_link %} | <a href="/admin">Admin</a>{% endif %}
            </p>
        </div>
    </div>

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
        "titles.html": """<?xml version="1.0"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{{ planet.name }} - Titles Only</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <link href="/static/style.css" rel="stylesheet" type="text/css"/>
    <link href="/static/favicon.ico" rel="shortcut icon" type="image/x-icon"/>
    <link rel="alternate" href="{{ feed_links.atom or '/feed.atom' }}" title="{{ planet.name }}" type="application/atom+xml"/>
</head>
<body>
    <div id="utility">
        <p><strong>Looking For</strong></p>
        <ul>
            <li><a href="https://www.mozilla.org/">mozilla.org</a></li>
            <li><a href="https://wiki.mozilla.org/">Wiki</a></li>
            <li><a href="https://developer.mozilla.org/">Developer Center</a></li>
            <li><a href="https://www.mozilla.org/firefox/">Firefox</a></li>
            <li><a href="https://www.thunderbird.net/">Thunderbird</a></li>
        </ul>
    </div>

    <div id="header">
        <div id="dino">
            <h1><a href="/" title="Back to home page">{{ planet.name }}</a></h1>
        </div>
    </div>

    <div class="main-container">
        <div class="main-content">
            <p><a href="/">View full content</a></p>

            {% for date, day_entries in entries_by_date.items() %}
            <h2><time datetime="{{ date }}">{{ date }}</time></h2>
            {% set current_author = namespace(value='') %}
            {% for entry in day_entries %}
                {% if entry.display_author != current_author.value %}
                    {% set current_author.value = entry.display_author %}
            <h3><a href="{{ entry.feed_site_url or entry.feed_url or '#' }}">{{ entry.display_author or 'Unknown' }}</a></h3>
                {% endif %}
            <h4><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
            <p><em>{% if entry.display_author %}by {{ entry.display_author }} at {% endif %}{{ entry.published_at_display }}</em></p>
            {% endfor %}
            {% else %}
            <p>No entries yet.</p>
            {% endfor %}
        </div>

        <div class="sidebar-content">
            <div class="feeds">
                <h2>Subscribe to Planet</h2>
                <ul>
                    <li><a href="{{ feed_links.atom or '/feed.atom' }}">Atom</a></li>
                    <li><a href="{{ feed_links.rss or '/feed.rss' }}">RSS 2.0</a></li>
                    <li class="opml"><a href="{{ feed_links.opml or '/feeds.opml' }}">OPML</a></li>
                </ul>
            </div>

            <div class="main">
                <h2>Subscriptions</h2>
                <ul class="planets">
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
</body>
</html>
""",
        "search.html": """<?xml version="1.0"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Search Results - {{ planet.name }}</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <link href="/static/style.css" rel="stylesheet" type="text/css"/>
    <link href="/static/favicon.ico" rel="shortcut icon" type="image/x-icon"/>
</head>
<body>
    <div id="utility">
        <p><strong>Looking For</strong></p>
        <ul>
            <li><a href="https://www.mozilla.org/">mozilla.org</a></li>
            <li><a href="https://wiki.mozilla.org/">Wiki</a></li>
            <li><a href="https://developer.mozilla.org/">Developer Center</a></li>
            <li><a href="https://www.mozilla.org/firefox/">Firefox</a></li>
            <li><a href="https://www.thunderbird.net/">Thunderbird</a></li>
        </ul>
    </div>

    <div id="header">
        <div id="dino">
            <h1><a href="/" title="Back to home page">{{ planet.name }}</a></h1>
        </div>
    </div>

    <div class="main-container">
        <div class="main-content">
            <h2>Search Results</h2>
            {% if error %}
            <div class="search-error" style="background: #fee; padding: 1em; border-radius: 0.5em; margin: 1em 0;">
                <p>{{ error }}</p>
            </div>
            {% else %}
            <h3>Results for "{{ query }}"</h3>
            {% if words_truncated %}
            <p style="font-size: 11px; color: #666;">Note: Your search was limited to the first {{ max_search_words }} words.</p>
            {% endif %}
            {% if results %}
            <div class="entry">
                {% for entry in results %}
                <article class="news">
                    <h4><a href="{{ entry.url or '#' }}">{{ entry.title or 'Untitled' }}</a></h4>
                    <p style="font-size: 11px; color: #666; margin-left: 15px;">by {{ entry.display_author }}</p>
                </article>
                {% endfor %}
            </div>
            {% else %}
            <p>No results found for "{{ query }}"</p>
            {% endif %}
            {% endif %}
        </div>

        <div class="sidebar-content">
            <div class="main">
                <form action="/search" method="GET" class="search-form">
                    <label><strong>Search</strong></label>
                    <input type="search" name="q" value="{{ query }}" placeholder="Search entries..."/>
                    <button type="submit">Search</button>
                </form>
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
    },
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
TEMPLATE_FEED_ATOM = "feed.atom.xml"
TEMPLATE_FEED_RSS = "feed.rss.xml"
TEMPLATE_FEEDS_OPML = "feeds.opml"

# =============================================================================
# Theme-specific CSS and Logos (for multi-instance deployments)
# =============================================================================

THEME_CSS = {
    "planet-python": """/* Planet Python Theme - Using ORIGINAL selectors from planetpython.org */
/* Source: https://planetpython.org/static/styles/styles.css */

/* Main Styles for HTML Elements */
HTML, BODY {
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

H1, H2, H3, H4, H5 {
  font-family: Georgia, "Bitstream Vera Serif", "New York", Palatino, serif;
  font-weight: normal;
  line-height: 1em;
}

H1 {
  font-size: 160%;
  color: #234764;
  margin: 0.7em 0 0.7em 0;
  text-decoration: none;
}

H1 A {
  color: #234764;
  text-decoration: none;
}

H2 {
  font-size: 140%;
  color: #366D9C;
  margin: 0.7em 0 0.7em 0;
}

H3 {
  font-size: 135%;
  font-style: italic;
  color: #366D9C;
  margin: 0.4em 0 0.0em 0;
}

H4 {
  font-size: 125%;
  color: #366D9C;
  margin: 0.4em 0 0.0em 0;
}

/* Links */
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

/* Logo Header - ORIGINAL selector */
#logoheader {
  border: 0;
  margin: 0;
  padding: 1px;
  z-index: 1;
  background-color: #F7F7F7;
  background-repeat: repeat-x;
  border-bottom: 1px solid #999999;
  height: 84px;
}

#logo {
  width: 211px;
  height: 71px;
  margin-top: 10px;
  margin-left: 3%;
}

/* Main content section - ORIGINAL selectors */
#content-body {
  position: absolute;
  left: 0;
  top: 63px;
  width: 93.9%;
  z-index: 0;
  font-size: 75%;
  margin-left: 3.0%;
  min-width: 660px;
}

#body-main {
  padding: 0 0.55em 40px 0.0em;
  line-height: 1.4em;
  font-family: Arial, Verdana, Geneva, "Bitstream Vera Sans", Helvetica, sans-serif;
  margin-left: 19em;
  font-size: 100%;
}

/* Left Hand Navigation - ORIGINAL selectors */
#left-hand-navigation {
  position: absolute;
  left: 3%;
  z-index: 1;
  top: 110px;
}

#menu {
  padding: 0;
  margin-bottom: 5px;
  width: 16em;
  font-size: 75%;
}

#menu ul {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 0;
}

#menu li {
  display: inline;
}

#menu ul.level-one a {
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
}

#menu ul.level-one a:hover {
  color: black;
  text-decoration: underline;
}

#menu ul.level-two li:first-child a {
  border-top: 0;
}

#menu ul.level-two a {
  background-image: none;
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

#menu ul.level-two a:hover {
  text-decoration: underline;
  color: black;
}

#menu ul.level-two a:visited {
  color: #4C3B5B;
}

#menu h4 {
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

#menu h4 a {
  color: #4C5B6B;
  text-decoration: none;
  font-weight: bold;
}

#menu h4 a:hover {
  color: black;
  text-decoration: underline;
}

/* Page heading */
.pageheading {
  font-size: 145%;
}

/* Post styles */
h3.post a {
  color: #00A;
  text-decoration: none;
}

h3.post a:visited {
  color: #551A8B;
}

h3.post a:hover {
  text-decoration: underline;
}

/* Footer */
#footer {
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

#footer a:visited, #footer a:link {
  color: #666;
  display: inline;
}

#footer a:hover {
  color: #333;
  display: inline;
}

#footer p {
  margin: 0.5em 0;
}

/* Horizontal rule */
hr {
  border: none;
  border-top: 1px solid #DADADA;
  margin: 1em 0;
}

/* Content styles */
.content {
  font-size: 100%;
  line-height: 1.4em;
}

.content img {
  max-width: 100%;
  height: auto;
  border: 0;
}

.content pre {
  font-family: "Courier New", Courier, monospace;
  font-size: 115%;
  background: #E0E0FF;
  padding: 10px;
  overflow-x: auto;
  margin: 1em 0;
}

.content code {
  font-family: "Courier New", Courier, monospace;
}

.content blockquote {
  margin-left: 1em;
  padding-left: 1em;
  border-left: 1px solid #CCC;
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

/* Responsive */
@media (max-width: 700px) {
  #content-body {
    position: relative;
    top: 0;
    width: 95%;
    margin-left: 2.5%;
    min-width: auto;
  }

  #left-hand-navigation {
    position: relative;
    left: 0;
    top: 0;
  }

  #body-main {
    margin-left: 0;
  }

  #logo {
    max-width: 150px;
    height: auto;
  }
}

/* Print styles */
@media print {
  #left-hand-navigation, #footer {
    display: none;
  }

  #content-body {
    position: relative;
  }

  #body-main {
    margin-left: 0;
  }
}
""",
    "planet-mozilla": """/* Planet Mozilla Theme - Using ORIGINAL selectors from planet.mozilla.org */
/* Source: https://planet.mozilla.org/planet.css */

* {
  line-height: 1.4;
  padding: 0;
}

ul, ol {
  padding-left: 22px;
}

body {
  margin: 0;
  padding: 0;
  font-family: Helvetica, Arial, Verdana, sans-serif;
  background: #fff url('/static/img/background.jpg') no-repeat scroll -95px top;
  color: #000;
}

a {
  color: #148cb5;
  text-decoration: none;
}

a:hover {
  color: #148cb5;
  text-decoration: underline;
}

a:visited {
  color: #636;
}

/* Header - ORIGINAL selectors */
#header {
  height: 101px;
  background: url('/static/img/header-bg.jpg');
}

#header #dino {
  background: url('/static/img/header-dino.jpg') no-repeat;
  height: 101px;
  width: 300px;
}

#header h1 {
  padding: 0;
  margin: 0;
  background: transparent url('/static/img/logo.png') no-repeat 20px 35px;
  z-index: 1;
  height: 101px;
}

#header h1 a {
  display: block;
  text-indent: -9999px;
  background: transparent url('/static/img/logo.png') no-repeat 20px 35px;
  overflow: hidden;
  width: 265px;
  height: 101px;
}

/* Utility nav - ORIGINAL selectors */
#utility {
  font-family: "Trebuchet MS", sans-serif;
  font-size: 62.5%;
  margin: 0.8em 0 0.7em 30px;
  text-align: right;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 3px 30px 0 0;
}

#utility * {
  display: inline;
}

#utility p {
  margin-right: -20px;
}

#utility strong {
  color: #000;
  font-size: 11px;
}

#utility ul {
  margin-left: 10px;
}

#utility li {
  background: transparent url('/static/img/bullet_utility.png') no-repeat 4px center;
  padding-left: 16px;
  font-size: 11px;
}

#utility li:first-child {
  background: none;
  padding: 0;
}

/* Main container - ORIGINAL selectors */
.main-container {
  display: flex;
  gap: 16px;
  margin: 0 auto;
  max-width: 1200px;
}

.main-content {
  flex-grow: 1;
  max-width: 900px;
}

/* Headings */
h2 {
  font-family: Georgia, Times, "Times New Roman", serif;
  font-weight: normal;
  font-size: 1.75em;
  color: #b72822;
  margin-bottom: 0;
}

h3 {
  margin-top: 10px;
  border-bottom: 1px solid #ccc;
}

h3 a {
  color: black;
}

h4 {
  margin: 0 0 0 15px;
  border-bottom: 1px solid #ccc;
}

h4 a {
  color: black;
}

/* Entry styles */
.entry {
  margin-left: 15px;
}

.news .permalink {
  text-align: right;
}

.news img {
  max-width: 100%;
  height: auto;
}

/* Footer - ORIGINAL selectors */
#footer {
  background-image: url('/static/img/footer.jpg');
  background-position: center;
  background-repeat: no-repeat;
}

#footer-content {
  padding-top: 100px;
}

#footer-content p {
  text-align: center;
  padding: 5px;
  background-color: #2a2a2a;
  color: #999999;
  font-size: 0.9em;
}

#footer-content a {
  color: #999999;
}

#footer-content a:hover {
  color: #ccc;
}

/* Sidebar - ORIGINAL selectors */
.sidebar-content {
  max-width: 300px;
  font-size: 70%;
}

.sidebar-content .feeds,
.sidebar-content .disclaimer {
  padding-left: 15px;
}

.sidebar-content .feeds p {
  padding: 0;
  margin: 5px 0 0 0;
}

.sidebar-content .feeds ul {
  padding-left: 10px;
}

.sidebar-content .feeds li {
  margin: 0;
  padding: 0px;
  display: inline;
}

.sidebar-content .feeds li {
  background-image: url('/static/img/feed-icon.png');
  background-repeat: no-repeat;
  background-position: 0 50%;
  padding: 3px 10px 3px 15px;
  margin: .4em 0;
}

.sidebar-content .feeds li.opml {
  background-image: url('/static/img/opml-icon.png');
  background-repeat: no-repeat;
  background-position: 0 50%;
  padding: 3px 10px 3px 15px;
  margin: .4em 0;
}

.sidebar-content .main {
  padding: 15px 0 0 15px;
}

.sidebar-content .main ul.planets {
  list-style-image: url('/static/img/world.png');
  padding-left: 35px;
}

.sidebar-content .main ul.planets li {
  font-size: 1.3em;
}

.sidebar-content h2 {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 1.2em;
  font-weight: bold;
  color: black;
  margin-top: 1em;
  margin-bottom: 0.5em;
}

/* Search form */
.search-form {
  background: #e4ecec;
  padding: 10px;
  border-radius: 1em;
  margin-bottom: 1em;
}

.search-form label {
  display: block;
  font-weight: bold;
  margin-bottom: 5px;
}

.search-form input[type="search"] {
  width: 100%;
  padding: 5px;
  margin: 5px 0;
  border: 1px solid #ccc;
}

.search-form button {
  padding: 5px 10px;
}

/* Video styles */
video {
  max-width: 80%;
  border: 1px solid lightgray;
  border-radius: 10px;
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
  border-radius: 6px;
}

.shortcuts-panel .close-btn:hover {
  background: #374461;
}

/* Responsive */
@media (max-width: 900px) {
  .main-container {
    flex-direction: column;
    margin: 16px;
  }
  .main-content,
  .sidebar-content {
    min-width: 100%;
    max-width: 100%;
  }
}

/* Print styles */
@media print {
  #utility, .sidebar-content, #footer {
    display: none;
  }
  .main-container {
    display: block;
  }
  #header {
    background: white;
  }
}
""",
}

THEME_LOGOS = {
    "planet-python": {
        "url": "/static/images/python-logo.gif",
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
        "url": "/static/img/logo.png",
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
        "footer_bg": "data:image/jpeg;base64,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",
        "background": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAgAAZABkAAD/2wBDAAEBAQEBAQEBAQECAQEBAgICAQECAgICAgICAgIDAgMDAwMCAwMEBAQEBAMFBQUFBQUHBwcHBwgICAgICAgICAj/2wBDAQEBAQICAgUDAwUHBQQFBwgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAj/wgARCALfBakDAREAAhEBAxEB/8QAHgABAAMAAwEBAQEAAAAAAAAAAAECAwQFBgcKCAn/xAAdAQEAAgMBAQEBAAAAAAAAAAAAAQMCBAUGBwgJ/9oADAMBAAIQAxAAAAH+ffin9KgEwgJmBETEZSlCCZip013P6TY5fVXaGU1kiTn17fdU9HuaOhzcNlMTlWjIREokEzbRydjR2yq1sqpXdtfp8i/UyrvFK7sqti0xrZRyLdXvep5b1PX8bz7tXtN7z2d+pWaOXtc7v+n5TsNrj+h6HlfqHqfjG2Nnsed3fd8r0fHmMYz52r1LpujaJ5cPS4PrWtlmalAXKSmIJlIsCEVlWAkTFYmTSYwNInQF4nKW8TUklKEETGiaBAqVNjIStDM3KkGcspwhOkBQk0mMSSxJaGUzvEUJTKdcc9McuVhdtGWbHXGzkY58mu1GfJic06RPJwswTySCCpUGpkC5kcgqVLkmRJU0LkFgWIJBJAPzBfFP6VCWJLPCYQmMcwiYjIQjz+zyPNbXF42VISGkZwik4AkjmY7HbVbvLxv62zT6/LXxzpvGXZ17fp9XudnbhrlVrlVaY2t1tLaL5VJisZ5U7V86rzjpnVtdq9js8z0PT8x6nt+C6+re7jp+T2zprXs1nDud/wA59T93+cvVdbxPYUbXNq2fp/F9bzKdzn6+5tVuTDKXYw7XF7SqfaVZCCUSZGxQguVlEJTYqiTKMtkVmLnHNSxVNysTqiqZTCJLxMJhFkxOOcTqZzGcxoTEipomqJJmMzNEmBuQaHFOQCkpRU1Mi5aMrRItGWkTJExibxKMtcLO4p2t67eThbpjnonM1LEEGQBczBYsXOOalSSTI2ILliCSwAAPzAfFP6VTMITMAQlEhExE9dZqeO3fPcKzVTEw7anod9R1Ozq3N4tI42VXWW6XU26HWW6XGs1wBaMuXhfoy4GevplX9Cq7XZxbrlVplhrbr3yrrhZWM6YW8va5nJ2NJGZCMvT9nxfcbXJ48Zdz0vL8u7Q7Xc4tZr7zqeUrlX9n+kflHsK7ubTtciu/2Wh2fd8f1fb6+7rE95jPBmPQ4O7xehwy3gJibTHHNkQYzGwiczQoXJSialU7scyJiSxVOsSKzGuOXHmLA2icDYoSSmqM5JxqbRMGpkWKorMUlMKlCqOWnjyvCSxALEAoSm8ToYm0TWVURE6SjHLk4Wc2rZ7vX298bNIyqASChJIMixYsULlSpqCgLFiC4LEEgAH5gfin9KZCCRESkgTVHl9riea2uNEwlzatr2Ol6HssNkBIICE9FdzfHb/m+Zjb2+v0u4r6HJxt66zTpDHKrzPR8z2Vtf0TR9RaM+TbqaZVyy49G3rZRydnn8/ocOTKnb0mrst7jd1vcHmzV2t/L4eGz3d3M7Le4Hp+z4q0PXem+S+19P8AJNcZ5lex22vv+s5/b+j8f1E45+lwn1tU8+HJRocmJxhdNkZTOsQTlMURqZmhBUmMt05IEliDOY2KolOkTSYRMlTM5MTVNURKIaTFYyGc4xMInVFkkUTnMWRJibHHmJSRrE1INAC5UgsknKHIKExNJi8TYiMrpvjlya7uzp2u1p2dYygyBcuZFgVNTim4LFC5gbEggFgSSSASAAfmC+J/0qAhMoEJHFmnxW95zrrdOWKXoNbset1e3aMxhnR0F/L6y3Swyq7Sne9Xrdxjl5vZ4/dVb/Li3qLNLzuzyOru0KxIvOO2xp1Pf63e7eL+bdp0rvk0zqlF7tbXPX5+7yK458vZ53N2ebvZR6XZ4vquj5KlW93Fmlx6N7k7nI9N0vKf0J2/mHZdzwHlN7j8+u/0Gn1Pd8n0voqNu8T3OE+trnvsFZioITYuCsTYmYwNUQQXTBWJtMWiYKmyawTFZiIaJCYgxN4lJjOqaxOc4zK0KmaZnHOYmJ5EohSYtEYyhOpx0amaLSoalIJnWGRoSAZHIjKBE2mETQumwibY2cyu3n07XOqv5+NlAXMAaGJqWOOck45scc5IMwXJABJJJJIAAAPzBfE/6VQSExAkdRdz/GbvnMsqwPWaff8ASU9RGSY4mVHguj5TDKnaZ9dpeh7ujpRjnxcqeru5/W3aXVW6HGyqtGXfa/WtjZ57a4kTjrfra50+61e73uG6TpNfL2ubrOGtuvpdq83c4/Mt06xnnFnZbnE5exobYzzK7Po+95XLPDxfK9n7jr+I9Zuee/qD23515Vunws6vQ6vQ7vT6vZ13drEbRPLh3WLucMuxjGpVOpmblTOJuCZiqJTmaRJBOhmWLxOMxZO0TmhIihoUlCNImyYiYRczLkGUoRaYwOREyTMZIglMElUXMyxJmQakEFiktYUJLpCJkkonaEJjHLk42djTs71bHaVX6JsZgggkguVKGxmVLmhkaFSTQoSQSSWILAAAA/MF8T/pUQIZSiDzW1xvLbXDgTA7nX6XuNX0MY5TnWyx+f73l8Zq492p6HT7nrNTvRhZEx5/Z5HT7PJ42dGKKH0Dner6K7neZ2eMyxmcN9nR5d+n6Wno/QbM9rtSzHjU73It1educXlXaPMlnnVybtHa3W6zW649Hvea9Ps8XkanU8Zxfc8zd5P271/wz6P1fD/cOx88nHPtdfe7nX3efjlU5R6Cueaj0deXMhxZxsE2JELyqmsBJMxeJqQZy2iZRkbJoQSVRvjnTLAZTG0TlKYXLppEyiSkxeJgylCKzGiSBVGZqZzFomxUlNSUSnNFyhoSQEyiqbEmkTRMwtKIaJvjnOFnMwt5tOz2Nd22NkkmJuZAuAYg2IJMzYoWKlypYgguCwJAAAB+YL4n/SoglE0R47d870ezy0EkEx6TW7Nsqu3i7ucN3rGHDmvXGzwm/wCX9joem73X6k5Y9fbp9Nscr1FfT0jPoM9DyezxPpHM9n836HkfR0dbyu3weTbR285V6PneRbqd5ll7qN3ajoci7RzjPj6vSpXs9hucbS3X9D1/HYzhzdjmanZQ5Vdu+n0vMc71XvvQfOfv/sfgn2T0nyHuNTq+q0OzzatnlRlrEZS5UPT4T6GtySiMJi5ZMFDeFUpEULQiZ0iazGuM5yhAk0TQgIuUTvjOeWIlNESnQxhcunMlCYglOCNZQjNES3hiQRMInVFEymSxmWKo2TiWRYqWKJsaQyTrEyQmxvjZOOXJws5VWx2NWxysLKJk2MSpJBuZlihoYGhYxOQZG5mZmxBJBoQCSSCQAAfmB+Jf0sIJymvw+95rrbtEJgSi2dNssPQ63W9o38tfeyq2USR4bd853+v1O5q6HGyp4V2l5ze89lZr+20fTcyva8Lt+d9Pqd3iTT5Dc8/Mx3jYz3/P/QdjV8fZo8bKuuF3oauh6iro31unacUTjhfzL9H0PY8f2vX8flrdL03R8r2dul6a3m/IPD/f/adPyX3D1Pxn7/674V9Gz5/pOf3evZcmJ5+OXFmO9xn1Nbs4YmpBQpOIsSkWIglQFiYlMXic4m0xWYtEySZmhYxNEyixCaoF0omqETMxMTMxnIjGYsiZjNMwsYmxCZRpDCQ0TJUgsWMjQGkKpqWTeExlJWJ2idIz3xz0ws59Wzyq7d8c9U4lDkHEOQQDY45YFzMuUNChIJJBYqXIJBYAAAA/MD8T/pWieLlT4be8xwrNYJiYlOMzCY5MZ/SNP015Z0bcY5JRExOPHmvZn5bd895/b4s5V+o1O921W92GG3SI4lunwNjncjG3h50dds8zLc43ZxZ7zX7Pntnjebu5mEZSd/OfqrMeyr37TXyy2VffdXyHb387fC70/U8d4Dyf1z6B1PK/cfTfH/pd/F/r/o/OeNjf1kz1GTt6NrtKdrusJ5Gxz+fDOYIFAZzjVMo0ILpgFSQiU2CYiYYykCpZNkC0TSWkIkRQuCYnM3TkaBHHmLSxnHSFSSQmqM5ciGadYZykqWRiWTqQSCYm5SUxNgTEsc+XjlMZcjCzn13ThdysbNsLNTMkkgGZuYm5mSZGhUFwZGgLnFOWAVLgkEgAAA/MD8S/pZw89bwm95jKce0r3O0q3zHzW3xMcqpyxk9Prdf1VPXtZTnrbkY2EAcO7V8/s8fpdjl4Z66Y9Rqd701HW81s8XlxZ3le/nnT4/Z4eVur2k5+jyu58XTlXy79C1mt1d/J87ZocCGONmdlXqc3ssNrnU7/AKPd4PY7XH7jb4mdGz5Xg/RP6D9X8Y/q3oeB/onPh+43POa4XdFnh5m6r2un0PUU29jhbhlX0+zo9ZfqxMInuKNvk07POq2Ovt1/Ob/ItE5o2TBQqXBZNiDI0KIsREjUzNUwjjZYWlVFysT2VWxlMWiaGxmXMZXKoicdInMEmUpRMxUtE6xNCEiiLFyhYlNSSxJBeFE7RlfCzm42UieZhZONm2OW0Z2JKEAoXLlCSxkaGZoSYmhmXJKlipoSQSSCQCQAAD8wHxL+lnntjk9jXt8+vbk8ztcXzG3wmWFs6iYh7rR9L3GG4mKUbURKWM18ezW6TY5vJsqsmkThlVhZrew1e9GVfgt7zOkT7bW7/Lyjkb3IjC2csZzqtOF7tXlb/D0yr2xngV5eZy1fLV5cfU6O2dHoMNr6x0OR9P7/AM59l2fB/C/nX6X+xdbxH9G9TwH9W9j5l/QTlMc+LnXTLDKceyq2OVjmJIIJKGhJgQcgqQXMzQzJLAoaFSpYkoC5U0OKcgscc0LAqXBJiXBJJBQuCpQ2IILFASCCCwLHFOSDIuSSZmpBJkWJJBJiagoUNyoBBcoQXIOMcsoSVLEEGhUsWIJIJJAJAAPzBfEf6WQlLKcPHbvm+nv5jKL2URGWudOeNv0LR9PzqtyE0p2JMLKOku5no6+kIZTOEzimL268TPHz14xy8Fueatfpe6x6ncW4bX6JNMbK137bXO5G7yJwszq2a4XRhbNG1wred5PCrj3c/wBd0/K/0j3PC9ZwvffTLND6/wBDyf2TqeF/o/qfPu9xn0+j1dsM8csePnXzqr+TGWZoUKGxiakmBsAQSCCoINSCCCoJLmZoZlzMsXMyxcggEgoaFC5BYzLkEEmZYsSVBQksQSVBBJYqSSSQSQCpcoaFC5Q0MwCpYkkgkkwNyhYwOQZkFypYsVLkAsQSSCQAAfmC+I/0tHFzo8Pv+Y4lmnEwmNb9S2WPY0b+UT6/U7/YVbkRlESPI7nn/QVdDsMNuIyZYxjneyhONrKZzr8/no9vGxxr+f4Xe8zrbr+sx3fUxt7X6k5YRGWt+mRGFtKdycsKVbHYzRphdvVf84v4Hqen4/7H0fJ9/wAH6b979H8o/oLu/MO1wz/oHo+G7WrZ7zV3u11t+yOJlhtGfJicTQFSS5QkGRqDM2KFShoCDUzKEli5xjkAAzNDI1BBY4xyjjHIKElyCxkSXKgsZkFyQQULnHOQADMuULkkFjjHIMTUgFwWMSxcoCxkSWBJYoScQ5hUzJJNChYzNzI0JIABJIJBAIPzC/Ef6WcPOjwfQ8thnr8zG3tcNvpNnla7fI2q3/Y6ff4+NkV291XvRGaCcfnHR8h7nQ9V2GeNcbLZ1RGUzjpfqQllh5C/j9/lnyIs+c7fnCORvcftmftcOpzIu1v0UZzlVpZr56/Q0zovTsctGlO35rCjo7eV6va43Scz1P8AoD6/4t9/9L8h+0dXwXbYz3ddvqNLp+i0+lzatm5BUsQWLlCpoZkFyDM1KFyCSDI1BIKlSQCSxYzJIKli5QksUINCACSCSpYgkgqXIBJiaFSpoSWMixBUsXMy4IKGxUEkEgoWILFShcEFyCxxy4LEgxLmpQsQSAQWJKkgsAAQfl++Jf0n8B0fKc6LPTa3W5azwu75zi7GhtsaOle19J5/rmOfHws3nGuOcY2RMfMel432Wv2PQUdSsZbW6tZmE2spiJhPitzzs26vLr3PNbHHnLCcsNtrmcvc5frMd30Wr3LZRZjpDQpXfz7NXsrNXfT6vzOzi9gq66rY9Rbpf6Tet+Lf0/6n4f2duj3FOz2dWx9C5XoOVjZUuULmZqSVJJKEEkkEGhiWNCCpBJBcFCQCpcoagwNSpIILkEAqaAgkkqVLFipYqVLmZoVAKliC4MTUoXKg0KlC5maEkEggoaAAGRoZmxmQAaGRYuZFySpcoXIBBYsUJLEkAEmR+XP4t/RnlLe0xs4OxzPDdDzPHyrqz0u04mfpPP8AW7VbV86P9avb/mGMc645zMdBfy9sbu4p37Z1TlhXC2csSIxsg6q7Q4tumxsjKuZxnLHS3VnLCZw5+G32eN8zCrY33OJ2fY8T2NO31XE93yU9HZpdhXf5ynZ+m9bxH1zZ5fqN3z2jFMeg1t/taNkmxBBczNCCCSSoAJILFCpqVJIJKElgAQACSCSpJJAJBABIAILEAAkEAEEggAEkElSSxQkkgkgEgAgsQACSACASQQCwIBBYqWBUuQCCQUJJLAoXIJPzIfEP6STZVw9ni+E6Xl+blj2ut3ug2OV19lUns9bsekw3h+mv6v8Az6AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFSgBcgkAofml+H/ANGeLucfxfU8p67Oztaep4Pb4nmWd7KNrNTnV7X0ens50b36YvqP4KAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFSpU0BQsQSVPzmfD/355vqcrsNmqle14ze4fjM8NLNaZxvbrZrPbava77T7f6XfqX4NAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEGJcsQUNCoND89nxD9vdH2dLibGHiqup893OTrbq99Tu8ba53URMZ4cijZ+javoP0w/Tfw0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIMwXIIBU0IPz8/nn959L6jgePz7PzXe85z43fW1dHgWa/g9/wA9lhfoxzme9mP1KfQfx2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABmCQQACh/hx+XP3b8/7HT+f+n85ToU64dbHGv5b0OBxs8LYze3VX69cbf1Ve+/IgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgqSQSULEEHGP8UvzF+4Ok27vGbfV4XY4/nuzrfLt7jdhNWMXdPZoT0uXnq7kV7P6mvoH5LAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEGZoVAKgkof4p/l39veL6u9xsrOoy2/n3S0eft87Lp6fzna4tMo427qxr7/AKrmdv8ATP8AW/xUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIIBUsQCpBxD/HT8r/ALV850b/ADm1vde2KZU4Z7Hyfp8TkbeHSb9PQ7fJmjZ+pcD1f6Mvu34RAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEAAFSSDjH+TP5M/Y3guz0FuHjrexXJ5Da6HHifM7fN8Nv8jPb1a363o+V6P9Ln278OAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQCCSACgP8AJj8nfsHxvV3emu2fL29TyG70eNNnLojy+7zvF7nI4W3q8XDYxyn9Qv2f8UgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAQSCpIKkn+Zn5E/VXxT0nouk2r/Jz2urtv4OV/n7Nf570vNxLgbjstfq+i0u5+kj7v/P8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgEkEEkEEn+a/5D/UvyT0nY+a9HvTq39Bdu8Obuty2fF7vL8Jv8rk7WfP1tzr5r/Tl9q/D4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEkAFST/N78r/pLxc93511Oz5izp+d2d3pMt3rG3wc7vC73L6Xr+UY2fQuN6/9Gf3f8CgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAf5wfmX9C9Todn472vTeQx7nk97f6O3bmHF2sedoZ+K9Fw/MbfnfacvV/Rl9r/ACYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABU/wA4/wA2ff8AHkdn412PTfPLPR9flf0G7f1kbmnS0MNnD30+a9jveH58eC/2T+r/ADAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQUP87fzp914/mPTfM+t2vJ5dbw+91uit3PK7m/9L3fE/fPdfB/o274fPzPqePr7H+in1X5wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIB/nf+evt3E8h6/zd2/8x6vb8Psdn2Opzvtej4vs/Y+M7f7H8d5n0j5r1vx37LTn9H/Qn6B40AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAf56/EfrPW/MvpNr6fN7O96XX0b7WtjrbFdjX5/0f553v6T/ADZXV3es+N/Zv9B/fePAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAH+fvyT6R1Hyf6nXX2NLar541zw06nN4+hu1ie8/Sf5y5n075fl5P1/wDfOt2QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB/AXyT6N03y36jnyujvs6+3Q089nW5nY5TXvw7HG739Kfm6Oxxrw/u3xn0YAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfwZ869l0Hxr7Gqz0rsv3uLphlv0+d6P1vlvSfavifTdzg9dnhqn+3vHfQgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB/CvzT3Hnvk31eZi1mGnU5utefd+w8l9C+4fD/W7un5e6jz91XFyx/sfyfuwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB/Evzv2fk/kn1nk72nnDfHLvfZ+P8ArX3r4P22UdtXZMT43Z1OBlH9L+e9cAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP4u8Z6TzXyL63rt61NTZ9D67yf2n7r8Q7eM/QUbGk48TOuInoLa/rXM7QAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEH8n9Dh+Y+QfYOLy+l6b6B8++re58XzMc/Wau96XW28csc0VmB2td4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/l70fjur8b7XvfRec7zZ1vVa252lO17DU3uXjZBBINAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAfy36XxfMws7+nY7HCzm4WdtTf7zQ62kZyWKEmgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABB/MPpfF87Czt6re0rv5+Fno9bb9hpdUSCCS4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIB/MHpfFd/Tsap9PrbXYV3ep1Oj3NG2ILFC5YAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgFT+WfT+J7Gu3tcMvWa25y8LPbaHX7KrYsVJBJYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgEHx7teY8rdTzIeq19ntqdn22h1+RjZJUkAuAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQASQQCSp4To8XrbKMpjaJ7zX3fWafS0jIQWIINAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAQSQChjlX1Nuv11uvdPY139vRtaRkABU1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIIJIIJBU0IMjDLAxJ3xz1TQsQQDQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAggEkAqSCShYgkqWBJBJU0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIAKkgFC5JUqSWIJKlyhILgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFQQSQWIKFiSCpcqWKkkAA0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABBUkEAsVILgoCxBJAKkkkGgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKkElSSQCpJYgkgqWAJIJILAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgEEkAgkFipBIILAgEFiCwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIBBIIBBJQ0IIBJJAJIALAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgEEkAAEFipYoWAJIJAJAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAIJKkgkgkFC5BBIJIJIJBBIBBIIJAAAJAIAJIABJAABBIBJAJAIJIJIJAAIJAAAAAAAAABABJBIAAAAAABBIAAAAAAIJIJIJBBIBBIAIJAIJIBIIABIAIAJIABJUkgkggkAkgEgEEggAkgkAEAEkEgEEkEkEgAAEkAAAEkEggkgAAEkEkEgAAAEEkEgAAAAAAAAAEAkgkAAAAAAAAAgEgAAAAgEkEgEEgAAgkgkAgkgAEgAgkEAAAEkAEEgEAAkgkgEkEgFSwBJAAKlgQASQASASCACSASQSQSAQSQSAACASCACQACCSACQQSAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQSAQSAACCQCASAAQSQSAQSQAAAQCSAASACSpJBIAIJAAAAIABYgEkAAEkEkEkEgEAkAgkAAEAEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEggkAAgkgkEEkEkEggAEkAEEgAgAkFSwIBJBYgEkEEgAEEggkkEAAAkEEkAEkEgAEAEggkEEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEgAAgkAEEkAEkEkAkgAgEkAsVALEAEEgAAAkgEkEkEEkEkkEkEkAkAgEgEEgAAAgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgkAEEgAAEEgEEkEkEkAEEkEgAgEklSxAIJAABJUkAEkAAAEkAEgAAgkgEgAgkAAAAgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEgAAAAgkgEkEggkgAkEAEElSxBJUsCCQSCAAAASQASCASVLEEggkAAAAAAEEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEgAAAAAAAAgEkEkEkAEAAguQACSACSASQSCACSCSCQQSQSAQSAAQSAAAAAAACCQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQSAAQSAQSAQAACSCASCpcgAAkgkgEFiCSASACCSCQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQSACCQCCSCSASQCCSCQCCQAACQCACQCCQQCQAQSAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACCQAQAAAQWKliACSACQQSQCQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQSQSCAAASAQSQCSCSACSCQAAAAAAAAQSAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQACSCSACSAACQACCQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQSQACSAACQQSQSAAQSAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACACSACShcgAEkAkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgEgEEgAEAEggkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgkAAAEEggkgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAqWAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB//xAA0EAABAwIFAgUDBAMAAgMAAAABAAIDBBEFEBIhMRNBBhQgInAY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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEIdjAkEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgVFpAkgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEkOs0EgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAmVNAgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEgEkErFhkgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEEkAAzUBEAkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEkkAgEj9EEkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAgAEEgkAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEggkgAkEkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEkkAkggkgkkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAkEEEAEAkkEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAkkgAgAEEkAkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAkgkkAkgAgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgggkgkEggEgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAkkkAkEEEgEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgkkkAgEkEAgEAkgkkEEAEkAkgEEgggkAEEAAAEAAAAAAAAAAEggAAAAAAAgAAAAAAAEEAgAgAEAEEgEEgAEkAAgkgggkgkgEkggEEkggEAAkkgggkEgAEEgkgggAAAAggAAAAAAAAAAkEAAAAAAAAAEgAAAAEAgAgAAEEAEEkgAEAkkEgEkgEgEkEkkEgAkAkEEEkAgAEEggAAgAAAEgEkAAEEkAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAgAAEAEgAAgAAgEkAEAkgggAgEgkEgAgkEEggggAAAAkAEAAAkgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgEAAEEAggAEkggEkkkEAgkkAAkkEkAAAkkkAAgggAAkgEAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAEAAggggkEkkkgEgggEggEAAgkkggAkAEAAgAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAgAAAgAgggkkEAEgAgkEggAkggEEkgkgAAEEgAEAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAEEggAEgAAEkEEkkgEkEEgggEAggEAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAAAAAEggAEAkkEAgEggEAEgggEEAEAAEAAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAEAAAAkkgEAEEggEEkEEgAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAEAEEEAgkgkkgkkAEkAEAkAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAkEEEAAEAkAgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAggAgkgAAEEAgEAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgkEAgEkEAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgkgEkgAAgAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEkEkEEkgkAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEgAgAAkgEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAgEEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA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",
        "feed_icon": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAMAAABhq6zVAAAABGdBTUEAAK/INwWK6QAAABl0RVh0U29mdHdhcmUAQWRvYmUgSW1hZ2VSZWFkeXHJZTwAAAD/UExURdlyKd5yMOF4MeiGNemHNdteKt1jK99qMOBpLOFuNONvLuNyNeOAU+VzLuV2NuZ6M+d2MOh5MOh7N+l+N+t+MuuAMeuAOeuDOeyHPu2aY+6FM+6GOu6HOu6mfe+GNPCLO/CNQPCdZfGKNPGMPPGPOfGVTfGxivKPPPOONvOPNvOkZvO2i/SSPfSTPfScT/S8mPWVO/WWPvaUN/abRParaPeXOPeZP/eydfiYOPi5gfjEmvjFmvmrXfmxavnHmvqbOfq3dvq4dvq9g/rl2PudOvujRvuuXvuvX/u6d/u/g/zAg/3q2f3v5f3w5v3x5v7nzv7y5v7z5v748v/58////wfSbk0AAAAFdFJOUzDv7+/vprtoDgAAAI9JREFUCB0FwVELgjAQAODd3XYztdQeQvo1Qv//rfeIgggkGurSeW59HyhstKGMdboKYsEQCY2tOoIKL2pxk7HG/agGL7beI7phoQbbMMTCuq9fNfFZyTyWx6dHzOxtgnJ5ciGCvMthlMNrboOg5lO+vZkeTdzQWIl9r8xHaQHducF7CTEmoXjPtjUlpSCkP9saQ08zzj08AAAAAElFTkSuQmCC",
        "bullet": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAQAAAAEBAMAAABb34NNAAAAJFBMVEW92OJ0iJG91+KFl56ClZ5qfIR0h49peoK81+G+2OJebnYJERfu9vKuAAAAFElEQVQIHWOYtYiheitD9kaGZgcAG+oETJeFk0UAAAAASUVORK5CYII=",
        "world": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAMCAYAAABWdVznAAAABGdBTUEAAK/INwWK6QAAAaRpQ0NQSUNDIFByb2ZpbGUAAHgBrZI7SMNAGMf/iYgi1cUnihBEqkOUoosFEWoGKxWsRfCxpUmshZqG5Kw6OjgKBSfFwQc4iTiJYyenbgVBEEF0cRAEwUUkfpdDKii4eHCX3/3ve+S77wC5pDtOTgawYjM3NTGuzC8sKnU3qEcXiTR0w3NiyeSU2P22vl1D4nplgMfy4+rD5nTPFcs+7W4+b1d+8/imhVxKCEgtpLVkBPdzTgse5bzGHEY2Sc7Gsm4S04TqzqY04iJxU0bwAee04HPOBSPDfUvEEdvM2sQvxCOm5RmAzHMxw3HJRt4n7uX105cGSwBj3UBNuaotesDpCdAermr9HUDrHHA5XNVeZ4I7kdrK3tLwUBBOCo0DtXe+/xoG6naAj6Lvvx/5/scx5bgFSrax6hYCW/pJOQr8tRe1ieiiB8S8F0E/frKoP7CPAIdxYK4BSGwBe/dA3xnQfAEkG4HZKOSRx68p7irw69T0XDbt6swyFf5ctHwu73qObljB8f8tzFqnngBa3tlws5llpsTodVmqMmkbg6oyFIlE8Qk3BXczyiXR/gAAAAlwSFlzAAALEwAACxMBAJqcGAAAAhFJREFUGBkFwc1Lk3EAwPHv83uezc1n785Zak7TNUOMsDAi6mgE1a0QD0FCQtG9f6JbRJ2LLt26VEZQhygj0yinrlnTtZq6Fzefue152fP0+UgAAGef93vHYuenY52R29jyWNtBEdjpSrP4OF1aefL+eqoOIAFce30xkgiPPEiGRqbHIyfEvu5Da8gY7Rob2iKFWubFamF17s2Nj7vy1PyUOh4cfnRp5MLMyeikZNt+tlsu6raPQs1PwIkTj3hGa9p2snZOfyn6lPD1RDA+0+HpYdnYJW+0qLTc/C5Z/KpUyctZOkI2A/7+q3Hp0E2lT43eTYSH2GiVCcmDaHU3q/8sNLuC0feZeucOB1WZM9FBvinrc8Itu0YtIVja+05Fr7NZMSlpNaK9GkVXnZymsZX/gyK5cSxpSMFBsqwmTitI/sAhtSmwTA+7WZVu+RRqzcDWP9CO6pimKYlGq/WzbZh0E6By0MQwHBxPkHwhRHZJpVnsJCqHaeh1DF3Pyf1XevHK3ss+YbKt5ZCsI5iWiiwUXB1ZVP8iCb/FRjHHcnb9vmxOkPYK9+hwuOd4LBCj3e5GsmTctk2X+oVjwTKSAp/SP+YX1r7ek8tvy4Y1Kd7tVWtJYTnJofBhAgJ6/ToDXVUyhQwLa6n55Ux2tvFsvyQBAHAH3+noxK0uX2jWMqWjQoCQrK2/pZ2nK6n1h7xiH+A/1vfxSHYY5ggAAAAASUVORK5CYII=",
    },
}
