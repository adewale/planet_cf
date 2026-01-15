# Lessons Learned

Hard-won knowledge from building Planet CF on Cloudflare Workers Python.

---

## 1. JsProxy Conversion is Critical

**Problem:** Pyodide (the Python-in-WebAssembly runtime) returns `JsProxy` objects when interacting with JavaScript APIs. These look like Python objects but aren't subscriptable or iterable.

**Symptom:**
```
TypeError: 'pyodide.ffi.JsProxy' object is not subscriptable
```

**Solution:** Convert JsProxy to Python before use:
```python
from pyodide.ffi import to_js
import js

# For passing Python dicts TO JavaScript APIs (Vectorize, Workers AI):
js_data = to_js(python_dict, dict_converter=js.Object.fromEntries)

# For receiving data FROM JavaScript APIs:
def _to_py_safe(obj):
    """Convert JsProxy to Python dict, or return as-is if already Python."""
    if obj is None:
        return None
    if hasattr(obj, 'to_py'):
        return obj.to_py()
    return obj
```

**Where this bites you:**
- `request.form_data()` returns JsProxy FormData, not a Python dict
- `env.AI.run()` results need conversion
- `env.SEARCH_INDEX.query()` results need conversion
- Vectorize `upsert()` needs Python→JS conversion for input

---

## 2. Create a Boundary Layer for JS/Python Types

**Problem:** JsProxy types leak throughout the codebase, requiring conversion checks everywhere. This spreads complexity and creates multiple failure points.

**Anti-pattern:**
```python
# BAD: Checking for JsProxy in business logic
async def process_feed(self, feed_data):
    if hasattr(feed_data, 'to_py'):  # JsProxy check in business logic!
        feed_data = feed_data.to_py()
    # ... more code with more JsProxy checks
```

**Solution:** Create a thin boundary layer at the edge that converts all JS types to Python types immediately:

```python
# GOOD: Boundary layer at the edge
class SafeD1:
    """Boundary wrapper that quarantines JS types from Python core."""

    def __init__(self, db):
        self._db = db

    async def query(self, sql, params):
        result = await self._db.prepare(sql).bind(*params).all()
        # Convert immediately at boundary
        return [_to_py_safe(row) for row in result.results]


class SafeVectorize:
    """Boundary wrapper for Vectorize."""

    async def query(self, vector, options):
        result = await self._index.query(to_js(vector), to_js(options))
        return _to_py_safe(result)  # Convert at boundary
```

**Architecture:**
```
┌─────────────────────────────────────────────────┐
│            JavaScript / Cloudflare APIs          │
│   (D1, Vectorize, Workers AI, Request, etc.)    │
└─────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────┐
│            Boundary Layer (thin wrappers)        │
│   SafeD1, SafeVectorize, _to_py_safe, to_js     │
│   All JsProxy conversion happens HERE ONLY       │
└─────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────┐
│               Python Core Logic                  │
│   Pure Python types: dict, list, str, int       │
│   No JsProxy checks needed - guaranteed clean    │
└─────────────────────────────────────────────────┘
```

**Benefits:**
- Business logic stays pure Python - easier to test with mocks
- Single point of conversion - easier to debug type issues
- Core code doesn't know about Pyodide/JsProxy
- Tests with Python mocks actually reflect production behavior

---

## 3. Mocks Don't Catch JsProxy Issues

**Problem:** Unit tests with Python mocks pass, but production fails because mocks are pure Python while production involves JS interop.

**Symptom:** All tests green, but production returns 500 errors.

**Solution:**
1. Create wrapper classes (SafeAI, SafeVectorize) that handle conversion
2. Add E2E tests that run against real infrastructure (`wrangler dev --remote`)
3. Test the actual JsProxy conversion paths

```python
# tests/e2e/test_search_real.py - runs against real Cloudflare bindings
@pytest.mark.asyncio
async def test_reindex_and_search(self, require_server, admin_session):
    """This catches JsProxy issues that mocks miss."""
    # ... test against http://localhost:8787 with wrangler dev --remote
```

---

## 4. Templates Must Be Embedded (No Filesystem Access)

**Problem:** Cloudflare Workers Python runs in WebAssembly inside V8 isolates. There is **no filesystem** - no `open()`, no `os.path`, no `pathlib` at runtime. This fundamentally changes how you approach file-based patterns.

**What doesn't work:**
```python
# ALL of these fail in Workers - there's no filesystem
from jinja2 import FileSystemLoader
loader = FileSystemLoader('templates/')  # No filesystem!

with open('config.json') as f:  # No filesystem!
    config = json.load(f)

template_dir = Path(__file__).parent / 'templates'  # Path exists but can't read files!
```

**Why this constraint exists:**
- Workers run in V8 isolates, not a traditional OS
- WebAssembly sandbox has no filesystem access
- Each request gets a fresh isolate - no persistent local state
- Only Cloudflare bindings (D1, KV, R2) provide storage

