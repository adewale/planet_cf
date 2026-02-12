# Planet CF Architecture

A feed aggregator built on Cloudflare Workers (Python) with D1, Queues, and Vectorize.

## System Overview

```
                         ┌──────────────────────────────────────────┐
                         │            Cloudflare Edge                │
                         │     (Global CDN, 1-hour edge cache)      │
                         └──────────────────────────────────────────┘
                                            │
                              ┌─────────────┴─────────────┐
                              │                           │
                     /static/* requests           All other requests
                              │                           │
                              ▼                           ▼
               ┌────────────────────────┐  ┌────────────────────────────────────┐
               │  Workers Static Assets │  │      Planet CF Python Worker       │
               │                        │  │     (Python via Pyodide/WASM)      │
               │  Serves CSS, JS, fonts │  ├────────────────────────────────────┤
               │  images from assets/   │  │                                    │
               │                        │  │  ┌──────────┐  ┌──────────────┐   │
               │  TTFB: ~15-90ms        │  │  │  fetch() │  │ scheduled()  │   │
               │  No Worker boots       │  │  │  (HTTP)  │  │   (cron)     │   │
               │  No Pyodide cold start │  │  └──────────┘  └──────────────┘   │
               │  Edge-cached (24h)     │  │  ┌──────────┐  ┌──────────────┐   │
               └────────────────────────┘  │  │  queue() │  │  Admin UI    │   │
                                           │  │(consumer)│  │  Dashboard   │   │
                                           │  └──────────┘  └──────────────┘   │
                                           │                                    │
                                           │  TTFB: ~1000-1400ms (cold start)  │
                                           │  TTFB: ~90ms (warm/cached)        │
                                           └──────────────┬─────────────────────┘
                                                          │
                    ┌─────────────────────────────────────┼──────────────────┐
                    │                                     │                  │
                    ▼                                     ▼                  ▼
          ┌─────────────────┐                   ┌─────────────────┐ ┌───────────────┐
          │   D1 Database   │                   │   FEED_QUEUE    │ │   Vectorize   │
          │                 │                   │   (Cloudflare   │ │   (Semantic   │
          │  - feeds        │                   │    Queues)      │ │    Search)    │
          │  - entries      │                   │                 │ │               │
          │  - admins       │                   └─────────────────┘ └───────────────┘
          │  - audit_log    │
          └─────────────────┘
```

## Request Flow

### Public Pages (/, /titles, /feed.atom, /feed.rss, /feed.rss10, /feeds.opml, /foafroll.xml, /search)

```
Browser Request
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Edge Cache Check                            │
│   Cache-Control: public, max-age=3600, s-maxage=3600            │
└─────────────────────────────────────────────────────────────────┘
      │
      │ (cache miss)
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Query D1 for entries (last 90 days, max 50/feed)            │
│  2. Query D1 for active feeds                                    │
│  3. Render Jinja2 template                                       │
│  4. Return HTML/XML with cache headers                           │
└─────────────────────────────────────────────────────────────────┘
```

### Add Feed Flow (with validation)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Add Feed Button Clicked                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. SSRF Validation (blocks localhost, private IPs, metadata)   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. FETCH & VALIDATE the feed URL (10s timeout)                 │
│     - HTTP request to the feed                                   │
│     - Parse with feedparser                                      │
│     - Check for valid RSS/Atom structure                         │
│     - Extract: title, site_url, entry_count                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
               ❌ INVALID               ✅ VALID
                    │                       │
                    ▼                       ▼
         ┌──────────────────┐    ┌──────────────────────────────┐
         │ Return error:    │    │ 3. INSERT into feeds table   │
         │ "Feed validation │    │    (with extracted title)    │
         │  failed: ..."    │    └──────────────────────────────┘
         └──────────────────┘                   │
                                                ▼
                                 ┌──────────────────────────────┐
                                 │ 4. QUEUE for immediate fetch  │
                                 │    (FEED_QUEUE.send)          │
                                 └──────────────────────────────┘
                                                │
                                                ▼
                                 ┌──────────────────────────────┐
                                 │ 5. Queue consumer fetches     │
                                 │    entries, stores in DB      │
                                 └──────────────────────────────┘
                                                │
                                                ▼
                                 ┌──────────────────────────────┐
                                 │ 6. Entries appear on homepage │
                                 │    within seconds!            │
                                 └──────────────────────────────┘
