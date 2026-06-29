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

**Solution:** Always sanitize HTML before storage using bleach. See `ALLOWED_TAGS` and `ALLOWED_ATTRS` in `src/models.py` for the current allowlists.

```python
import bleach  # Safe HTML sanitizer

def sanitize(html):
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
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

**Solution:** Keyword matches rank in tiers, and **all** keyword tiers rank above semantic matches. Semantic results come last, used only to surface conceptually-related entries that no keyword tier already captured. This matches the code in `_search_entries` (`src/main.py`) and SPEC §13.4.

```python
# FIRST TIER  — keyword matches with title relevance:
#   exact title match        -> score 1.0   match_type="exact_title"
#   title contained in query -> score 0.98  match_type="title_in_query"
#   query contained in title -> score 0.95  match_type="query_in_title"
# SECOND TIER — remaining keyword matches (content/partial):
#   keyword content match    -> score 0.80  match_type="keyword_content"
# THIRD TIER  — semantic matches not already added, by similarity score:
#   semantic match           -> score = vectorize similarity, match_type="semantic"
```

Order of assembly (highest first): exact_title → title_in_query → query_in_title → keyword_content → semantic. The code comment states the rule directly: *"Keyword matches always rank above semantic matches."*

**Why this matters:** Users searching for specific content expect literal matches to rank first. Semantic similarity is useful for discovery but never outranks an explicit keyword/title match.

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

## 17. Pyodide FFI Type-Compatibility Matrix

**Problem:** Python and JavaScript have different type systems. When Python values cross the Pyodide FFI boundary into JavaScript (e.g., D1 `.bind()` params, Queue `.send()`, Vectorize `.upsert()`), some types convert cleanly while others cause subtle, hard-to-debug failures.

**The critical gotchas:**

### Python → JavaScript (Outbound)

| Python Type | Becomes in JS | D1 `.bind()` | Queue `.send()` | Notes |
|-------------|---------------|:------------:|:---------------:|-------|
| `str` | `string` | OK | OK | |
| `int` | `number` | OK | OK | |
| `float` | `number` | OK | OK | |
| `bool` | `boolean` | OK | OK | |
| `None` | `undefined` | **BREAKS** | OK (as `undefined`) | D1 rejects `undefined`; use `JS_NULL` |
| `dict` | `Map` | N/A | **Fails silently** | Use `to_js(d, dict_converter=Object.fromEntries)` |
| `list` | `Array` | N/A | OK | Via `to_js()` |
| `bytes` | `PyProxy` | **BREAKS** | **BREAKS** | Must decode to `str` first |
| `datetime` | `PyProxy` | **BREAKS** | **BREAKS** | Must convert to ISO string first |

### JavaScript → Python (Inbound)

| JS Type | Arrives as in Python | `dict["key"]` | `.to_py()` | Notes |
|---------|---------------------|:-------------:|:----------:|-------|
| `Object` | `JsProxy` | **TypeError** | `dict` | Not subscriptable — must call `.to_py()` |
| `Array` | `JsProxy` | **TypeError** | `list` | Not iterable as Python list |
| `null` | `JsNull` | N/A | N/A | **NOT** Python `None`; `type(x).__name__ == "JsNull"` |
| `undefined` | `JsUndefined` | N/A | N/A | **NOT** Python `None`; has `.typeof == "undefined"` |
| `string` | `str` | N/A | N/A | Passes through cleanly |
| `number` | `int`/`float` | N/A | N/A | Passes through cleanly |
| `boolean` | `bool` | N/A | N/A | Passes through cleanly |
| `ArrayBuffer` | `JsProxy` | N/A | `bytes` | Via `.to_bytes()` |

### The JsNull Trap

This is the most insidious gotcha. JavaScript `null` does **not** become Python `None`:

```python
# In Pyodide:
result = await db.prepare("SELECT nullable_col FROM t").first()
value = result.nullable_col  # This is JsNull, NOT None

value is None          # False!
isinstance(value, type(None))  # False!
bool(value)            # False (it IS falsy)
type(value).__name__   # "JsNull"
```

**Solution:** The boundary layer's `_is_js_undefined()` checks `type(x).__name__` for both `"JsUndefined"` and `"JsNull"`, and `_to_py_safe()` converts both to Python `None`.

### The None→undefined Trap

Python `None` becomes JavaScript `undefined`, **not** `null`. D1 rejects `undefined`:

```python
# ❌ BREAKS: D1_TYPE_ERROR: Type 'undefined' not supported
await db.prepare("INSERT INTO t (a) VALUES (?)").bind(None).run()