**Solution:** Embed templates as Python strings at **build time**:
```
templates/                  # Source .html files (edit these)
├── index.html
├── search.html
├── style.css
└── admin/
    ├── dashboard.html
    └── login.html

scripts/build_templates.py  # Compiles templates into Python module
src/templates.py            # Generated - contains embedded strings
```

**The build script pattern:**
```python
# scripts/build_templates.py
def build_templates():
    templates = {}
    for path in TEMPLATE_FILES:
        templates[path] = (TEMPLATE_DIR / path).read_text()

    # Generate Python code with embedded strings
    output = f'''
_EMBEDDED_TEMPLATES = {repr(templates)}

class EmbeddedLoader(BaseLoader):
    def get_source(self, environment, template):
        return _EMBEDDED_TEMPLATES[template], template, lambda: True
'''
```

**Workflow:**
```bash
# After editing any template:
python scripts/build_templates.py  # Regenerate src/templates.py
wrangler deploy                    # Deploy the new code
```

**Key insight:** Anything you'd normally load from disk at runtime must be:
1. Embedded in Python code at build time, OR
2. Stored in Cloudflare bindings (KV, R2, D1) and fetched at runtime

---

## 5. Hybrid Search Beats Pure Semantic

**Problem:** Semantic search (Vectorize) finds conceptually similar content but can miss exact keyword matches.

**Symptom:** Searching "context" doesn't find articles containing the word "context" if they're not semantically similar to the query.

**Solution:** Hybrid search combining both approaches:
```python
async def _search_entries(self, request):
    # 1. Semantic search via Vectorize (finds similar concepts)
    semantic_results = await self.env.SEARCH_INDEX.query(embedding, {"topK": 50})

    # 2. Keyword search via D1 LIKE (finds exact matches)
    keyword_results = await self.env.DB.prepare("""
        SELECT * FROM entries
        WHERE title LIKE ? OR content LIKE ?
    """).bind(f"%{query}%", f"%{query}%").all()

    # 3. Combine: semantic first (by score), then keyword-only (by date)
```

---

## 6. D1 LIKE Queries Need Escaping

**Problem:** User input in LIKE patterns can break queries or cause injection.

**Solution:**
```python
# Escape special LIKE characters
escaped = query.replace("%", "\\%").replace("_", "\\_")
pattern = f"%{escaped}%"
result = await db.prepare("SELECT * FROM t WHERE col LIKE ? ESCAPE '\\'").bind(pattern).all()
```

---

## 7. SSRF Protection Must Be Comprehensive

**Problem:** Feed URLs can point to internal resources, cloud metadata endpoints, or localhost.

**Checklist:**
```python
def _is_safe_url(self, url):
    # Block: localhost, 127.x.x.x, 0.0.0.0
    # Block: private IPs (10.x, 172.16-31.x, 192.168.x)
    # Block: link-local (169.254.x.x)
    # Block: IPv6 loopback (::1), link-local (fe80::), ULA (fc00::/fd00::)
    # Block: metadata endpoints:
    #   - 169.254.169.254 (AWS/GCP)
    #   - metadata.google.internal
    #   - metadata.azure.internal  # Don't forget Azure!
```

---

## 8. Feed Dates Can Be Missing or Malformed

**Problem:** RSS/Atom feeds have inconsistent date formats, or omit dates entirely.

**Bad approach:**
```python
# Don't do this - makes undated entries appear "new" forever
published_at = entry.get('published') or datetime.now()
```

**Good approach:**
```python
# Store NULL for missing dates
published_at = None
if entry.get('published_parsed'):
    published_at = datetime(*entry['published_parsed'][:6])
# Let DB use CURRENT_TIMESTAMP only for first_seen, not published_at
```

---

## 9. Stateless Sessions via Signed Cookies

**Problem:** Workers are stateless. No server-side session storage.

**Solution:** HMAC-signed cookies containing session data:
```python
import hmac, hashlib, base64, json

def create_session(data, secret):
    payload = base64.b64encode(json.dumps(data).encode()).decode()
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"

def verify_session(cookie, secret):
    payload, sig = cookie.rsplit('.', 1)
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None  # Invalid signature
    return json.loads(base64.b64decode(payload))
```

---

## 10. Workers AI Embedding Model Choice

**Problem:** Different embedding models have different dimensions and quality.

**Choice:** `@cf/baai/bge-base-en-v1.5` with CLS pooling
- 768 dimensions (must match Vectorize index)
- Good balance of quality and speed
- CLS pooling better than mean pooling for search

```python
result = await env.AI.run(
    "@cf/baai/bge-base-en-v1.5",
    {"text": [content], "pooling": "cls"}  # cls, not mean
)
```

---

## 11. Content Sanitization is Non-Negotiable

**Problem:** Feed content can contain XSS payloads.

**Solution:** Always sanitize HTML before storage:
```python
import nh3  # Safe HTML sanitizer

ALLOWED_TAGS = {"p", "br", "a", "strong", "em", "code", "pre", "blockquote", "ul", "ol", "li", "h1", "h2", "h3"}
ALLOWED_ATTRS = {"a": {"href", "title"}}

def sanitize(html):
    return nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
```