```

### Scheduled Feed Refresh (Hourly Cron)

```
Cron Trigger (0 * * * *)
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Query all active feeds from D1                               │
│  2. For each feed, send message to FEED_QUEUE                    │
│     {feed_id, url, etag, last_modified}                         │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FEED_QUEUE Consumer                           │
│  For each message:                                               │
│    1. Convert JsProxy message.body to Python dict                │
│    2. Validate URL (SSRF protection)                             │
│    3. Fetch with conditional headers (ETag, Last-Modified)       │
│    4. Parse RSS/Atom with feedparser                             │
│    5. Upsert entries to D1                                       │
│    6. Generate embeddings via Workers AI                         │
│    7. Index in Vectorize for semantic search                     │
│    8. Update feed metadata (title, last_success_at)              │
│    9. ACK message on success, RETRY on failure                   │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema (D1)

```sql
-- Feeds table
CREATE TABLE feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    site_url TEXT,
    author_name TEXT,
    author_email TEXT,
    etag TEXT,
    last_modified TEXT,
    last_fetch_at TEXT,
    last_success_at TEXT,
    fetch_error TEXT,
    fetch_error_count INTEGER DEFAULT 0,
    consecutive_failures INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_entry_at TEXT
);

-- Entries table
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    guid TEXT NOT NULL,
    url TEXT,
    title TEXT,
    author TEXT,
    content TEXT,
    summary TEXT,
    published_at TEXT,
    updated_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    first_seen TEXT,          -- Added by migration 003
    UNIQUE(feed_id, guid)
);

-- Admins table (GitHub OAuth)
CREATE TABLE admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_username TEXT UNIQUE NOT NULL,
    github_id INTEGER,
    display_name TEXT,
    avatar_url TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT
);

-- Audit log
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER REFERENCES admins(id),
    action TEXT NOT NULL,
    target_type TEXT,
    target_id INTEGER,
    details TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## Key Technical Considerations

### Pyodide/JsProxy Gotchas

**CRITICAL**: Cloudflare Workers Python runs via Pyodide (Python compiled to WebAssembly).
JavaScript objects are exposed as `JsProxy` objects, NOT native Python dicts.

```python
# ❌ WRONG - JsProxy is not subscriptable
result = await db.prepare("SELECT * FROM feeds").first()
title = result["title"]  # TypeError: 'pyodide.ffi.JsProxy' object is not subscriptable

# ✅ CORRECT - Convert first
result_raw = await db.prepare("SELECT * FROM feeds").first()
result = _to_py_safe(result_raw)  # Converts JsProxy to Python dict
title = result["title"]  # Works!
```

Key places requiring conversion:
- `request.form_data()` returns JsProxy FormData
- `db.prepare().first()` returns JsProxy row
- `db.prepare().all().results` returns JsProxy array
- `message.body` in queue handler returns JsProxy
- `AI.run()` returns JsProxy result
- `Vectorize.query()` returns JsProxy with matches array

### JavaScript/Python Boundary Layer

To prevent JsProxy bugs from recurring throughout the codebase, we use a **boundary layer pattern**
that shields business logic from JavaScript specifics:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         JavaScript World (Cloudflare Workers)                    │
│                                                                                  │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│   │    D1    │    │    AI    │    │Vectorize │    │  Queue   │    │   Form   │  │
│   │ Database │    │ Workers  │    │  Index   │    │ Messages │    │   Data   │  │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘  │
│        │               │               │               │               │         │
│        │  JsProxy      │  JsProxy      │  JsProxy      │  JsProxy      │JsProxy  │
│        ▼               ▼               ▼               ▼               ▼         │
├────────┼───────────────┼───────────────┼───────────────┼───────────────┼─────────┤
│        │               │               │               │               │         │
│   ┌────┴─────┐    ┌────┴─────┐    ┌────┴─────┐    ┌────┴─────┐    ┌────┴─────┐  │
│   │ SafeD1   │    │ SafeAI   │    │SafeVect. │    │SafeQueue │    │_extract_ │  │
│   │_to_py()  │    │_to_py()  │    │_to_py()  │    │_to_py()  │    │form_val()│  │
│   └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘  │
│        │               │               │               │               │         │
│        │  Python       │  Python       │  Python       │  Python       │ Python  │
│        │  dict/list    │  dict         │  dict         │  dict         │ str     │
│        ▼               ▼               ▼               ▼               ▼         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│                         Python World (Business Logic)                            │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │ Application code works with native Python types:                          │  │
│   │                                                                           │  │
│   │   result = await db.prepare(...).first()  # Returns Python dict          │  │
│   │   title = result["title"]                 # Works! No JsProxy            │  │
│   │                                                                           │  │
│   │   embedding = await ai.run(...)           # Returns Python dict          │  │
│   │   vector = embedding["data"][0]           # Works! No JsProxy            │  │
│   │                                                                           │  │
│   │   matches = await search.query(...)       # Returns Python dict          │  │
│   │   for m in matches["matches"]:            # Works! Python list           │  │
│   │       score = m["score"]                  # Works! Python dict           │  │
│   │                                                                           │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Boundary Layer Components** (defined in `src/wrappers.py`):

| Component | Wraps | Auto-converts |
|-----------|-------|---------------|
| `SafeD1` | `env.DB` | Query results to Python dicts |
| `SafeAI` | `env.AI` | AI model outputs to Python dicts |
| `SafeVectorize` | `env.SEARCH_INDEX` | Search matches to Python lists |
| `SafeQueue` | `env.FEED_QUEUE` | (outbound only, no conversion needed) |
| `_to_py_safe()` | Any JsProxy | Universal fallback converter |
| `_extract_form_value()` | FormData | Handles undefined and converts values |

**Rule**: All JavaScript bindings MUST be accessed through boundary layer helpers.
Business logic code should NEVER import or use JsProxy types directly.

### Python None vs JavaScript undefined

```python
# Python None becomes JavaScript undefined in D1 bindings
# D1 rejects undefined: "D1_TYPE_ERROR: Type 'undefined' not supported"