# ✅ WORKS: SafeD1Statement.bind() auto-converts via _to_d1_value()
JS_NULL = js.JSON.parse("null")  # Proper JS null
await safe_db.prepare("INSERT INTO t (a) VALUES (?)").bind(None).run()
```

### How Planet CF Handles Each Case

| Boundary | Direction | Conversion Point | Handler |
|----------|-----------|-----------------|---------|
| D1 reads | JS→Python | `SafeD1Statement.first()` / `.all()` | `_to_py_safe()` + row factories |
| D1 writes | Python→JS | `SafeD1Statement.bind()` | `_to_d1_value()` (None→`JS_NULL`) |
| Queue reads | JS→Python | `queue()` handler | `_to_py_safe(message.body)` |
| Queue writes | Python→JS | `SafeQueue.send()` | Pass-through (simple dicts cross OK) |
| AI results | JS→Python | `SafeAI.run()` | `_to_py_safe()` |
| AI inputs | Python→JS | `SafeAI.run()` | `_to_js_value()` |
| Vectorize results | JS→Python | `SafeVectorize.query()` | `_to_py_safe()` |
| Vectorize inputs | Python→JS | `SafeVectorize.upsert()` | `_to_js_value()` |
| HTTP headers | JS→Python | `SafeHeaders` | `_safe_str()` |
| Form data | JS→Python | `SafeFormData` | `_extract_form_value()` |

---

## 18. Visual Fidelity: Converting Planet/Venus Sites

When converting an existing Planet or Venus website to Planet CF, achieving 100% visual fidelity requires systematic attention to detail.

### The Problem

We initially achieved only 67-79% pixel match when comparing our converted sites to originals. The gap was caused by:
- Using recreated SVG logos instead of original GIF/PNG files
- Substituting solid colors for background images
- Different template text ("Last updated:" vs "Last update:")
- Wrong sidebar positions (right instead of left)
- Missing related-sites sections

### The Solution: Systematic Conversion

**Use the converter tool:**
```bash
pip install requests beautifulsoup4
python scripts/convert_planet.py https://planetpython.org/ --name planet-python
```

**Key principles:**

1. **Reuse original assets exactly** - Don't recreate logos, download the originals
2. **Serve assets at original paths** - `/static/images/python-logo.gif` not `/static/logo.svg`
3. **Use original CSS** - Download and adapt, don't rewrite
4. **Match template text exactly** - "Last update:" not "Last updated:"
5. **Verify with visual comparison** - Screenshot and pixel-diff

### Checklist for 100% Fidelity

- [ ] HTTP 200 on main page
- [ ] HTTP 200 on all static assets (logo, CSS, images)
- [ ] Logo is EXACT same file (not recreated)
- [ ] Background images served (header-bg.jpg, footer.jpg)
- [ ] CSS colors match exactly
- [ ] Fonts match (same font-family, size, weight)
- [ ] Sidebar position matches (left/right/none)
- [ ] Related sites sections present
- [ ] Template text matches ("Last update:", date format)
- [ ] Visual comparison of structural elements > 95%

### Tools Created

| Tool | Purpose |
|------|---------|
| `scripts/convert_planet.py` | Converts Planet/Venus sites to Planet CF |
| `scripts/visual_compare.py` | Screenshot-based visual comparison |

### Quick Reference: Visual Fidelity Gotchas

| Issue | Solution |
|-------|----------|
| Low pixel match (67-79%) | Dynamic content differs - compare structure only |
| Logo looks different | Use original file, don't recreate |
| Missing backgrounds | Download and serve original images |
| Wrong sidebar position | Check CSS for `order: -1` (left) or `order: 1` (right) |
| Template text differs | Extract exact text from original |
| THEME_LOGOS KeyError | Must include `url` key in config |
| HTTP 500 after deploy | Verify assets actually load, check error logs |

---

## 19. Deterministic E2E Tests: Synchronous Endpoints Beat Sleep

**Problem:** E2E tests that trigger asynchronous work (queue processing, reindexing) must wait for that work to complete before asserting. The common pattern is `asyncio.sleep()`:

```python
# ❌ BAD: Flaky and slow
await client.post("/admin/regenerate", cookies=session)  # Enqueues feeds
await asyncio.sleep(5)  # Hope it's done? Maybe not under load.
response = await client.get("/")
assert "expected entry" in response.text
```

**Why this fails:**
- **Flaky:** 5 seconds is enough on your machine, not enough on CI, too much on fast machines
- **Slow:** 13+ seconds of dead wait across 5 E2E test methods
- **Opaque:** When a test fails, you can't tell if the assertion is wrong or the sleep was too short

**Solution:** Add a synchronous "process-now" endpoint that runs the pipeline inline and returns the result:

```python
# ✅ GOOD: Deterministic and fast
response = await client.post(
    f"/admin/feeds/{feed_id}/fetch-now",
    cookies=session,
)
result = response.json()
assert result["ok"] is True
assert result["entries_added"] > 0
# Now assert on homepage — no sleep needed
```

**Implementation:** `POST /admin/feeds/{id}/fetch-now` runs `_process_single_feed` synchronously in the request handler, bypassing the queue entirely. The response includes `entries_added`, `entries_found`, and `status` — errors surface immediately instead of silently retrying in the queue.

**Key insight:** The endpoint doesn't replace the queue for production use. It exists alongside it, specifically for testing and admin debugging. The queue handles batching, retries, and timeouts at scale; fetch-now handles "I need to know the result right now."

**Caveat:** fetch-now only eliminates sleeps for *feed processing*. Vectorize indexing propagation still requires waiting — that's an external system with no synchronous API. The 3 remaining `asyncio.sleep(2)` calls in the E2E suite wait for Vectorize, not feed fetching.

---

## 20. Two-Tier FFI Testing: CPython Tests + Pyodide Fakes

**Problem:** Unit tests using Python mocks verify business logic but completely miss FFI boundary bugs. JsNull, JsUndefined, and JsProxy types don't exist in CPython, so mock-based tests pass even when production code crashes on these types.

**Symptom:** `_to_py_list()` had no guard for JsNull/JsUndefined input. The `None` check (`if js_array is None: return []`) didn't catch them because JsNull is **not** Python None. The function crashed with `TypeError: 'JsNull' object is not iterable` in production but all mock tests passed.

**Solution:** Adopt a two-tier test structure (pattern from [tasche](https://github.com/adewale/tasche)):

1. **`test_safe_wrappers.py`** — CPython tests with Python mocks. Fast, test logic.
2. **`test_wrappers_ffi.py`** — Pyodide fake tests. Monkeypatch `HAS_PYODIDE=True` and inject fake JS types.

**The fake JS types:**
```python
class FakeJsProxy:
    """Simulates pyodide.ffi.JsProxy."""
    def __init__(self, data):
        self._data = data
    def to_py(self):
        return self._data

