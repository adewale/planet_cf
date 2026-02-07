# Performance Guide

Planet CF runs on Cloudflare Workers with Python via Pyodide (WebAssembly). The main performance constraint is Pyodide's cold-start latency (~1.8-3s TTFB on the first request to a cold isolate). Every optimization in this document exists either to hide that cold start from real users or to make the warm path as fast as possible.

## Caching Strategy

### Cache-Control with stale-while-revalidate

Every HTML and feed response includes (`src/utils.py:199-201`):

```
Cache-Control: public, max-age=3600, stale-while-revalidate=3600
```

- **Hour 0-1 (fresh):** Cloudflare edge serves the cached response directly. Zero Worker invocations.
- **Hour 1-2 (stale):** Edge serves the stale response instantly to the visitor while making a background request to the Worker to refresh the cache.
- **Hour 2+ (expired):** Only if nobody visits for 2+ hours does the cache fully expire.

This means visitors almost always get an edge-cached response (~20-50ms), even when the content is slightly stale.

### Edge cache pre-warming

The hourly cron scheduler, after enqueueing feed fetches and running retention cleanup, requests the 4 most important pages on itself (`src/main.py:544-552`):

```python
for path in ("/", "/titles", "/feed.atom", "/feed.rss"):
    await safe_http_fetch(f"{base_url}{path}", headers=warm_headers)
```

This ensures the edge cache always has a fresh copy, even if no real user has visited recently. Combined with `stale-while-revalidate`, there is no window where a visitor hits an uncached Worker.

| Time | What happens | Visitor experience |
|------|-------------|-------------------|
| 0:00 | Cron fires, fetches feeds, pre-warms cache | Cache now fresh |
| 0:01-1:00 | Visitors get cached responses | ~20-50ms |
| 1:00-2:00 | `stale-while-revalidate` window | ~20-50ms (stale but fast) |
| 2:00 | Next cron fires, pre-warms again | Cache refreshed |

### Conditional GETs

Feed fetches store ETag and Last-Modified from each response (`src/main.py:678-683`). On the next fetch, we send `If-None-Match` and `If-Modified-Since` headers. If the feed hasn't changed, the server returns 304 Not Modified with no body, saving bandwidth and parse time.

## Asset Delivery

Each Planet CF instance (planet-python, planet-mozilla, etc.) is deployed as a separate Cloudflare Worker with its own database, queues, and assets directory. They share the same source code but are independent deployments.

### Workers Static Assets

Each instance configures a [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/) binding in its `wrangler.jsonc`:

```jsonc
"assets": {
  "directory": "./assets/",
  "binding": "ASSETS"
}
```

With the default `run_worker_first = false`, Cloudflare serves matching files from the assets directory at the edge **before the Worker runs**. A request for `/static/style.css` that matches a file at `assets/static/style.css` is served directly from the CDN with zero Pyodide cold start, zero Worker CPU cost, and automatic tiered edge caching.