# ❌ WRONG
await db.prepare("INSERT INTO t (a, b) VALUES (?, ?)").bind(value, None).run()

# ✅ CORRECT - Convert None to empty string or 0
safe_value = str(value) if value else ""
await db.prepare("INSERT INTO t (a, b) VALUES (?, ?)").bind(safe_value, "").run()
```

### SSRF Protection

All feed URLs are validated before fetching:
- Block localhost/loopback (127.0.0.0/8, ::1)
- Block private networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Block link-local (169.254.0.0/16)
- Block cloud metadata endpoints (169.254.169.254, 100.100.100.200)
- Block internal hostnames (*.internal, metadata.google.internal)
- Only allow http:// and https:// schemes

### Stateless Sessions (No KV)

Authentication uses HMAC-signed cookies instead of server-side sessions:
```
Cookie: session=base64(json_payload).hmac_sha256_signature
```

Payload contains: `{github_username, github_id, avatar_url, exp}`

### Edge Caching Strategy

- Homepage: `Cache-Control: public, max-age=3600, s-maxage=3600`
- Feeds (RSS/Atom): Same as homepage
- Admin pages: `Cache-Control: no-store` (never cached)
- Static assets: `Cache-Control: public, max-age=86400`

### Content Security Policy (CSP)

**CRITICAL**: Admin pages use JavaScript for dynamic functionality (tabs, toggles, AJAX).
The CSP must allow this JavaScript to execute while blocking XSS attacks.

```
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src https: data:;
frame-ancestors 'none';
base-uri 'self';
form-action 'self'
```

**Why External JavaScript (not inline)**:

The CSP has `default-src 'self'` which:
- ✅ Allows external scripts from same origin (`/static/admin.js`)
- ❌ Blocks inline `<script>` tags
- ❌ Blocks `onclick`, `onchange` event handlers
- ❌ Blocks `javascript:` URLs

**Security rationale**: Admin pages display attacker-controlled data (feed titles, URLs from
RSS feeds). If we allowed `'unsafe-inline'`, an XSS payload in a malicious feed title could
execute in the admin's browser. By requiring external scripts, we maintain defense-in-depth.

**Implementation**:
```html
<!-- ❌ WRONG - Blocked by CSP -->
<button onclick="showTab('feeds')">Feeds</button>
<script>function showTab() { ... }</script>