class JsNull:
    """JS null sentinel — NOT a JsProxy subclass."""
    def __bool__(self):
        return False
JsNull.__name__ = "JsNull"  # Must match type(x).__name__ check

class _Undefined:
    """JS undefined singleton."""
    pass
_Undefined.__name__ = "JsUndefined"
```

**The `pyodide_fakes` fixture:**
```python
@pytest.fixture
def pyodide_fakes(monkeypatch):
    monkeypatch.setattr(W, "HAS_PYODIDE", True)
    monkeypatch.setattr(W, "js", FakeJsModule())
    monkeypatch.setattr(W, "to_js", fake_to_js)
    monkeypatch.setattr(W, "JS_NULL", JsNull())
```

**What this caught immediately:** The `_to_py_list` bug — JsNull input bypassed the `is None` check and fell through to iteration, crashing. The fix was a two-line guard:

```python
def _to_py_list(js_array):
    if js_array is None:
        return []
    # This line was missing — caught by FFI tests:
    if _is_js_undefined(js_array):
        return []
```

**Key insight:** Every function that checks `if x is None` at the JS/Python boundary is potentially broken because JsNull `is not None`. FFI fake tests systematically verify every such boundary. The effort to write fake JS types pays for itself by catching bugs that no amount of mock testing will find.

---

## 21. `is None` is Never Enough at the FFI Boundary

**Problem:** In CPython, `None` is the only "null-like" value, so `if x is None` catches all null cases. At the Pyodide FFI boundary, there are **three** distinct null-like values:

| Value | `is None` | `bool()` | `type().__name__` |
|-------|:---------:|:--------:|:------------------:|
| Python `None` | `True` | `False` | `NoneType` |
| JS `null` (JsNull) | **`False`** | `False` | `JsNull` |
| JS `undefined` (JsUndefined) | **`False`** | `False` | `JsUndefined` |

**Where this bites you:**
```python
# ❌ Misses JsNull and JsUndefined
if result is None:
    return default_value

# ❌ Also misses them (same check, different syntax)
if result is not None:
    process(result)  # Crashes on JsNull
```

**Solution:** Use the boundary layer's `_is_js_undefined()` which checks `type(x).__name__` against a set of known JS null types:

```python
# ✅ Catches all three null-like values
if value is None or _is_js_undefined(value):
    return default_value
