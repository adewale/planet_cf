# Planet CF Architecture

A feed aggregator built on Cloudflare Workers (Python) with D1, Queues, and Vectorize.

## System Overview

```
                                    ┌─────────────────────────────────────┐
                                    │         Cloudflare Edge             │
                                    │  (Global CDN, 1-hour edge cache)    │
                                    └─────────────────────────────────────┘
                                                     │
                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Planet CF Worker                                    │
│                         (Python via Pyodide runtime)                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │    fetch()   │    │   queue()    │    │ scheduled()  │    │   Admin UI   │  │
│  │  HTTP Handler│    │Queue Consumer│    │Cron Scheduler│    │  Dashboard   │  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                   │                   │                   │           │
│         └───────────────────┴───────────────────┴───────────────────┘           │
│                                      │                                           │
└──────────────────────────────────────┼───────────────────────────────────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         │                             │                             │
         ▼                             ▼                             ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│   D1 Database   │          │   FEED_QUEUE    │          │   Vectorize     │
│                 │          │   (Cloudflare   │          │   (Semantic     │
│  - feeds        │          │    Queues)      │          │    Search)      │
│  - entries      │          │                 │          │                 │
│  - admins       │          └─────────────────┘          └─────────────────┘
│  - audit_log    │
└─────────────────┘
```

## Request Flow

### Public Pages (/, /feed.atom, /feed.rss)

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
│  1. Query D1 for entries (last 30 days, max 100/feed)           │
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
    is_active INTEGER DEFAULT 1,
    consecutive_failures INTEGER DEFAULT 0,
    last_fetch_at TEXT,
    last_success_at TEXT,
    fetch_error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Entries table
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    guid TEXT NOT NULL,
    url TEXT,
    title TEXT,
    author TEXT,
    summary TEXT,
    content TEXT,
    published_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(feed_id, guid)
);

-- Admins table (GitHub OAuth)
CREATE TABLE admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_username TEXT UNIQUE NOT NULL,
    github_id INTEGER,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
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

**Boundary Layer Components** (defined in `main.py`):

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

Payload contains: `{github_username, github_id, exp}`

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
style-src 'self' 'unsafe-inline';
img-src https: data:;
frame-ancestors 'none'
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

### Static File Serving

Static files are served from `/static/*` routes:
- `/static/style.css` - Main stylesheet
- `/static/admin.js` - Admin dashboard JavaScript

These are embedded in the Python code (not separate files) for Workers compatibility.
In production, consider using Cloudflare Pages or R2 for static assets.

## Security Measures

### HTTP Security Headers

All HTML responses include comprehensive security headers:

```
Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; img-src https: data:; frame-ancestors 'none'
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

## File Structure

```
planet_cf/
├── src/
│   ├── main.py          # Main worker (fetch, queue, scheduled handlers)
│   ├── templates.py     # Jinja2 templates (embedded for Workers)
│   ├── models.py        # Pydantic models for observability
│   ├── observability.py # Structured logging and event emission
│   └── __init__.py
├── tests/
│   ├── unit/            # Unit tests (pure Python, no external deps)
│   ├── integration/     # Integration tests (require wrangler dev)
│   ├── e2e/             # End-to-end tests (production-like)
│   └── mocks/           # Mock implementations for testing
├── wrangler.toml        # Cloudflare Workers configuration
├── pyproject.toml       # Python project configuration
└── ARCHITECTURE.md      # This file
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