<!-- ✅ CORRECT - Allowed by CSP -->
<button data-tab="feeds">Feeds</button>
<script src="/static/admin.js"></script>
```

The external JavaScript uses:
- `data-*` attributes instead of inline event handlers
- `addEventListener()` in `DOMContentLoaded` for initialization
- `escapeHtml()` for all dynamic content to prevent XSS

### Per-Theme Feed Format Configuration

Feed formats are controlled by theme-based frozensets in `src/main.py`:

| Frozenset | Controls | Themes |
|-----------|----------|--------|
| `_THEMES_HIDE_SIDEBAR_LINKS` | Hides RSS/titles-only sidebar links | `planet-cloudflare` |
| `_THEMES_WITH_RSS10` | Enables RSS 1.0 (RDF) feed link | `planet-mozilla` |

RSS 2.0, Atom, and OPML are available for all instances. RSS 1.0 is only linked in templates
for themes in `_THEMES_WITH_RSS10`. All feed routes (`/feed.rss`, `/feed.atom`, `/feeds.opml`,
`/feed.rss10`, `/foafroll.xml`) are registered universally — the frozensets control what appears in `feed_links`
(and thus in the rendered HTML), not whether the route exists.

### Two-Tier Serving Architecture

Planet CF has two fundamentally different serving paths, visible in the System Overview
diagram above. Understanding this split is critical for performance tuning and debugging.

**Tier 1: Workers Static Assets (CSS, JS, fonts, images)**

Requests matching files in an instance's `assets/` directory are served by Cloudflare's
Workers Static Assets infrastructure at the edge. The Python Worker never boots.

- TTFB: ~15–90ms (edge-served, no cold start)
- Configured via the `assets` binding in each `wrangler.jsonc`
- Files live under `assets/static/` in each instance directory
- Edge-cached with long TTLs; no Pyodide/WASM overhead

Static files per instance:

| File | Purpose | Canonical Source |
|------|---------|-----------------|
| `style.css` | Main stylesheet (per-theme) | `templates/style.css` (default theme) |
| `keyboard-nav.js` | Keyboard navigation (j/k/o) | `templates/keyboard-nav.js` |
| `admin.js` | Admin dashboard (full mode only) | `static/admin.js` |
| `favicon.ico`, `favicon.svg`, etc. | Favicons | Per-instance |
| Theme-specific images | Logos, banners (e.g., `images/python-logo.gif`) | Per-instance |

**Tier 2: Python Worker (HTML, feeds, API, admin)**

All other requests — HTML pages, feed XML, search, admin actions — hit the Python
Worker running via Pyodide (Python compiled to WebAssembly).

- TTFB: ~1000–1400ms cold start (Pyodide runtime initialization)
- TTFB: ~90ms warm (Worker already running, reuses runtime)
- Mitigated by `stale-while-revalidate=3600` and cron-based cache pre-warming
- HTML templates are compiled into `src/templates.py` at build time (Workers has no filesystem)

**Why this matters:**

The cold-start penalty is the dominant performance bottleneck. Lighthouse scores show
~15–90ms TTFB for static assets vs ~1000–1400ms for HTML. The caching strategy
(`Cache-Control: public, max-age=3600, stale-while-revalidate=3600`) ensures most
visitors get a cached HTML response while the Worker regenerates in the background.

**Canonical source enforcement:**

Each instance's `assets/static/` is the deployed truth for CSS/JS. For instances using
the default theme, `templates/style.css` is the canonical source — a test in
`test_theme_integration.py::TestStaticAssetsIntegrity::test_default_theme_instances_match_canonical_css`
enforces that all default-theme copies match. Similarly, `keyboard-nav.js` and `admin.js`
have their own consistency tests.

When creating a new instance, `scripts/create_instance.py` copies default static files
from `templates/` and `static/` into `assets/static/`. Instances can then customize
their CSS independently.

## Security Measures

### HTTP Security Headers

All HTML responses include comprehensive security headers:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src https: data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

- **CSP**: Blocks inline scripts, restricts images to HTTPS only
- **X-Frame-Options**: Prevents clickjacking attacks
- **X-Content-Type-Options**: Prevents MIME type sniffing
- **Referrer-Policy**: Limits referrer header leakage
- **HSTS**: Forces HTTPS connections

### SSRF Protection

Feed URLs are validated against:
- **Localhost**: `localhost`, `127.0.0.1`, `::1`, `0.0.0.0`
- **Private Networks**: RFC 1918 ranges (10.x, 172.16-31.x, 192.168.x)
- **Cloud Metadata**: `169.254.169.254`, `100.100.100.200`, `192.0.0.192`
- **Metadata Hostnames**: `metadata.google.internal`, `metadata.azure.internal`
- **Internal Domains**: `*.internal`, `*.local`
- **IPv6 ULA**: `fc00::/7` (both `fc00::/8` and `fd00::/8`)

### XXE/Billion Laughs Protection

OPML import uses `ET.XMLParser(forbid_dtd=True)` to prevent:
- XML External Entity (XXE) attacks
- Entity expansion attacks (Billion Laughs)

### OAuth Security

- **State Parameter**: CSRF protection via random state token
- **Configured Redirect URI**: Set `OAUTH_REDIRECT_URI` env var for production
- **HttpOnly Cookies**: Session cookies not accessible to JavaScript
- **Secure Flag**: Cookies only sent over HTTPS
- **SameSite=Lax**: Protection against CSRF

### Input Validation

- **Search Queries**: Maximum 1000 characters to prevent DoS
- **Feed Validation**: Feeds are fetched and parsed before adding
- **Error Sanitization**: Internal errors logged, generic messages returned to users

### HTML Sanitization

Feed content is sanitized using Bleach with strict allowlists:
- Only safe tags: `p`, `a`, `img`, `ul`, `ol`, `li`, `h1-h6`, etc.
- Only safe protocols: `http`, `https`, `mailto`
- All event handlers stripped
- `<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>` completely removed

## Known Limitations

### Rate Limiting

**Current State**: No per-admin rate limiting on API endpoints.

**Risk**: Authenticated admins could spam the system with feed additions or OPML imports.

**Mitigation**: Admin access is restricted to GitHub users in the allowlist. For higher security requirements, implement Cloudflare Durable Objects for rate limiting.

### Race Conditions

**Concurrent Entry Updates**: If two queue consumers process the same entry simultaneously, the database's `ON CONFLICT` clause handles deduplication. However, Vectorize embeddings could be duplicated.

**Mitigation**: Queue processes feeds sequentially within each consumer. The low probability of collision (different consumers, same entry, same moment) is accepted.

**Admin Status Race**: An admin could be deactivated between authentication check and action execution.

**Mitigation**: Window is milliseconds. Risk accepted for simplicity; system uses session expiration for access control.

### Cache Purge

Manual "Regenerate" button re-queues feeds but cannot purge Cloudflare's edge cache. Content updates are visible after the 1-hour TTL expires.

### Search Indexing Transactions

If Vectorize indexing fails after D1 insert, the entry exists but isn't searchable. The entry is still usable via chronological browsing.

## Why Testing Didn't Catch The Bug

The queue message body JsProxy bug wasn't caught because:

1. **Local dev uses mocks**: The wrangler local dev environment doesn't perfectly
   replicate production Pyodide behavior. Message bodies in local dev may work
   differently than in production.

2. **Integration tests use Python dicts**: Our test mocks create Python dict
   message bodies, not JsProxy objects.

3. **Unit tests don't test queue handler**: The queue handler was tested for
   presence but not for JsProxy conversion.

4. **No production-like E2E tests**: We need tests that actually deploy to
   Cloudflare and verify real queue processing.

### Lesson Learned

Every place that receives data from JavaScript (D1 results, form data, queue
messages, AI results) MUST convert through `_to_py_safe()` before use.

## Module Structure

### Current Module Layout

```
src/
├── main.py              - Worker entrypoint + core business logic
├── templates.py         - Jinja2 templates (embedded at build); CSS/JS served via Static Assets
├── wrappers.py          - JS ↔ Python boundary converters
├── observability.py     - Wide events + structured logging
├── models.py            - Data models + sanitizer
├── oauth_handler.py     - GitHub OAuth flow handler
├── utils.py             - Utility functions (logging, responses, dates)
├── route_dispatcher.py  - HTTP route matching + dispatch
├── search_query.py      - SQL search query builder
├── admin_context.py     - Admin action context manager
├── config.py            - Constants + env-based config getters
├── content_processor.py - Feed entry content extraction
├── auth.py              - Session cookies + HMAC signing
├── admin.py             - Admin error responses + OPML parsing
├── instance_config.py   - Lite mode detection + config loading
├── xml_sanitizer.py     - XML control character stripping
└── __init__.py
```

### Module Dependency Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               CLOUDFLARE WORKERS                                  │
│                                                                                   │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐                               │
│  │ scheduled()│   │  queue()   │   │  fetch()   │                               │
│  │  (cron)    │   │ (consumer) │   │  (HTTP)    │                               │
│  └─────┬──────┘   └─────┬──────┘   └─────┬──────┘                               │
│        │                │                │                                        │
│        └────────────────┼────────────────┘                                        │
│                         ▼                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                          main.py (entrypoint)                                │  │
│  │                                                                              │  │
│  │  class Default(WorkerEntrypoint):                                            │  │
│  │    - scheduled() → enqueue feeds to FEED_QUEUE                               │  │
│  │    - queue() → process feed messages                                         │  │
│  │    - fetch() → route HTTP requests via RouteDispatcher                       │  │
│  │                                                                              │  │
│  │  Imports from ALL 15 other modules (see arrows below)                        │  │
│  └──────┬────────────────────────────────────────────────────────────────┬──────┘  │
│         │                                                                │         │
│    ┌────┴────────────┬──────────────┬──────────────┬──────────────┐      │         │
│    ▼                 ▼              ▼              ▼              ▼      │         │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌────────────┐ ┌──────────┐ │         │
│  │ admin.py  │ │admin_     │ │oauth_     │ │route_      │ │search_   │ │         │
│  │           │ │context.py │ │handler.py │ │dispatcher  │ │query.py  │ │         │
│  │error resp.│ │action ctx │ │GitHub flow│ │.py         │ │SQL build │ │         │
│  │OPML parse │ │timing     │ │code exch. │ │pattern     │ │phrase/   │ │         │
│  │           │ │audit emit │ │user info  │ │matching    │ │multi-word│ │         │
│  └──┬──┬──┬──┘ └──┬────┬──┘ └─────┬─────┘ └────────────┘ └──────────┘ │         │
│     │  │  │        │    │          │         (no deps)      (no deps)  │         │
│     │  │  │        │    │          │                                    │         │
│    ┌┘  │  │     ┌──┘    │    ┌─────┘   ┌───────────────────────────────┘         │
│    │   │  │     │       │    │         │                                          │
│    ▼   │  ▼     ▼       ▼    ▼         ▼                                          │
│  ┌─────┴────┐ ┌─────────────────┐ ┌──────────┐ ┌──────────────────┐              │
│  │config.py │ │observability.py │ │wrappers  │ │  templates.py    │              │
│  │          │ │                 │ │.py       │ │                  │              │
│  │constants │ │ RequestEvent    │ │SafeEnv   │ │render_template   │              │
│  │get_config│ │ FeedFetchEvent  │ │SafeHeaders│ │TEMPLATE_*        │              │
│  │_value()  │ │ SchedulerEvent  │ │SafeFeed  │ │THEME_LOGOS       │              │
│  │          │ │ AdminActionEvent│ │Info      │ │_EMBEDDED_         │              │
│  │          │ │ Timer           │ │safe_http │ │EmbeddedLoader    │              │
│  │          │ │ emit_event      │ │_fetch    │ │                  │              │
│  └────┬─────┘ └───────┬────────┘ └──────────┘ └──────────────────┘              │
│       │               │           (no local)    (no local deps)                  │
│       │               │                                                          │
│       ▼               ▼                                                          │
│  ┌────────────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │       utils.py         │  │    models.py     │  │  instance_config.py      │  │
│  │                        │  │                  │  │                          │  │
│  │ log_op, log_error      │  │ BleachSanitizer  │  │ is_lite_mode()           │  │
│  │ html/json/feed_response│  │ EntryRow,FeedRow │  │ theme loading            │  │
│  │ format_date, xml_escape│  │ Session          │  │                          │  │
│  │ validate_feed_id       │  │ (no local deps)  │  │ imports: config,         │  │
│  │ (no local deps)        │  │                  │  │          wrappers        │  │
│  └────────────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│                                                                                   │
│  ┌──────────────────────────────┐  ┌──────────────────────────────────────────┐   │
│  │  content_processor.py        │  │  xml_sanitizer.py                        │   │
│  │                              │  │                                          │   │
│  │  EntryContentProcessor       │  │  strip_xml_control_chars()               │   │
│  │  extract content, GUID, date │  │  (no deps - leaf module)                 │   │
│  │                              │  │                                          │   │
│  │  imports: xml_sanitizer  ────┼──┘                                          │   │
│  └──────────────────────────────┘                                             │   │
│                                                                                   │
│  ┌───────────────────────────────────────────────────────────────────────────┐    │
│  │  auth.py                                                                   │    │
│  │                                                                            │    │
│  │  create_signed_cookie, get_session_from_cookies, build_*_header            │    │
│  │  imports: config, utils                                                    │    │
│  └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                   │
│  Dependency summary (local imports only):                                         │
│                                                                                   │
│    main.py ──► admin, admin_context, auth, config, content_processor,             │
│                instance_config, models, oauth_handler, observability,              │
│                route_dispatcher, search_query, templates, utils,                   │
│                wrappers, xml_sanitizer                                             │
│    admin.py ──► config, templates, utils                                          │
│    admin_context.py ──► observability, utils                                      │
│    auth.py ──► config, utils                                                      │
│    config.py ──► utils                                                            │
│    content_processor.py ──► xml_sanitizer                                         │
│    instance_config.py ──► config, wrappers                                        │
│    oauth_handler.py ──► wrappers                                                  │
│    observability.py ──► utils                                                     │
│    models.py, route_dispatcher.py, search_query.py,                               │
│      templates.py, utils.py, wrappers.py, xml_sanitizer.py ──► (none)             │
│                                                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Class Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                  main.py                                      │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    class Default(WorkerEntrypoint)                       │ │
│  │─────────────────────────────────────────────────────────────────────────│ │
│  │ Properties:                                                              │ │
│  │   env: SafeEnv                  # Wrapped environment bindings           │ │
│  │                                                                          │ │
│  │ Trigger Handlers:                                                        │ │
│  │   scheduled(event, env, ctx)    # Cron trigger (hourly)                  │ │
│  │   queue(batch, env, ctx)        # Queue consumer                         │ │
│  │   fetch(request, env, ctx)      # HTTP requests (via RouteDispatcher)    │ │
│  │                                                                          │ │
│  │ Routing:                                                                 │ │
│  │   _create_router()              # Build RouteDispatcher with all routes  │ │
│  │   _dispatch_route()             # Execute matched route handler          │ │
│  │                                                                          │ │
│  │ Feed Processing:                                                         │ │
│  │   _process_single_feed()        # Fetch + parse + store                  │ │
│  │   _sanitize_html()              # Bleach sanitization                    │ │
│  │   _validate_feed_url()          # SSRF protection                        │ │
│  │                                                                          │ │
│  │ Entry Management:                                                        │ │
│  │   _upsert_entry()               # Insert or update entry                 │ │
│  │   _index_entry_for_search()     # Generate embedding + index             │ │
│  │   _apply_retention_policy()     # Delete old entries                     │ │
│  │   _get_recent_entries()         # Query entries for display              │ │
│  │                                                                          │ │
│  │ HTML/Feed Generation:                                                    │ │
│  │   _generate_html()              # Render index template                  │ │
│  │   _generate_atom_feed()         # Atom XML via template                  │ │
│  │   _generate_rss_feed()          # RSS 2.0 XML via template               │ │
│  │   _generate_rss10_feed()        # RSS 1.0 XML via template               │ │
│  │   _export_opml()                # OPML feed list                         │ │
│  │                                                                          │ │
│  │ Search:                                                                  │ │
│  │   _search_entries()             # Semantic + keyword (uses SearchQuery   │ │
│  │                                 #   Builder, SafeVectorize, SafeAI)      │ │
│  │                                                                          │ │
│  │ Admin (delegates to admin.py, admin_context.py):                         │ │
│  │   _handle_admin()               # Route admin requests                   │ │
│  │   _add_feed()                   # Add new feed                           │ │
│  │   _remove_feed()                # Deactivate feed                        │ │
│  │   _import_opml()                # Bulk import (admin.parse_opml_feeds)   │ │
│  │                                                                          │ │
│  │ Auth (delegates to auth.py, oauth_handler.py):                           │ │
│  │   Uses auth.get_session_from_cookies()                                   │ │
│  │   Uses auth.build_session_cookie_header()                                │ │
│  │   Uses auth.build_clear_session_cookie_header()                          │ │
│  │   Uses auth.build_oauth_state_cookie_header()                            │ │
│  │   Uses GitHubOAuthHandler.exchange_code() / .get_user_info()             │ │
│  │                                                                          │ │
│  │ Config (delegates to config.py):                                         │ │
│  │   _get_config_value()           # Env-based config with defaults         │ │
│  │   _get_retention_days()         # Entry retention period                 │ │
│  │   _get_max_entries_per_feed()   # Per-feed entry limit                   │ │
│  │   _get_search_score_threshold() # Semantic search threshold              │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        │ imports
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                                wrappers.py                                    │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         class SafeEnv                                    │ │
│  │─────────────────────────────────────────────────────────────────────────│ │
│  │ Wraps WorkerEnv to provide safe access to bindings:                     │ │
│  │   DB: SafeD1                  # D1 database (auto-converts results)      │ │
│  │   FEED_QUEUE: SafeQueue       # Feed fetch queue (optional)              │ │
│  │   DEAD_LETTER_QUEUE: SafeQueue# Failed job queue (optional)              │ │
│  │   SEARCH_INDEX: SafeVectorize # Semantic search index (optional)         │ │
│  │   AI: SafeAI                  # Embedding generation (optional)          │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  Safe Wrappers:                                                               │
│    SafeD1 / SafeD1Statement        # Auto-convert D1 results to Python      │
│    SafeAI                          # Auto-convert AI outputs to Python       │
│    SafeVectorize                   # Auto-convert search results to Python   │
│    SafeQueue                       # Queue send (outbound, no conversion)    │
│    HttpResponse                    # Typed HTTP response wrapper             │
│                                                                               │
│  Converters:                                                                  │
│    _to_py_safe(obj)                # JsProxy → Python dict/list              │
│    _to_py_list(js_array)           # JsProxy array → Python list             │
│    _to_d1_value(value)             # Python → D1-safe value                  │
│    _is_js_undefined(value)         # Check for JS undefined                  │
│    _safe_str(value)                # Safely stringify JsProxy                │
│    _extract_form_value(form, key)  # Extract from JsProxy FormData          │
│    entry_rows_from_d1(result)      # D1 results → Python dicts              │
│    feed_rows_from_d1(result)       # D1 results → Python dicts              │
│    feed_row_from_js(row)           # Single feed row conversion              │
│    admin_row_from_js(row)          # Single admin row conversion             │
│    audit_rows_from_d1(results)     # Audit log rows conversion              │
│    entry_bind_values(entry)        # Entry → D1 bind params                 │
│    feed_bind_values(feed)          # Feed → D1 bind params                  │
│    safe_http_fetch(url, ...)       # Fetch with JsProxy handling            │
│                                                                               │
│  Data Classes:                                                                │
│    SafeHeaders                     # Typed request header access             │
│    SafeFormData                    # Typed form data access                  │
│    SafeFeedInfo                    # Typed feed metadata                     │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        │ imports
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                                 utils.py                                      │
│                                                                               │
│  Logging:                                                                     │
│    log_op(event_type, **kwargs)       # Structured operational log           │
│    log_error(event_type, exc, ...)    # Structured error log                 │
│    truncate_error(error, max_len)     # Safe error truncation                │
│                                                                               │
│  Validation:                                                                  │
│    validate_feed_id(feed_id) → int    # Validate path parameter              │
│    get_display_author(author, feed)   # Filter email from author             │
│                                                                               │
│  Response Builders:                                                           │
│    html_response(content, max_age)    # HTML with security headers           │
│    json_response(data, status)        # JSON response                        │
│    json_error(message, status)        # Error response                       │
│    redirect_response(location)        # 302 redirect                         │
│    feed_response(content, type)       # Atom/RSS/OPML                        │
│                                                                               │
│  Formatters:                                                                  │
│    xml_escape(text)                   # Escape for XML embedding             │
│    normalize_entry_content(content)   # Remove duplicate headings            │
│    parse_iso_datetime(iso_string)     # Parse to datetime                    │
│    format_datetime(iso_string)        # Format for display                   │
│    format_pub_date(iso_string)        # RFC 2822 date for RSS                │
│    relative_time(iso_string)          # "2 hours ago" format                 │
│    format_date_label(date_str)        # "Today", "Yesterday", etc.           │
└──────────────────────────────────────────────────────────────────────────────┘
```