```

**Rule of thumb:** Any function in `wrappers.py` that has `if x is None` should also check `_is_js_undefined(x)`. When writing new boundary code, always ask: "What happens when this receives JsNull instead of None?"

---

## 22. Pyodide Doesn't Have All CPython APIs

**Problem:** CPython 3.13.3 added `ET.XMLParser(forbid_dtd=True)` for XXE protection. Pyodide bundles an older Python — calling `forbid_dtd=True` crashes with `TypeError: XMLParser() got an unexpected keyword argument 'forbid_dtd'`.

**Symptom:** OPML import returns 500 in production but passes all unit tests (which run on CPython).

**Why unit tests can't catch this:** Unit tests run on the system CPython (3.13+) where `forbid_dtd` exists. The bug only manifests in the Pyodide runtime used by Cloudflare Workers.

**Solution:** Use a portable XXE mitigation that does not depend on the parser flag. The robust form is to **reject** any document containing a DTD/entity declaration before parsing, rather than relying on `forbid_dtd` or trying to surgically strip the declaration (a `<!DOCTYPE[^>]*>` regex breaks on internal subsets that contain `>`):

```python
import xml.etree.ElementTree as ET

# ✅ Works in both CPython and Pyodide: refuse DTDs outright
if "<!DOCTYPE" in opml_content or "<!ENTITY" in opml_content:
    raise ValueError("DTD/entity declarations are not allowed in OPML")
root = ET.fromstring(opml_content)  # stdlib ET resolves no external entities anyway

# ❌ Fails in Pyodide
parser = ET.XMLParser(forbid_dtd=True)  # CPython 3.13.3+ only
root = ET.fromstring(opml_content, parser=parser)
```

**Key insight:** Any stdlib API added after Python 3.12 may not exist in Pyodide. When using newer Python features, always check Pyodide compatibility — and rely on E2E tests against deployed Workers to catch these, since unit tests on CPython are structurally blind to them.

---

## 23. Optional Bindings Must Be Guarded, Not Assumed

**Problem:** `planet-python` runs in lite mode — no AI or Vectorize bindings. The code called `self.env.AI.run()` without checking if `AI` was `None`, causing `AttributeError` on every queue message. The error was caught by a `try/except` and logged, so all 1267 unit tests passed while production logged errors on every feed fetch.

**Symptom:**
```
AttributeError: 'NoneType' object has no attribute 'run'
```
Logged as `search_index_skipped` on every queue-processed entry, but the entry was still inserted — so the bug was invisible to tests that only checked for successful inserts.

**Solution:** Guard bindings at three levels:

```python
# 1. Startup validation: warn on mode/binding mismatch (once per isolate)
def _validate_config(self):
    is_lite = check_lite_mode(self.env)
    has_ai = getattr(self.env, "AI", None) is not None
    has_search = getattr(self.env, "SEARCH_INDEX", None) is not None
    if not is_lite and (not has_ai or not has_search):
        log_op("config_warning", severity="warning",
               message=f"Missing bindings: {missing}. Set INSTANCE_MODE=lite.")

# 2. Loop-level guard: skip indexing entirely when bindings absent
has_search_bindings = getattr(self.env, "AI", None) and getattr(self.env, "SEARCH_INDEX", None)
if entry_id and title and has_search_bindings:
    indexing_stats = await self._index_entry_for_search(...)

# 3. Function-level guard: early return if called without bindings
async def _index_entry_for_search(self, ...):
    if not getattr(self.env, "AI", None) or not getattr(self.env, "SEARCH_INDEX", None):
        return {"success": False, "error_type": "NotConfigured", ...}
```

**Key insight:** Tests passing doesn't mean the code is correct. If an error is caught and swallowed, the bug is invisible. Tests must assert *absence of errors*, not just *absence of crashes*. The integration test that would have caught this:

```python
async def test_fetcher_no_ai_binding_inserts_entry_without_error():
    """Verify no error-level logs when processing feeds without AI binding."""
    # ... process feed with AI=None ...
    # Assert: no ERROR-level log records emitted