Binary assets (images, fonts, favicons) are already served this way. CSS and JS files should be too — see the [migration note](#planned-migration-css-and-js-to-static-assets) below.

### HTML templates compiled into Python

Cloudflare Workers have no filesystem at runtime. Pyodide cannot read files from disk, so Jinja2 templates must be in Python memory. The build step (`scripts/build_templates.py`) compiles HTML templates into string constants in `src/templates.py`. This is necessary and correct — Jinja2 needs the template strings to render HTML.

### Planned migration: CSS and JS to Static Assets

CSS and JS are currently also compiled into `templates.py` as Python string constants (`STATIC_CSS`, `THEME_CSS`, `ADMIN_JS`, `KEYBOARD_NAV_JS`) and served through a `_serve_static()` method in the Worker. This means every request for `/static/style.css` boots the Pyodide WASM runtime to return a string from memory — the slowest possible way to serve a static file on Cloudflare.

This was an early design shortcut. The correct approach is to place CSS and JS files in each instance's `assets/` directory and let Static Assets serve them. The [official Python Workers assets example](https://github.com/cloudflare/python-workers-examples/tree/main/06-assets) demonstrates this pattern. Some instances (planet-cloudflare, planet-mozilla) already have CSS files in their assets directories, but the Worker also serves its own compiled copy, creating two divergent sources of truth.

The migration will:
- Make each instance's `assets/static/style.css` the single source of CSS
- Add `keyboard-nav.js` and `admin.js` to each instance's assets directory
- Remove `STATIC_CSS`, `THEME_CSS`, `ADMIN_JS`, `KEYBOARD_NAV_JS` from `templates.py`
- Remove `_serve_static()` and the `/static/` route from the Worker
- Shrink `templates.py` to contain only HTML templates (its actual purpose)

### Inline SVG icons

Icons (like the RSS feed icon in the sidebar) are embedded as inline SVG directly in template HTML (`src/templates.py:93`):

```html
<a href="{{ feed.url }}" class="feed-icon" title="RSS Feed">
  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14"
       viewBox="0 0 24 24" fill="currentColor">
    <circle cx="6.18" cy="17.82" r="2.18"/>
    <path d="M4 4.44v2.83c7.03 0 12.73 5.7 12.73 ..."/>
  </svg>
</a>
```

Each inline SVG is ~200 bytes. An external image request would add DNS lookup + connection + transfer overhead far exceeding the cost of those bytes inline. With dozens of feed icons on the sidebar, this eliminates dozens of HTTP requests.

### Multi-format favicons

Three favicon formats cover all browsers and platforms (`src/templates.py:31-33`):

```html
<link rel="icon" href="/static/favicon.ico" sizes="32x32">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
```

- **favicon.ico** (32x32 PNG): Legacy browser support, tiny file size.
- **favicon.svg**: Modern browsers use this. Scales perfectly to any size, typically smaller than equivalent PNGs at high resolutions.
- **apple-touch-icon.png**: iOS home screen icon.

These are served from Workers Static Assets via each instance's `assets/` directory.

### System font stacks (no web fonts)

All themes use system font stacks with no web font downloads (`src/templates.py:1569, 1586`):

```css
/* Body text */
font-family: 'Georgia', 'Times New Roman', serif;

/* Headings and UI */
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;

/* Code blocks */
font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
```

Web fonts (Google Fonts, Adobe Fonts, self-hosted WOFF2) typically add 50-200 KiB of downloads plus at least one additional HTTP request, often render-blocking. System fonts are already on the user's device: zero network cost, zero layout shift from font swapping, instant text rendering. The trade-off is less typographic control, but for a feed aggregator the user experience improvement from faster rendering outweighs custom typography.

## Feed Fetching

### Queue isolation

Each feed is enqueued as a separate queue message (`src/main.py:507-527`). This gives us:

- **Isolated retries:** Only the failed feed is retried, not the entire batch.
- **Isolated timeouts:** A slow feed doesn't block others. Each gets its own `asyncio.wait_for()` with a configurable timeout (default 60s).
- **Dead letter queue:** After 3 failed retries (with 5-minute backoff), the message goes to the DLQ.
- **Parallel processing:** Queue consumers scale independently.

### Rate limit compliance

HTTP 429/503 responses with `Retry-After` headers are handled specially (`src/main.py:712-720`). They don't increment the consecutive failure counter and trigger a queue retry instead. This prevents well-behaved feeds from being auto-deactivated due to temporary rate limiting.

### Auto-deactivation

After a configurable number of consecutive failures (default 10), feeds are automatically deactivated (`src/main.py:1131-1158`). This prevents permanently broken feeds from wasting queue capacity and CPU time every hour.

## Database Optimization

### Indexes

Five indexes on the two main tables (`src/main.py:393-415`):

- `idx_feeds_active` on `feeds(is_active)` for filtering active feeds
- `idx_feeds_url` on `feeds(url)` for URL lookups
- `idx_entries_published` on `entries(published_at DESC)` for recent entries
- `idx_entries_feed` on `entries(feed_id)` for feed-specific queries
- `idx_entries_guid` on `entries(feed_id, guid)` for deduplication

### Window functions for smart result limiting

The homepage query uses `ROW_NUMBER() OVER (PARTITION BY feed_id, date(...))` to limit entries to 5 per feed per day and 100 per feed total (`src/main.py:1518-1545`). This prevents any single prolific feed from dominating the page without requiring multiple queries.

The same pattern is used for retention cleanup (`src/main.py:1808-1828`), identifying excess entries in a single query rather than looping per-feed.

### Per-isolate initialization

Database schema checks and auto-migration run only once per Worker isolate via a `_db_initialized` flag (`src/main.py:347-452`). Subsequent requests skip the check entirely.

## Worker Runtime

### Pyodide dedicated snapshot

The `python_dedicated_snapshot` compatibility flag (`wrangler.jsonc:23`) uses Cloudflare's pre-built Python snapshot for faster cold starts. This is the single most impactful Worker-level optimization.

### Per-isolate caching

The `SafeEnv` wrapper and `RouteDispatcher` are cached as instance variables (`src/main.py:294-316, 1255-1308`). Route matching is computed once per isolate, not per request.

### Async I/O throughout

All D1 queries, HTTP requests, vector operations, and AI inference use `async/await`. The Worker never blocks on I/O.

## Content Optimization

### Image lazy loading

All images in feed content get `loading="lazy"` added during sanitization (`src/models.py:350-361`). Only images in the viewport load initially.

### Content deduplication

Feeds often include the post title as an `<h1>` at the start of the content body. `normalize_entry_content()` strips this duplicate heading (`src/utils.py:142-172`).

### Summary truncation

Summaries are capped at 500 characters (`src/content_processor.py:154-169`) for feed formats that use summaries.

### Entry count limits

Three layers of result limiting prevent unbounded response sizes:
- 5 entries per feed per day (window function)
- 100 entries per feed total (configurable via `RETENTION_MAX_ENTRIES_PER_FEED`)
- 500 entries global cap (`DEFAULT_QUERY_LIMIT`)

## Known Bottleneck: TTFB

The ~1.8-3s TTFB on true cold starts is the biggest performance gap. This is inherent to Pyodide on Workers. Mitigations:

1. **stale-while-revalidate + cron pre-warming** ensures real visitors almost never hit a cold Worker.
2. **Dedicated Pyodide snapshot** reduces cold-start overhead.
3. **Minimal Python imports** at module level (no heavy libraries loaded until needed).

The TTFB only matters for the very first request to a cold isolate. Once warm, subsequent requests in the same isolate are fast (~50-200ms for HTML generation).
