# Python Workers — Patterns

Production patterns for FFI boundary handling, D1 queries, queue processing, search, routing, authentication, error handling, security, observability, Jinja2 SSR, and testing.

---

## Table of Contents

- [FFI Boundary Layer](#ffi-boundary-layer)
- [D1 Database Patterns](#d1-database-patterns)
- [Queue Processing](#queue-processing)
- [Search (Vectorize + Workers AI)](#search-vectorize--workers-ai)
- [Routing](#routing)
- [Multi-Handler Worker](#multi-handler-worker)
- [Error Handling](#error-handling)
- [Authentication](#authentication)
- [Security](#security)
- [Server-Side Rendering (Jinja2)](#server-side-rendering-jinja2)
- [Observability](#observability)
- [FastAPI Integration](#fastapi-integration)
- [HTMLRewriter from Python](#htmlrewriter-from-python)
- [Durable Object WebSockets](#durable-object-websockets)
- [Testing](#testing)

---

## FFI Boundary Layer

The most important pattern in production Python Workers. All Cloudflare bindings return JsProxy objects — **convert them to native Python at the boundary, before business logic sees them.**

### The HAS_PYODIDE guard

Makes code testable outside the Workers runtime:

```python
try:
    import js
    from js import fetch as js_fetch
    from pyodide.ffi import to_js
    HAS_PYODIDE = True
    JS_NULL = js.JSON.parse("null")  # js.eval() is disallowed
except ImportError:
    js = None
    js_fetch = None
    to_js = None
    JS_NULL = None
    HAS_PYODIDE = False
```

### Safe recursive conversion

```python
_MAX_CONVERSION_DEPTH = 50

def _to_py_safe(value, depth=0):
    """Recursively convert JsProxy to native Python types."""
    if depth > _MAX_CONVERSION_DEPTH:
        return value
    if value is None:
        return None
    if _is_js_undefined(value):
        return None
    if hasattr(value, 'to_py'):
        return value.to_py()
    return value

def _is_js_undefined(value):
    """Check if value is JavaScript undefined wrapped as JsProxy."""
    if value is None:
        return False
    return (str(type(value)) == "<class 'pyodide.ffi.JsProxy'>"
            and str(value) == "undefined")
```

### Python-to-JS conversion

```python
def _to_js_value(value):
    """Convert Python value to JavaScript for Workers bindings."""
    if not HAS_PYODIDE or to_js is None:
        return value  # Test environment
    if isinstance(value, dict):
        return to_js(value, dict_converter=js.Object.fromEntries)
    return to_js(value)
```

**Critical**: Without `dict_converter=Object.fromEntries`, Python dicts become JavaScript `Map` objects, breaking most Cloudflare APIs.

### JS null for D1

Python `None` → JS `undefined`, but D1 needs JS `null` for SQL NULL:

```python
JS_NULL = js.JSON.parse("null")

# Use in D1 binds where NULL is needed
await self.env.DB.prepare(
    "UPDATE feeds SET etag = ? WHERE id = ?"
).bind(JS_NULL, feed_id).run()
```

---

## D1 Database Patterns

### Row type conversion

```python
from typing import TypedDict

class FeedRow(TypedDict):
    id: int
    url: str
    title: str | None
    is_active: int
    consecutive_failures: int

class EntryRow(TypedDict):
    id: int
    feed_id: int
    guid: str
    title: str
    content: str | None
    published_at: str

def feed_rows_from_d1(results) -> list[FeedRow]:
    """Convert D1 JsProxy results to typed Python dicts."""
    if not results or not results.results:
        return []
    return [dict(row) for row in results.results.to_py()]

def entry_rows_from_d1(results) -> list[EntryRow]:
    if not results or not results.results:
        return []
    return [dict(row) for row in results.results.to_py()]
```

### Parameterized queries (prevent SQL injection)

```python
# Safe — parameterized
result = await env.DB.prepare(
    "SELECT * FROM entries WHERE feed_id = ? AND published_at > ? ORDER BY published_at DESC LIMIT ?"
).bind(feed_id, cutoff_date, limit).all()

# Safe — multiple parameters
await env.DB.prepare(
    "INSERT INTO feeds (url, title, is_active) VALUES (?, ?, ?)"
).bind(url, title, 1).run()
```

### Auto-initialization

```python
async def ensure_tables(env):
    """Create tables on first request if they don't exist."""
    try:
        await env.DB.prepare("SELECT 1 FROM feeds LIMIT 1").first()
    except Exception:
        # Tables don't exist — run initial migration
        migration = Path(__file__).parent.parent / "migrations" / "001_initial.sql"
        for statement in migration.read_text().split(";"):
            stmt = statement.strip()
            if stmt:
                await env.DB.prepare(stmt).run()
```

### Batch queries

```python
# Multiple statements in one round-trip
results = await env.DB.batch([
    env.DB.prepare("UPDATE feeds SET last_fetched_at = ? WHERE id = ?").bind(now, feed_id),
    env.DB.prepare("INSERT INTO entries (feed_id, guid, title) VALUES (?, ?, ?)").bind(feed_id, guid, title),
])
```

### Migration files

```sql
-- migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    etag TEXT,
    last_modified TEXT,
    last_fetched_at TEXT,
    last_success_at TEXT,
    last_error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_feeds_active ON feeds(is_active);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL REFERENCES feeds(id),
    guid TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    author TEXT,
    link TEXT,
    published_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(feed_id, guid)
);

CREATE INDEX IF NOT EXISTS idx_entries_published ON entries(published_at);
CREATE INDEX IF NOT EXISTS idx_entries_feed ON entries(feed_id);
```

---

## Queue Processing

### Producer — enqueue work from scheduled handler

```python
async def scheduled(self, controller):
    """Hourly cron: enqueue active feeds for fetching."""
    results = await self.env.DB.prepare(
        "SELECT id, url, etag, last_modified FROM feeds WHERE is_active = 1"
    ).all()
    feeds = feed_rows_from_d1(results)

    enqueued = 0
    for feed in feeds:
        await self.env.FEED_QUEUE.send(_to_js_value({
            "feed_id": feed["id"],
            "url": feed["url"],
            "etag": feed.get("etag"),
            "last_modified": feed.get("last_modified"),
        }))
        enqueued += 1

    log_event("scheduler", feeds_enqueued=enqueued)
```

### Consumer — process with error handling per message

```python
async def queue(self, batch):
    """Process feed fetch jobs from queue."""
    for message in batch.messages:
        try:
            job = message.body.to_py()
            await self.fetch_and_store_feed(
                feed_id=job["feed_id"],
                url=job["url"],
                etag=job.get("etag"),
                last_modified=job.get("last_modified"),
            )
            message.ack()
        except Exception as e:
            log_event("feed_fetch_error", feed_id=job.get("feed_id"), error=str(e)[:200])
            message.retry()
```

### Dead-letter queue handling

```python
# In consumer, after max_retries exhausted, message goes to DLQ automatically.
# You can also manually send to DLQ:
except PermanentError as e:
    await self.env.DEAD_LETTER_QUEUE.send(_to_js_value({
        "original_job": job,
        "error": str(e),
        "timestamp": time.time(),
    }))
    message.ack()  # Don't retry — it's permanent
```

### HTTP conditional requests (ETag/Last-Modified)

```python
async def fetch_feed(self, url, etag=None, last_modified=None):
    headers = {"User-Agent": "MyBot/1.0"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=30)

    if response.status_code == 304:
        return None  # Not modified — skip processing

    # Store new ETag/Last-Modified for next fetch
    new_etag = response.headers.get("ETag")
    new_last_modified = response.headers.get("Last-Modified")
    # ... update database
```

---

## Search (Vectorize + Workers AI)

### Two-tier search: semantic + keyword

```python
async def search(self, query: str, env):
    """Combine semantic (Vectorize) and keyword (D1 LIKE) search."""
    # 1. Generate embedding for query
    ai_response = await env.AI.run("@cf/baai/bge-small-en-v1.5", {"text": [query]})
    query_vector = list(ai_response.data[0])

    # 2. Semantic search via Vectorize
    js_vector = to_js(query_vector)
    js_options = _to_js_value({"topK": 50, "returnValues": True})
    matches = await env.SEARCH_INDEX.query(js_vector, js_options)
    semantic_ids = [m.id for m in matches.matches]

    # 3. Keyword fallback via D1
    like_pattern = f"%{query}%"
    keyword_results = await env.DB.prepare(
        "SELECT id FROM entries WHERE title LIKE ? OR content LIKE ? LIMIT 50"
    ).bind(like_pattern, like_pattern).all()
    keyword_ids = [str(row.id) for row in keyword_results.results]

    # 4. Merge and deduplicate, semantic results first
    all_ids = list(dict.fromkeys(semantic_ids + keyword_ids))
    return all_ids
```

### Index entries on insert

```python
async def index_entry(self, entry_id: int, text: str, env):
    """Generate embedding and upsert to Vectorize."""
    # Truncate to max chars for embedding model
    truncated = text[:2000]

    response = await env.AI.run("@cf/baai/bge-small-en-v1.5", {"text": [truncated]})
    embedding = list(response.data[0])

    await env.SEARCH_INDEX.upsert([
        _to_js_value({"id": str(entry_id), "values": embedding})
    ])
```

---

## Routing

### Simple URL-based routing

```python
from urllib.parse import urlparse

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path
        method = request.method

        if path == "/":
            return await self.handle_home()
        elif path == "/feeds.xml":
            return await self.handle_rss()
        elif path == "/search" and method == "GET":
            return await self.handle_search(request)
        elif path.startswith("/admin") and method == "POST":
            return await self.handle_admin(request)
        else:
            return Response("Not Found", status=404)
```

### Route dispatcher pattern (for larger apps)

```python
import re
from dataclasses import dataclass

@dataclass
class Route:
    pattern: str
    handler: str
    methods: list[str] | None = None
    content_type: str = "text/html"
    cacheable: bool = False
    requires_auth: bool = False
    lite_mode_disabled: bool = False

@dataclass
class RouteMatch:
    route: Route
    params: dict

class RouteDispatcher:
    def __init__(self, routes: list[Route]):
        self._compiled = [(re.compile(r.pattern + "$"), r) for r in routes]

    def match(self, path: str, method: str = "GET") -> RouteMatch | None:
        for regex, route in self._compiled:
            if route.methods and method not in route.methods:
                continue
            m = regex.match(path)
            if m:
                return RouteMatch(route=route, params=m.groupdict())
        return None

# Usage
ROUTES = [
    Route(r"/", "handle_home", cacheable=True),
    Route(r"/feeds\.xml", "handle_rss", content_type="application/rss+xml", cacheable=True),
    Route(r"/search", "handle_search"),
    Route(r"/admin/feeds/(?P<feed_id>\d+)/delete", "handle_delete_feed",
          methods=["POST"], requires_auth=True),
]

dispatcher = RouteDispatcher(ROUTES)
```

---

## Multi-Handler Worker

Combine fetch + scheduled + queue in one class:

```python
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        """Serve web UI and API endpoints."""
        path = urlparse(request.url).path
        match = dispatcher.match(path, request.method)
        if not match:
            return Response("Not Found", status=404)
        handler = getattr(self, match.route.handler)
        return await handler(request, **match.params)

    async def scheduled(self, controller):
        """Hourly: enqueue feeds for fetching, run retention cleanup."""
        await self.enqueue_active_feeds()
        await self.cleanup_old_entries()

    async def queue(self, batch):
        """Process enqueued feed fetches."""
        for msg in batch.messages:
            try:
                await self.process_feed_job(msg.body.to_py())
                msg.ack()
            except Exception:
                msg.retry()
```

---

## Error Handling

### Result type

```python
from dataclasses import dataclass
from typing import TypeVar, Generic

T = TypeVar("T")
E = TypeVar("E")

@dataclass
class Ok(Generic[T]):
    value: T

@dataclass
class Err(Generic[E]):
    error: E

Result = Ok[T] | Err[E]
```

### Error classification (permanent vs transient)

```python
from enum import Enum

class FetchError(Enum):
    TIMEOUT = "timeout"
    DNS_FAILED = "dns_failed"
    CONNECTION_REFUSED = "connection_refused"
    HTTP_404 = "http_404"
    HTTP_410 = "http_410"
    PARSE_ERROR = "parse_error"

    @property
    def is_permanent(self) -> bool:
        return self in {FetchError.HTTP_404, FetchError.HTTP_410, FetchError.PARSE_ERROR}
```

### Feed health tracking

```python
async def update_feed_health(self, feed_id: int, success: bool, error: str | None = None):
    if success:
        await self.env.DB.prepare(
            "UPDATE feeds SET consecutive_failures = 0, last_success_at = datetime('now') WHERE id = ?"
        ).bind(feed_id).run()
    else:
        await self.env.DB.prepare(
            "UPDATE feeds SET consecutive_failures = consecutive_failures + 1, "
            "last_error_message = ? WHERE id = ?"
        ).bind(error[:200] if error else None, feed_id).run()

        # Auto-deactivate after threshold
        await self.env.DB.prepare(
            "UPDATE feeds SET is_active = 0 WHERE id = ? AND consecutive_failures >= ?"
        ).bind(feed_id, 10).run()
```

---

## Authentication

### Stateless HMAC-signed cookies

```python
import hashlib, hmac, json, base64, time

def create_signed_cookie(payload: dict, secret: str, ttl: int = 604800) -> str:
    payload["exp"] = int(time.time()) + ttl
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"

def verify_signed_cookie(cookie: str, secret: str) -> dict | None:
    try:
        encoded, sig = cookie.rsplit(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
```

### GitHub OAuth flow

```python
class GitHubOAuthHandler:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorize_url(self, state: str) -> str:
        from urllib.parse import urlencode
        params = urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "read:user",
            "state": state,
        })
        return f"https://github.com/login/oauth/authorize?{params}"

    async def exchange_code(self, code: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                json={"client_id": self.client_id, "client_secret": self.client_secret, "code": code},
                headers={"Accept": "application/json"},
            )
            return response.json()
```

---

## Security

### SSRF protection

```python
import ipaddress
from urllib.parse import urlparse

BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "metadata.google.internal"}

def validate_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.hostname in BLOCKED_HOSTS:
        return False
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
    except ValueError:
        pass  # Hostname, not IP — OK
    return True
```

### HTML sanitization (bleach)

```python
import bleach

ALLOWED_TAGS = [
    "a", "p", "br", "div", "span", "em", "strong", "code", "pre",
    "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "img", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td",
]

ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "loading"],
    "*": ["class"],
}

def sanitize_html(html: str) -> str:
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
```

### XXE prevention in XML/OPML parsing

```python
import xml.etree.ElementTree as ET
from io import BytesIO

def parse_opml_safe(content: str) -> ET.Element:
    """Parse OPML with XXE prevention."""
    parser = ET.XMLParser()
    # ElementTree's default parser in Python doesn't expand external entities,
    # but for defense in depth, parse from controlled input only
    return ET.fromstring(content.encode(), parser=parser)
```

---

## Server-Side Rendering (Jinja2)

### Pre-compiled templates (recommended)

Avoid Jinja2 parse cost at cold start by compiling templates at build time:

```python
# scripts/build_templates.py — run at build time
import jinja2
env = jinja2.Environment(loader=jinja2.FileSystemLoader("templates/"))
# Generate src/templates.py with template strings embedded

# src/templates.py — generated file, imported at runtime
_EMBEDDED_TEMPLATES = {
    "home": "<html>... {{ planet_name }} ...</html>",
    "feed_rss": "<?xml ... {{ entries }} ...",
}

# Usage in handler
template = jinja2.Template(_EMBEDDED_TEMPLATES["home"])
html = template.render(planet_name="My Planet", entries=entries)
```

### Runtime rendering (simpler, slower cold start)

```python
import jinja2

env = jinja2.Environment(autoescape=True)  # Module-level OK (no PRNG)

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        template = env.from_string("<h1>{{ title }}</h1>")
        html = template.render(title="Hello")
        return Response(html, headers={"Content-Type": "text/html"})
```

---

## Observability

### One event per unit of work

```python
from dataclasses import dataclass, field, asdict
import json, time

@dataclass
class RequestEvent:
    path: str
    method: str
    status: int = 0
    duration_ms: float = 0
    cache_hit: bool = False
    search_query: str | None = None
    error: str | None = None

    def emit(self):
        print(json.dumps({k: v for k, v in asdict(self).items() if v is not None}, default=str))

@dataclass
class FeedFetchEvent:
    feed_id: int
    url: str
    status_code: int = 0
    entries_found: int = 0
    entries_new: int = 0
    duration_ms: float = 0
    error: str | None = None

    def emit(self):
        print(json.dumps({k: v for k, v in asdict(self).items() if v is not None}, default=str))

class Timer:
    def __init__(self):
        self.start = time.monotonic()

    @property
    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.start) * 1000
```

---

## FastAPI Integration

```python
from fastapi import FastAPI, Request
from workers import WorkerEntrypoint

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello from FastAPI"}

@app.get("/env")
async def env(req: Request):
    env = req.scope["env"]  # Access Cloudflare bindings
    return {"name": env.APP_NAME}

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        import asgi
        return await asgi.fetch(app, request.js_object, self.env)
```

**Key points**:
- Use `request.js_object` to pass the underlying JS Request to the ASGI bridge
- Access `self.env` bindings in FastAPI via `req.scope["env"]`
- Add `python_dedicated_snapshot` for acceptable cold starts with FastAPI

---

## HTMLRewriter from Python

```python
from js import HTMLRewriter
from pyodide.ffi import create_proxy

class MetaTagInjector:
    def element(self, element):
        element.prepend('<meta property="og:title" content="My Site" />', html=True)

class OldMetaRemover:
    def element(self, element):
        element.remove()

injector = create_proxy(MetaTagInjector())
remover = create_proxy(OldMetaRemover())
rewriter = HTMLRewriter.new()
rewriter.on('meta[property^="og:"]', remover)
rewriter.on("head", injector)
return rewriter.transform(response.js_object)
```

---

## Durable Object WebSockets

```python
from js import WebSocketPair
from workers import DurableObject, Response
import json

class ChatRoom(DurableObject):
    async def fetch(self, request):
        client, server = WebSocketPair.new().object_values()
        self.state.acceptWebSocket(server)
        return Response(None, status=101, web_socket=client)

    async def webSocketMessage(self, ws, message):
        for client in self.state.getWebSockets():
            client.send(message)

    async def webSocketClose(self, ws, code, reason, wasClean):
        pass
```

---

## Testing

### Three-tier strategy

| Tier | Speed | What it tests | Bindings |
|------|-------|---------------|----------|
| **Unit** | ~1s (850+ tests) | Functions, models, logic | Mock objects |
| **Integration** | ~2s (85+ tests) | HTTP endpoints, full flows | Mock bindings |
| **E2E** | ~30s (34 tests) | Real Cloudflare infra | Live D1, Vectorize, AI |

### The HAS_PYODIDE pattern

Allows the same source code to run in Workers and pytest:

```python
# src/wrappers.py
try:
    import js
    from pyodide.ffi import to_js
    HAS_PYODIDE = True
except ImportError:
    js = None
    to_js = None
    HAS_PYODIDE = False

def _to_js_value(value):
    if not HAS_PYODIDE:
        return value  # In tests, pass through unchanged
    if isinstance(value, dict):
        return to_js(value, dict_converter=js.Object.fromEntries)
    return to_js(value)
```

### Mock D1

```python
class MockD1Statement:
    def __init__(self, sql, db):
        self.sql = sql
        self.db = db
        self.params = []

    def bind(self, *args):
        self.params = list(args)
        return self

    async def all(self):
        rows = self.db._execute(self.sql, self.params)
        return type("D1Result", (), {"results": rows, "success": True})()

    async def first(self):
        rows = self.db._execute(self.sql, self.params)
        return rows[0] if rows else None

    async def run(self):
        self.db._execute(self.sql, self.params)
        return type("D1Meta", (), {"changes": 1})()

class MockD1:
    def __init__(self):
        self._tables = {}  # table_name -> list of dicts

    def prepare(self, sql):
        return MockD1Statement(sql, self)

    def _execute(self, sql, params):
        # Simplified — match rows based on SQL patterns
        # In practice, use sqlite3 in-memory for full SQL support
        return []

    async def batch(self, statements):
        results = []
        for stmt in statements:
            results.append(await stmt.run())
        return results
```

### Mock Vectorize

```python
class MockVectorize:
    def __init__(self):
        self._vectors = {}  # id -> vector

    async def query(self, vector, options=None):
        top_k = 50
        if options and hasattr(options, 'topK'):
            top_k = options.topK
        # Return mock matches
        matches = [
            type("Match", (), {"id": id_, "score": 0.9})()
            for id_ in list(self._vectors.keys())[:top_k]
        ]
        return type("QueryResult", (), {"matches": matches})()

    async def upsert(self, vectors):
        for v in vectors:
            self._vectors[v["id"]] = v.get("values", [])

    async def deleteByIds(self, ids):
        for id_ in ids:
            self._vectors.pop(id_, None)
```

### Mock Workers AI

```python
class MockAI:
    async def run(self, model, inputs):
        if "bge-small" in model:
            # Return mock embeddings (768-dim)
            texts = inputs.get("text", inputs.get("input", []))
            embeddings = [[0.1] * 768 for _ in texts]
            return type("AIResult", (), {"data": embeddings})()
        return type("AIResult", (), {"output": "Mock AI response"})()
```

### Mock Queue

```python
class MockQueue:
    def __init__(self):
        self.messages = []

    async def send(self, body, **kwargs):
        self.messages.append(body)
```

### Mock request/response

```python
class MockRequest:
    def __init__(self, url="https://example.com/", method="GET", headers=None, body=None):
        self.url = url
        self.method = method
        self.headers = headers or {}
        self._body = body

    async def json(self):
        return self._body

class MockEnv:
    def __init__(self):
        self.DB = MockD1()
        self.SEARCH_INDEX = MockVectorize()
        self.AI = MockAI()
        self.FEED_QUEUE = MockQueue()
        self.DEAD_LETTER_QUEUE = MockQueue()
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret-key"
```

### Test factories

```python
class FeedFactory:
    _counter = 0

    @classmethod
    def create(cls, **overrides) -> dict:
        cls._counter += 1
        defaults = {
            "id": cls._counter,
            "url": f"https://example.com/feed{cls._counter}.xml",
            "title": f"Test Feed {cls._counter}",
            "is_active": 1,
            "consecutive_failures": 0,
        }
        defaults.update(overrides)
        return defaults

class EntryFactory:
    _counter = 0

    @classmethod
    def create(cls, feed_id=1, **overrides) -> dict:
        cls._counter += 1
        defaults = {
            "id": cls._counter,
            "feed_id": feed_id,
            "guid": f"entry-{cls._counter}",
            "title": f"Test Entry {cls._counter}",
            "content": "<p>Test content</p>",
            "published_at": "2026-01-15T12:00:00Z",
        }
        defaults.update(overrides)
        return defaults
```

### Example test

```python
import pytest

@pytest.fixture
def env():
    return MockEnv()

@pytest.mark.asyncio
async def test_search_returns_results(env):
    # Seed mock data
    env.SEARCH_INDEX._vectors = {"1": [0.1] * 768, "2": [0.2] * 768}

    builder = SearchQueryBuilder(env)
    results = await builder.search("python workers")

    assert len(results) > 0

@pytest.mark.asyncio
async def test_feed_fetch_updates_health_on_success(env):
    feed = FeedFactory.create()
    env.DB._tables["feeds"] = [feed]

    await update_feed_health(env, feed["id"], success=True)
    # Assert consecutive_failures reset to 0

@pytest.mark.asyncio
async def test_queue_message_acked_on_success():
    queue = MockQueue()
    # ... test queue processing
    assert len(queue.messages) == 1
```

### Running tests

```bash
# All tests
uv run pytest tests/ -x -q

# Unit only (fast)
uv run pytest tests/unit -x -q

# Integration only
uv run pytest tests/integration -x -q

# With coverage
uv run pytest tests/unit tests/integration --cov=src --cov-report=term-missing

# Specific test
uv run pytest tests/unit/test_models.py::test_feed_row_conversion -v
```