```

---

## 24. Cap Feed Entry Processing to Prevent CPU Exhaustion

**Problem:** Some feeds are enormous — `pythonbytes.fm` has 474 entries in a 1.4MB RSS file. Processing all 474 (D1 upsert per entry + indexing attempt per entry) exceeds the Workers 60-second CPU limit. This causes cascading Pyodide runtime crashes:

1. `exceededCpu` — CPU limit hit
2. `RuntimeError: table index is out of bounds` — Wasm crash during cleanup
3. `NoGilError: Attempted to use PyProxy when Python GIL not held` — Pyodide state corruption
4. `TypeError: There is no 'Default' class defined` — Module can't load after crash
5. `Recursive call to fatal_error` — Death spiral

Since queue batches share one CPU budget (e.g., 5 messages × 60s total), one expensive feed starves the entire batch.

**Solution:** Cap entries processed per feed to the retention limit:

```python
max_entries = self._get_max_entries_per_feed()  # e.g., 100
if len(entries_list) > max_entries:
    entries_list = entries_list[:max_entries]
```

**Why this is correct:** The retention policy deletes entries beyond the limit anyway. Processing 474 entries when you'll only keep 100 is pure waste.

**Also:** Skip indexing calls entirely when bindings are absent — don't make 130 function calls that each return `NotConfigured` immediately:

```python
# ❌ 130 no-op function calls per feed in lite mode
for entry in entries:
    await self._index_entry_for_search(entry_id, ...)  # Returns NotConfigured

# ✅ Check once before the loop
has_search_bindings = getattr(self.env, "AI", None) and getattr(self.env, "SEARCH_INDEX", None)
for entry in entries:
    if has_search_bindings:
        await self._index_entry_for_search(entry_id, ...)
```

---

## 25. Cloudflare Workers Observability: Log Level Classification

**Problem:** Every log event showed `$metadata.level: "error"` in the Cloudflare dashboard — even successful feed fetches and routine 304 responses. This made the error signal useless.

**Root causes (multiple, compounding):**

1. **`logging.StreamHandler()` defaults to `sys.stderr`** — Cloudflare Workers classifies stderr output as error level. All `logger.info()` calls went to stderr, poisoning every invocation.

2. **`$metadata.level` is per-invocation, not per-log-line** — Queue batches process 5 messages in one invocation. If one feed fails (404, timeout), the entire invocation — including successful feeds — is tagged `level: "error"`.

3. **`logger.error()` in expected failure paths** — Transient D1 errors during the per-request database init check called `log_error()` (which uses `logger.error()`), elevating every invocation that hit a cold start.

**Solutions:**

```python
# Fix 1: Split stdout (info) and stderr (error) handlers
_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.addFilter(lambda r: r.levelno < logging.ERROR)
logger.addHandler(_stdout_handler)

_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setLevel(logging.ERROR)
logger.addHandler(_stderr_handler)

# Fix 2: Don't use logger.error() for recoverable/expected failures
# Transient D1 errors, feed 404s, etc. should use logger.info()
log_op("database_auto_init_error", error_type=type(e).__name__, error=str(e))
# NOT: log_error("database_auto_init_error", e)  # This uses logger.error()

# Fix 3: Use "severity" not "level" in JSON fields
# Cloudflare may parse JSON content and use "level" field for classification
log_op("config_warning", severity="warning", ...)  # Not level="warning"
```

**Key insight:** Reserve `logger.error()` (stderr) for truly unexpected failures where you want the invocation flagged in the dashboard. Everything else — including feed 404s, timeouts, validation errors — should use `logger.info()` (stdout) with error context in the JSON fields. The structured JSON fields (`error_type`, `error_message`, `outcome`) are searchable without polluting the invocation-level severity.

---

## 26. Stateless Execution: Per-Isolate State is Unreliable

**Problem:** Class variables like `_db_initialized = None` and `_config_validated = False` are intended to cache per-isolate state so expensive checks only run once. In Workers' stateless execution model, each request gets a new instance — these variables reset to their defaults every time.

**Consequences:**
- `_ensure_database_initialized()` runs a D1 query on every request
- `_validate_config()` runs on every request
- Logging "already initialized" on every request creates noise

**Solutions:**

1. **Make per-request checks cheap** — The DB init check (`SELECT name FROM sqlite_master`) is fast but still a D1 round-trip. Accept the cost; don't try to cache what can't be cached.

2. **Don't log routine per-request checks** — Remove the `already_initialized` log since it fires on every request with zero signal.

3. **Keep logging for genuine first-time events** — `database_auto_init status=completed` (actual schema creation) is worth logging; `status=already_initialized` is not.

4. **Downgrade error handling for per-request code** — If a per-request check fails transiently (cold start D1 error), log at info level, not error level. Otherwise transient failures poison the entire invocation.

```python
# ❌ Every transient D1 error elevates the whole invocation to error
except Exception as e:
    log_error("database_auto_init_error", e)  # logger.error()

# ✅ Transient failures logged at info level
except Exception as e:
    log_op("database_auto_init_error",
           error_type=type(e).__name__, error=truncate_error(e))