## File Structure

```
planet_cf/
├── src/                    # Worker source code (16 modules + __init__.py)
├── tests/                  # Unit, integration, and E2E tests
│   ├── unit/               # ~855 tests with mock bindings
│   ├── integration/        # ~86 end-to-end flow tests
│   └── e2e/                # 34 tests against real Cloudflare infrastructure
├── templates/              # Jinja2 HTML/XML templates + canonical CSS/JS sources
├── examples/               # Deployable instance configurations
│   ├── default/            # Default theme instance
│   ├── planet-cloudflare/  # planetcf.com (uses default theme)
│   ├── planet-python/      # Planet Python clone
│   ├── planet-mozilla/     # Planet Mozilla clone
│   └── test-planet/        # E2E test instance
├── scripts/                # Build, deploy, and validation scripts
├── docs/                   # Architecture, performance, and operations docs
├── config/                 # Admin users and instance config templates
├── migrations/             # Database migration SQL files
├── stubs/                  # Type stubs for Cloudflare Workers runtime
├── static/                 # Source static assets (admin.js, favicons)
└── assets/                 # Root instance static files (CSS, JS, favicons)
```

## Deployment

```bash
# Deploy to production
npx wrangler deploy

# Run local dev server
npx wrangler dev

# Run tests
uv run pytest tests/ -v
```

## Bindings

| Binding | Type | Description |
|---------|------|-------------|
| `DB` | D1 Database | SQLite database for feeds, entries, admins |
| `FEED_QUEUE` | Queue | Async feed fetch jobs |
| `DEAD_LETTER_QUEUE` | Queue | Failed jobs after max retries |
| `SEARCH_INDEX` | Vectorize | Semantic search embeddings |
| `AI` | Workers AI | Generate embeddings for search |
