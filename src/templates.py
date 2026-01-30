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
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="/feed.atom">
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="/feed.rss">
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

            <form action="/search" method="GET" class="search-form">
                <label class="search-label"><strong>Search</strong></label>
                <input type="search" name="q" placeholder="Search entries..." aria-label="Search entries">
                <button type="submit">Search</button>
            </form>

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
        <p><a href="/feed.atom">Atom</a> · <a href="/feed.rss">RSS</a> · <a href="/feeds.opml">OPML</a></p>
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
    <link rel="alternate" type="application/atom+xml" title="{{ planet.name }} Atom Feed" href="/feed.atom">
    <link rel="alternate" type="application/rss+xml" title="{{ planet.name }} RSS Feed" href="/feed.rss">
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

            <form action="/search" method="GET" class="search-form">
                <label class="search-label"><strong>Search</strong></label>
                <input type="search" name="q" placeholder="Search entries..." aria-label="Search entries">
                <button type="submit">Search</button>
            </form>

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
        <p><a href="/feed.atom">Atom</a> · <a href="/feed.rss">RSS</a> · <a href="/feeds.opml">OPML</a></p>
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

STATIC_CSS = """/* Planet Python Theme - Faithful recreation of planetpython.org */
/* Based on the original python.org/PSF design language */
/* LEFT sidebar, Georgia headings, classic blog aggregator style */

:root {
    /* Primary Blues - from python.org brand */
    --python-blue-dark: #234764;
    --python-blue-medium: #366D9C;
    --python-blue-light: #5E72A5;

    /* Navigation colors */
    --nav-dark: #4B5A6A;
    --nav-medium: #3C4B7B;
    --nav-light: #5E72A5;

    /* Link colors - classic web style */
    --link-color: #0000AA;
    --link-visited: #551A8B;
    --link-hover: #366D9C;

    /* Backgrounds */
    --bg-primary: #FFFFFF;
    --bg-secondary: #F5F5F5;
    --bg-tertiary: #F7F7F7;
    --bg-highlight: #FBFBF7;

    /* Accent colors - Python yellow */
    --accent-yellow: #FFDB4C;
    --accent-gold: #FFBC29;

    /* Text colors */
    --text-primary: #000000;
    --text-secondary: #333333;
    --text-muted: #696969;

    /* Borders */
    --border-light: #CCCCCC;
    --border-medium: #999999;
    --border-dark: #666666;

    /* Success/Error */
    --success: #228B22;
    --error: #CC0000;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: Arial, Verdana, Geneva, Helvetica, sans-serif;
    font-size: 103%;
    line-height: 1.4;
    color: var(--text-primary);
    background: var(--bg-primary);
}

/* Headings - Georgia serif font, Python blue colors */
h1, h2, h3, h4, h5, h6 {
    font-family: Georgia, "Bitstream Vera Serif", Palatino, serif;
    font-weight: normal;
}

h1 {
    font-size: 160%;
    color: var(--python-blue-dark);
}

h2 {
    font-size: 140%;
    color: var(--python-blue-medium);
}

h3 {
    font-size: 135%;
    font-style: italic;
    color: var(--python-blue-medium);
}

h4 {
    font-size: 125%;
    color: var(--python-blue-medium);
}

/* Header - Python.org style logo banner */
header {
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-medium);
    min-height: 84px;
    padding: 0.5rem 3%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 1rem;
}

header .logo-link {
    display: flex;
    align-items: center;
    flex-shrink: 0;
}

header .logo {
    max-height: 71px;
    width: auto;
}

header .header-text {
    display: flex;
    flex-direction: column;
    justify-content: center;
}

header h1 {
    font-size: 145%;
    margin: 0;
}

header h1 a {
    color: var(--python-blue-dark);
    text-decoration: none;
}

header h1 a:hover {
    color: var(--python-blue-medium);
}

header p {
    color: var(--text-muted);
    font-size: 0.9em;
    margin: 0;
}

header a {
    color: var(--python-blue-dark);
    text-decoration: none;
}

header a:hover {
    text-decoration: underline;
}

/* Container - LEFT sidebar layout (classic Planet style) */
.container {
    display: flex;
    flex-direction: row;
    max-width: 100%;
    margin: 0 3%;
    padding-top: 1rem;
    gap: 1.5rem;
}

/* Sidebar - Left position, 16em width */
.sidebar {
    width: 16em;
    flex-shrink: 0;
    order: -1; /* Force left side */
    padding-top: 0.5rem;
}

.sidebar h2 {
    font-size: 100%;
    color: var(--python-blue-dark);
    text-transform: uppercase;
    font-weight: bold;
    font-family: Arial, Verdana, Geneva, Helvetica, sans-serif;
    margin-bottom: 0.5rem;
    padding: 0.4em 0;
    background: var(--bg-secondary);
    border-left: 4px solid var(--accent-yellow);
    padding-left: 0.5em;
}

/* Sidebar links (RSS, titles-only, Planet Planet) */
.sidebar-links {
    margin-bottom: 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border-light);
    font-size: 0.9em;
}

.sidebar-links a {
    color: var(--nav-medium);
    text-decoration: none;
    margin-right: 1em;
}

.sidebar-links a:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

/* Search form styling */
.search-form {
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border-light);
}

.search-form .search-label {
    display: block;
    margin-bottom: 0.5em;
    color: var(--text-primary);
}

.search-form input {
    width: 100%;
    padding: 0.4em;
    border: 1px solid var(--border-light);
    font-size: 0.9em;
    margin-bottom: 0.5em;
    font-family: inherit;
}

.search-form input:focus {
    outline: 1px solid var(--python-blue-medium);
    border-color: var(--python-blue-medium);
}

.search-form button {
    padding: 0.4em 1em;
    background: var(--bg-secondary);
    color: var(--text-primary);
    border: 1px solid var(--border-medium);
    cursor: pointer;
    font-size: 0.85em;
    font-family: inherit;
}

.search-form button:hover {
    background: var(--accent-yellow);
    border-color: var(--accent-gold);
}

/* Feeds list - Classic indented navigation */
.feeds {
    list-style: none;
    font-size: 0.9em;
}

.feeds li {
    padding: 0.3em 0;
    border-bottom: 1px dotted var(--border-light);
}

.feeds li:last-child {
    border-bottom: none;
}

.feeds li a {
    color: var(--nav-medium);
    text-decoration: none;
}

.feeds li a:visited {
    color: var(--link-visited);
}

.feeds li a:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

/* Health indicators */
.feeds li.healthy::before {
    content: '\25CF';
    color: var(--success);
    margin-right: 0.4em;
    font-size: 0.6em;
    vertical-align: middle;
}

.feeds li.unhealthy::before {
    content: '\25CF';
    color: var(--error);
    margin-right: 0.4em;
    font-size: 0.6em;
    vertical-align: middle;
}

/* RSS icon in sidebar */
.feeds li .feed-icon {
    color: var(--accent-gold);
    margin-right: 0.3em;
}

.feeds li .feed-icon:hover {
    color: var(--accent-yellow);
}

/* Submission link at bottom of subscriptions */
.submission-link {
    margin-top: 1rem;
    padding-top: 0.75rem;
    border-top: 1px dotted var(--border-light);
    font-size: 0.85em;
    color: var(--text-muted);
}

.submission-link a {
    color: var(--nav-medium);
    text-decoration: none;
}

.submission-link a:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

/* Navigation Level Styling (for Related Sites sections) */
/* Level One - Section headers */
.nav-level-one,
h2.nav-level-one {
    background: var(--bg-secondary);
    color: var(--nav-dark);
    border-left: 4px solid var(--accent-yellow);
    border-bottom: 1px solid #DADADA;
    padding: 0.4em 0.5em;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
    font-size: 100%;
    font-weight: bold;
    font-family: Arial, Verdana, Geneva, Helvetica, sans-serif;
    text-transform: uppercase;
}

/* Level Two - Link lists */
.nav-level-two,
ul.nav-level-two {
    list-style: none;
    font-size: 0.9em;
    border-top: 1px solid #DDD;
    margin: 0;
    padding: 0;
}

.nav-level-two li {
    padding: 0.25em 0;
    border-bottom: 1px dotted var(--border-light);
}

.nav-level-two li:last-child {
    border-bottom: none;
}

.nav-level-two a {
    color: var(--nav-medium);
    text-decoration: none;
}

.nav-level-two a:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

/* Level Three - Indented items */
.nav-level-three,
li.nav-level-three {
    margin-left: 1.8em;
    font-size: 95%;
}

.nav-level-three a {
    color: var(--nav-light);
}

.nav-level-three a:hover {
    color: var(--link-hover);
}

/* Related links list styling */
.related-links {
    list-style: none;
    margin: 0;
    padding: 0;
}

.related-links li {
    padding: 0.3em 0;
    border-bottom: 1px dotted var(--border-light);
}

.related-links li:last-child {
    border-bottom: none;
}

.related-links a {
    color: var(--nav-light);
    text-decoration: none;
}

.related-links a:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

/* Main content area */
main {
    flex: 1;
    min-width: 0;
    line-height: 1.4em;
}

/* Day headers - Date grouping */
.day {
    margin-bottom: 1.5rem;
}

.day h2 {
    font-size: 140%;
    color: var(--python-blue-medium);
    border-bottom: 1px solid var(--border-light);
    padding-bottom: 0.3em;
    margin-bottom: 1em;
}

.day h2.date {
    color: var(--text-muted);
    font-size: 100%;
    font-family: Arial, Verdana, Geneva, Helvetica, sans-serif;
    text-transform: none;
    font-style: normal;
}

/* Articles */
article {
    margin-bottom: 1.5rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border-light);
}

article:last-child {
    border-bottom: none;
}

article h3 {
    font-size: 135%;
    font-style: italic;
    color: var(--python-blue-medium);
    margin-bottom: 0.25em;
}

article h3 a {
    color: var(--link-color);
    text-decoration: none;
}

article h3 a:visited {
    color: var(--link-visited);
}

article h3 a:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

/* Article header (nested inside article) */
article header {
    background: transparent;
    border: none;
    height: auto;
    padding: 0;
    display: block;
}

/* Author/meta information */
.meta {
    font-size: 0.85em;
    color: var(--text-muted);
    margin-bottom: 0.75em;
}

.meta .author {
    color: var(--python-blue-medium);
    font-weight: normal;
}

.meta .author a {
    color: var(--link-color);
    text-decoration: none;
}

.meta .author a:hover {
    text-decoration: underline;
}

.meta .date-sep {
    color: var(--text-muted);
    margin: 0 0.25em;
}

/* Content area */
.content {
    line-height: 1.5;
    color: var(--text-secondary);
}

.content p {
    margin-bottom: 1em;
}

.content p:last-child {
    margin-bottom: 0;
}

.content img {
    max-width: 100%;
    height: auto;
    margin: 0.5em 0;
}

.content a {
    color: var(--link-color);
    text-decoration: underline;
}

.content a:visited {
    color: var(--link-visited);
}

.content a:hover {
    color: var(--link-hover);
}

.content ul, .content ol {
    margin: 1em 0 1em 1em;
}

.content li {
    margin-bottom: 0.3em;
}

.content code {
    font-family: "Courier New", Courier, monospace;
    font-size: 0.95em;
    background: var(--bg-secondary);
    padding: 0.1em 0.3em;
}

.content pre {
    font-family: "Courier New", Courier, monospace;
    font-size: 0.9em;
    background: var(--bg-secondary);
    border: 1px solid var(--border-light);
    padding: 1em;
    overflow-x: auto;
    margin: 1em 0;
}

.content pre code {
    background: transparent;
    padding: 0;
}

.content blockquote {
    border-left: 3px solid var(--python-blue-light);
    padding-left: 1em;
    margin: 1em 0;
    color: var(--text-muted);
    font-style: italic;
}

.content table {
    border-collapse: collapse;
    margin: 1em 0;
}

.content th, .content td {
    border: 1px solid var(--border-light);
    padding: 0.5em;
}

.content th {
    background: var(--bg-secondary);
}

/* Footer */
footer {
    background: var(--bg-tertiary);
    border-top: 1px solid var(--border-medium);
    padding: 1.5rem 3%;
    margin-top: 2rem;
    text-align: center;
    font-size: 0.85em;
    color: var(--text-muted);
}

footer p {
    margin-bottom: 0.5em;
}

footer p:last-child {
    margin-bottom: 0;
}

footer a {
    color: var(--link-color);
    text-decoration: none;
}

footer a:hover {
    text-decoration: underline;
}

footer kbd {
    font-family: "Courier New", Courier, monospace;
    font-size: 0.9em;
    background: var(--bg-secondary);
    border: 1px solid var(--border-light);
    border-radius: 3px;
    padding: 0.1em 0.4em;
}

/* Skip links for accessibility */
.skip-link {
    position: absolute;
    left: -10000px;
    top: auto;
    width: 1px;
    height: 1px;
    overflow: hidden;
}

.skip-link:focus {
    position: static;
    width: auto;
    height: auto;
    padding: 0.5em 1em;
    background: var(--accent-yellow);
    color: var(--text-primary);
}

/* Keyboard shortcuts panel styling */
.shortcuts-backdrop {
    background: rgba(0, 0, 0, 0.5);
}

.shortcuts-panel {
    background: var(--bg-primary);
    border: 1px solid var(--border-medium);
    border-radius: 4px;
}

.shortcuts-panel h3 {
    color: var(--python-blue-dark);
    font-style: normal;
    border-bottom: 1px solid var(--border-light);
    padding-bottom: 0.5em;
    margin-bottom: 1em;
}

.shortcuts-panel kbd {
    font-family: "Courier New", Courier, monospace;
    background: var(--bg-secondary);
    border: 1px solid var(--border-light);
    border-radius: 3px;
    padding: 0.2em 0.5em;
}

.shortcuts-panel .close-btn {
    background: var(--bg-secondary);
    border: 1px solid var(--border-medium);
    padding: 0.4em 1em;
    cursor: pointer;
}

.shortcuts-panel .close-btn:hover {
    background: var(--accent-yellow);
}

/* Responsive design */
@media (max-width: 768px) {
    .container {
        flex-direction: column;
        margin: 0 1rem;
    }

    .sidebar {
        width: 100%;
        order: 1; /* Move below content on mobile */
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid var(--border-light);
    }

    header {
        height: auto;
        padding: 1rem 1rem;
        flex-direction: column;
        gap: 0.5rem;
        text-align: center;
    }

    footer {
        padding: 1rem;
    }
}

/* Titles-only page styles */
.titles-only .view-toggle {
    margin-bottom: 1rem;
    font-size: 0.9em;
}

.titles-only .view-toggle a {
    color: var(--nav-medium);
    text-decoration: none;
}

.titles-only .view-toggle a:hover {
    color: var(--link-hover);
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
    color: var(--link-color);
    text-decoration: none;
    font-family: Georgia, "Bitstream Vera Serif", Palatino, serif;
    font-style: italic;
}

.titles-only .entry-title:visited {
    color: var(--link-visited);
}

.titles-only .entry-title:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

.titles-only .entry-meta {
    font-size: 0.85em;
    color: var(--text-muted);
    margin-left: 0.5em;
}

.titles-only .entry-meta .author {
    color: var(--python-blue-medium);
}

.titles-only .entry-meta .date-sep {
    margin: 0 0.25em;
}

/* Titles-only page - Channel/Author grouping structure */
.titles-only h3.post {
    font-size: 135%;
    font-style: italic;
    color: var(--python-blue-medium);
    margin-top: 1em;
    margin-bottom: 0.25em;
}

.titles-only h3.post:first-of-type {
    margin-top: 0;
}

.titles-only h3.post a {
    color: var(--link-color);
    text-decoration: none;
}

.titles-only h3.post a:visited {
    color: var(--link-visited);
}

.titles-only h3.post a:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

.titles-only h4.entry-title {
    font-size: 100%;
    font-family: Georgia, "Bitstream Vera Serif", Palatino, serif;
    font-style: italic;
    font-weight: normal;
    color: var(--python-blue-medium);
    margin: 0.25em 0 0 0;
}

.titles-only h4.entry-title a {
    color: var(--link-color);
    text-decoration: none;
}

.titles-only h4.entry-title a:visited {
    color: var(--link-visited);
}

.titles-only h4.entry-title a:hover {
    color: var(--link-hover);
    text-decoration: underline;
}

.titles-only p.entry-meta {
    font-size: 0.85em;
    color: var(--text-muted);
    margin: 0 0 0.5em 0;
}

.titles-only p.entry-meta em {
    font-style: italic;
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
        background: white;
        border-bottom: 1px solid black;
    }

    article {
        page-break-inside: avoid;
    }

    a {
        color: black;
    }

    a:after {
        content: " (" attr(href) ")";
        font-size: 0.8em;
    }
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