```

---

## 27. Don't Hardcode Instance-Specific Logic in Shared Code

**Problem:** To make `planetcloudflare.dev` redirect to `www.planetcloudflare.dev`, we initially added a hostname check directly in `src/main.py`:

```python
# ❌ Instance-specific logic in shared codebase
if hostname == "planetcloudflare.dev":
    return Response.redirect(target, 301)
```

This meant every deployed instance (planet-python, planet-mozilla, etc.) carried a redirect rule that didn't apply to them.

**Solution:** Use Cloudflare's infrastructure layer instead:

1. **DNS:** Add a proxied A record for the apex domain → `192.0.2.1`
2. **Redirect Rules** (dashboard): `hostname eq "planetcloudflare.dev"` → 301 to `www.planetcloudflare.dev`

**Why Redirect Rules over other options:**

| Option | Fit |
|--------|-----|
| **Redirect Rules** | Best — free, runs at edge before Worker, no cold start |
| Bulk Redirects | Overkill for one domain |
| Page Rules | Deprecated |
| CNAME flattening | Not a redirect — just DNS resolution |
| Separate Worker | Unnecessary overhead |

**Key insight:** Routing and redirect logic belongs in the infrastructure layer (DNS, Cloudflare Rules, Terraform), not in application code. Application code should handle application concerns; the platform handles traffic routing.

---

## 28. Pyodide Typed Arrays → memoryview: The Complete Picture

**Problem:** Every JavaScript typed array — `Float32Array`, `Uint8Array`, `Int32Array`, etc. — becomes a Python `memoryview` when `.to_py()` is called. `memoryview` is truthy, has `len()`, and is iterable, but it is **not** a `list` and behaves differently when passed back to JavaScript via `to_js()`.

**The complete conversion table (from Pyodide's `buffer_datatype_map`):**

| JavaScript Type | `.to_py()` returns | memoryview `.format` | Cloudflare binding |
|---|---|---|---|
| `Float32Array` | `memoryview` | `'f'` (float) | Workers AI embeddings (possible, not documented) |
| `Float64Array` | `memoryview` | `'d'` (double) | — |
| `Int8Array` | `memoryview` | `'b'` (signed char) | — |
| `Int16Array` | `memoryview` | `'h'` (signed short) | — |
| `Int32Array` | `memoryview` | `'i'` (signed int) | — |
| `Uint8Array` | `memoryview` | `'B'` (unsigned char) | R2 `.arrayBuffer()`, KV `arrayBuffer` type |
| `Uint16Array` | `memoryview` | `'H'` (unsigned short) | — |
| `Uint32Array` | `memoryview` | `'I'` (unsigned int) | — |
| `ArrayBuffer` | `memoryview` | `'B'` (unsigned char) | R2 `.arrayBuffer()`, KV `arrayBuffer` type |
| `DataView` | `memoryview` | `'B'` (unsigned char) | — |

**What does NOT convert via `.to_py()`:**

| JavaScript Type | Behavior | Handling |
|---|---|---|
| `Blob` | Stays as JsProxy | Call `.arrayBuffer()` first (async), then `.to_py()` |
| `ReadableStream` | Stays as JsProxy | Consume via JS stream APIs |
| `SharedArrayBuffer` | Not available in Workers | Requires cross-origin isolation |
| `File` | Stays as JsProxy | Call `.text()` (async) or `.arrayBuffer()` |

**The bug this caused:** Workers AI returned embedding vectors that ended up as `memoryview` in Python. Our `_to_py_safe()` function didn't recognize `memoryview` and fell through to its `str()` fallback, mangling 768 floats into `"<memory at 0x7f...>"`. This passed our Python-side `len()` and truthiness checks but produced 0 dimensions when Vectorize received it via `to_js()`.

**Solution in `_to_py_safe()`:**
```python
# Handle memoryview/bytearray (from Pyodide typed array .to_py())
if isinstance(value, (memoryview, bytearray)):
    return list(value)

# bytes should be preserved, not converted to list
if isinstance(value, bytes):
    return value