---

## 12. Queue Error Handling

**Problem:** Queue consumers must handle errors gracefully or messages get stuck.

**Pattern:**
```python
async def queue(self, batch, env):
    for msg in batch.messages:
        try:
            await self._process_feed(msg.body["feed_id"])
            msg.ack()
        except Exception as e:
            # Don't ack - let it retry or go to DLQ
            log_op("feed_processing_failed", error=str(e))
            msg.retry()  # or let it auto-retry based on queue config
```

---

## 13. Observability From Day One

**Problem:** Production issues are hard to debug without structured logging.

**Solution:** Structured logging with operation context:
```python
def log_op(operation, **kwargs):
    """Structured log entry for observability."""
    print(json.dumps({
        "op": operation,
        "ts": datetime.utcnow().isoformat(),
        **kwargs
    }))

# Usage
log_op("feed_fetch", feed_id=123, status=200, entries=15)
log_op("search_query", query="cloudflare", results=8, latency_ms=45)
```

Enable in wrangler.jsonc:
```json
{
  "observability": {
    "enabled": true,
    "head_sampling_rate": 1.0
  }
}
```

---

## 14. Test Cleanup is Essential for E2E Tests

**Problem:** E2E tests that create real data can pollute the database.

**Solution:** Always use try/finally for cleanup:
```python
async def test_full_flow(self):
    created_id = None
    try:
        # Create test data
        created_id = await create_feed(url)
        # Test assertions...
    finally:
        # ALWAYS clean up
        if created_id:
            await delete_feed(created_id)
```

---

## 15. Search Ranking: Exact Matches First

**Problem:** Users expect searching for a literal phrase like "context is the work" to show an article with that exact title as the first result. Pure semantic search may rank conceptually similar content higher than exact matches.

**Symptom:** Searching for a title doesn't return that article first, or at all.

**Solution:** Three-tier ranking in hybrid search:
```python
# Priority 1: Exact title matches (score 1.0)
# Priority 2: Semantic matches (by similarity score)
# Priority 3: Keyword-only matches (by date)

for entry in keyword_entries:
    title_lower = (entry.get("title") or "").lower().strip()
    query_lower = query.lower().strip()

    if query_lower == title_lower:
        # Exact title match - highest priority
        results.append({**entry, "score": 1.0, "match_type": "exact_title"})
    elif query_lower in title_lower:
        # Partial title match - still high priority
        results.append({**entry, "score": 0.95, "match_type": "title_match"})

# Then add semantic matches (by score, excluding already-added)
# Then add remaining keyword matches (by date)
```

**Why this matters:** Users searching for specific content expect literal matches to rank first. Semantic similarity is useful for discovery but shouldn't override explicit matches.

---

## 16. Search Accuracy Requires Real Infrastructure Tests

**Problem:** Mock-based tests pass but search doesn't work correctly in production.

**Why mocks fail:**
```python
# MockVectorize returns ALL vectors for ANY query - no real similarity
# MockAI returns [0.1, 0.1, ...] - not real semantic embeddings
# MockD1 simulates LIKE but may differ from real D1 edge cases
```

**Solution:** Two-tier testing strategy:

1. **Mock tests** for logic verification (fast, no network):
   - Search ranking algorithm
   - Title matching (bidirectional)
   - Error handling

2. **Real infrastructure tests** for integration (requires `wrangler dev --remote`):
   - D1 LIKE query behavior
   - Vectorize semantic similarity
   - Workers AI embedding quality

```python
# tests/e2e/test_search_accuracy_real.py
@pytest.mark.skipif(not os.environ.get("RUN_E2E_TESTS"))
async def test_semantic_search_returns_results(client):
    """Verifies real Vectorize similarity works."""
    response = await client.get("/search", params={"q": "edge computing"})
    assert response.status_code == 200
```

**Key insight:** Bidirectional title matching is critical:
```python
# Both should match the title "What the day-to-day looks like":
"what the day-to-day looks like"      # Exact match
"what the day-to-day looks like now"  # Query contains title
```

---

## Quick Reference: Common Gotchas

| Issue | Solution |
|-------|----------|
| JsProxy not subscriptable | Use `to_js()` / `.to_py()` |
| JsProxy checks everywhere | Create boundary layer at edge |
| No filesystem access | Embed files at build time, not runtime |
| Tests pass, prod fails | Add E2E tests with real infra |
| Templates not loading | Embed in Python, use build script |
| Search misses keywords | Add hybrid search (semantic + LIKE) |
| XSS in feed content | Sanitize with nh3 before storage |
| Sessions in Workers | HMAC-signed cookies |
| Missing feed dates | Store NULL, don't fake current time |
| SSRF via feed URLs | Block private IPs + metadata endpoints |
| Search misses exact matches | Rank exact title matches first (score 1.0) |
| Mock tests pass, prod fails | Add E2E tests against real infrastructure |
| Query longer than title | Use bidirectional matching (title in query) |