```

**Where this matters in Planet CF:**
- Any future R2 or KV integration reading binary data (`.arrayBuffer()` returns typed arrays)
- Workers AI embeddings are NOT Float32Array — they are plain `Array` (confirmed by E2E test)
- The memoryview handling is defensive and correct regardless

**Key insight:** Don't just handle the types you expect — handle every type the runtime *could* produce. `_to_py_safe()` is the last line of defense before business logic; it must never fall through to `str()` for any structured data type.

---

## 29. `to_js()` Without `dict_converter` Produces Maps, Not Objects

**Problem:** This was the actual root cause of the 0-dimension Vectorize upsert bug. Pyodide's `to_js()` converts Python dicts to JS `Map` objects by default. Vectorize expects plain JS `Object`s with property access (`.id`, `.values`, `.metadata`).

When upserting a list of vector dicts:
```python
vectors = [{"id": "123", "values": [0.1, ...], "metadata": {"title": "..."}}]
js_vectors = to_js(vectors)  # Inner dicts become Maps!
await vectorize.upsert(js_vectors)  # Vectorize reads .values → undefined → 0 dimensions
```

**How we found it:** After weeks of wrong theories (memoryview, Float32Array, transient AI degradation), we added instrumentation to log the JS-side constructor name right before the Vectorize call. We also built a reproduction Worker (`6-vectorize-map-vs-object` in python-workers-issues) that demonstrates the bug directly.

The data showed:
- `js_constructor: "Object"` + `js_values.length: 768` = success (with fix)
- No new `search_index_skipped` errors after deploying the fix
- The E2E type inspection (issue 5) proved embeddings are plain `Array`, not `Float32Array`

**Why our earlier theories were wrong:**
- **memoryview theory:** Workers AI returns `Array` of numbers, not `Float32Array`. `.to_py()` produces `list[float]`, not `memoryview`. Confirmed by deploying a type-inspection Worker.
- **transient AI degradation theory:** The AI was returning correct 768-dim vectors. The vector survived Python intact. The corruption happened in `to_js()` on the way back to JS.
- We spent time on these theories because we didn't have instrumentation at the boundary. We could see the Python-side input (correct) and the Vectorize-side error (0 dimensions) but not the conversion step in between.

**The fix:**
```python
# ❌ Inner dicts become Maps
js_vectors = to_js(vectors)

# ✅ Inner dicts become Objects
js_vectors = to_js(vectors, dict_converter=js.Object.fromEntries)
```

**Why it was intermittent:** It wasn't. Every upsert without `dict_converter` produced Maps. But:
- Most feed fetches return 304 (no new entries, no indexing)
- The error was caught by try/except and logged as `search_index_skipped`
- The log lacked vector diagnostics, so we couldn't see that the vector was correct on the Python side

**The broader lesson:** When `_to_js_value()` checked `isinstance(value, dict)` to apply `dict_converter`, it missed lists-of-dicts. The top-level value was a `list`, so it took the default `to_js(value)` path. The inner dicts got default conversion (LiteralMap).

**The complete fix:** Don't selectively apply `dict_converter`. Always apply it:

```python
def _to_js_value(value):
    if not HAS_PYODIDE or to_js is None:
        return value
    return to_js(value, dict_converter=js.Object.fromEntries)
```

No `isinstance` check. `dict_converter` applies recursively to all nested dicts regardless of the top-level type. This eliminates the entire class of bugs — any future caller of `_to_js_value()` gets correct Object conversion automatically. And there should be no direct calls to `to_js()` outside of `_to_js_value()`.

**Lesson for debugging:** When a value crosses a boundary and the downstream system reports it as invalid, instrument the boundary itself — not just the input (Python side) or the output (error message). We needed to see what JS type `to_js()` actually produced, and we only got that by adding `constructor.name` logging at the Vectorize call site.

**How to prevent this class of bug:**
1. **Single gate for outbound conversion.** All `to_js()` calls go through `_to_js_value()`. No direct `to_js()` in business logic or wrapper code. A PBT source-scanning test enforces this.
2. **Always pass `dict_converter`.** There is no case in a Workers app where you want Python dicts to become JS Maps instead of Objects.
3. **`create_pyproxies=False`.** Raises `ConversionError` if any value in the object graph can't be natively converted (custom class, function, bytes, datetime). Catches non-primitive types that would silently create leaking PyProxies.
4. **PBT invariant:** For any nested Python structure of primitives/lists/dicts, `_to_js_value()` should succeed without creating PyProxies. A source-scanning test ensures no direct `to_js()` calls bypass the gate.

**Pyodide version context:** Cloudflare Workers uses **Pyodide 0.28.2** (as of 2026-03). The `to_js()` default changed from `LiteralMap` to `Object` in **Pyodide 0.29.0** (October 2025), but Workers hasn't shipped 0.29 yet. Our `dict_converter` fix is required on 0.28.2. It becomes redundant but harmless on 0.29+.

---

## 30. Pyodide Version Awareness and Binding Type Safety

**Problem:** Different Pyodide versions have different default behaviors. Code that works on one version may silently break on another. And different Cloudflare bindings return different JS types — some convert cleanly via `to_py()`, others stay as JsProxy.

**What Workers ships (as of 2026-03):**

| Pyodide | Python | Flag | Auto-enabled after |
|---------|--------|------|--------------------|
| 0.26.0a2 | 3.12.1 | `python_workers` | Always |
| **0.28.2** | **3.13.2** | `python_workers_20250116` | 2025-09-29 |

Planet CF uses compatibility date `2026-01-01` → runs **Pyodide 0.28.2**.

**Binding return type risk matrix:**

| Binding | `to_py()` converts? | Risk | Affected types |
|---------|---------------------|------|----------------|
| D1 | Yes — results are plain Objects | Low | — |
| Workers AI | Yes — embeddings are `number[][]` | Low | `ReadableStream` for streaming/images stays JsProxy |
| Vectorize | Mostly — matches may have custom prototypes | Medium | `Float32Array`/`Float64Array` → memoryview |
| Queues | Partially — `Message` is a class, `timestamp` is `Date` | Medium | `Date` stays JsProxy |
| R2 | No — `R2Object`, `R2ObjectBody` are classes | High | All return objects stay JsProxy |
| KV | Mostly — `arrayBuffer` type → memoryview | Low-Medium | `ArrayBuffer`, `ReadableStream` |

**Key rules from the Pyodide docs:**
- `to_py()` only converts objects with `constructor === Object` to dicts. Custom prototypes stay as JsProxy.
- `None` → `undefined` (not `null`). Use `js.JSON.parse("null")` for D1 SQL NULL.
- `null` → `pyodide.ffi.jsnull` (not Python `None`). Check with `_is_js_undefined()`.
- `to_js()` without `dict_converter` produces `LiteralMap` on Pyodide 0.28.2.
- `create_pyproxies=False` on `to_js()` raises `ConversionError` for non-primitive types instead of silently leaking.
- Wasm linear memory never shrinks — freed pages stay allocated until isolate eviction.

---

## 31. Test Count is Not Test Quality

**Problem:** Planet CF had ~1294 tests, all passing, with branch coverage enabled. This looked healthy. A test quality audit revealed that most test files had assertion density below 1.5 — meaning the average test made only one assertion. Security-critical files (`test_xml_sanitizer.py`, `test_session.py`, `test_security.py`, `test_auth.py`) were the worst offenders, with densities between 1.0 and 1.34.

**Why this matters:** A test with one assertion can pass even when the code is wrong. A sanitizer test that asserts `<script>` is removed but never checks that `<p>Hello</p>` survives will pass if the sanitizer strips *everything*. An auth test that asserts "invalid token returns None" but never checks "valid token returns session data" will pass even if the function always returns None.

**What we measured:**

| Metric | Before | After |
|--------|--------|-------|
| Test count | ~1294 | ~1426 |
| Avg assertion density | 1.82 | ≥3.0 (all files) |
| Hypothesis `@given` tests | 117 | 159 |
| Security test density | 1.0–1.34 | 3.0–4.4 |

**Three rules that emerged:**

1. **Bidirectional security checks.** Every security test must verify what's *allowed* AND what's *blocked*. A test that only checks one direction can pass even if the function is a no-op or strips everything.

2. **Assertion density ≥3.0 for all files, ≥4.0 for security.** A test function with 1 assertion is testing one property. A function with 3+ assertions tests behavior: the return value, its type, its side effects, and the absence of unwanted side effects. The density target is per-file average, not per-test minimum.

3. **Count mock assertions too.** `mock.assert_called_once()`, `mock.assert_awaited_once()`, and `mock.assert_not_called()` are real assertions — they raise `AssertionError` on failure. Automated audits that only count `assert` keyword statements will undercount mock-heavy test files. Our cache purge tests were flagged at 0.44 density but were actually 4.44 once mock assertions were included.

**PBT gaps follow module boundaries.** The existing `test_properties.py` had excellent coverage for core modules (auth, models, search) but missed utility modules (`utils.py`, `xml_sanitizer.py`, `instance_config.py`, `content_processor.py`, `templates.py`). These are exactly the kind of pure functions where "never crashes on arbitrary input", "idempotent", and "conservation" properties catch real bugs. PBT coverage should be audited per-module, not per-file.

**How to prevent this:**
- Track assertion density as a periodic audit metric, not just coverage percentage
- When adding a new test, check both directions: "does it work?" and "does it fail correctly?"
- When adding PBT for a new module, add at minimum: never-crashes, idempotent (if normalization), conservation (if filtering), roundtrip (if serialization)
