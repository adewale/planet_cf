# Python Workers — API Reference

Complete API reference for all handler types, all bindings, FFI functions, and the Response class.

---

## Table of Contents

- [Handlers](#handlers) — fetch, scheduled, queue
- [Response](#response)
- [FFI (Foreign Function Interface)](#ffi)
- [D1 Database](#d1-database)
- [KV Storage](#kv-storage)
- [R2 Object Storage](#r2-object-storage)
- [Queues](#queues)
- [Vectorize](#vectorize)
- [Workers AI](#workers-ai)
- [Durable Objects](#durable-objects)
- [Static Assets](#static-assets)
- [Workflows](#workflows)
- [Service Bindings (RPC)](#service-bindings-rpc)
- [Logging](#logging)

---

## Handlers

### fetch — HTTP Requests

```python
from workers import WorkerEntrypoint, Response

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # request is a JavaScript Request object (via FFI)
        url = request.url           # str
        method = request.method     # str: GET, POST, etc.
        headers = request.headers   # JS Headers object

        # Read a specific header
        auth = request.headers.get("Authorization")

        # Parse JSON body
        if method == "POST":
            body = await request.json()  # Returns JsProxy — use .to_py() for dict
            python_dict = body.to_py()

        # Parse URL and query parameters
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(request.url)
        path = parsed.path
        params = parse_qs(parsed.query)

        return Response("OK")
```

### scheduled — Cron Triggers

```python
class Default(WorkerEntrypoint):
    async def scheduled(self, controller):
        # controller.scheduledTime — when the cron fired (JS Date as string)
        # controller.cron — the cron pattern that matched (e.g. "0 * * * *")
        print(f"Cron triggered: {controller.cron}")
        await self.env.QUEUE.send({"action": "refresh"})
```

### queue — Queue Message Batches

```python
class Default(WorkerEntrypoint):
    async def queue(self, batch):
        # batch.messages — iterable of queue messages
        for message in batch.messages:
            body = message.body          # JsProxy — call .to_py() for Python dict
            python_body = body.to_py()

            message.ack()                # Acknowledge — remove from queue
            # OR
            message.retry()              # Return to queue for retry
```

**Message object properties**:

| Property | Type | Description |
|----------|------|-------------|
| `message.body` | JsProxy | Message payload (call `.to_py()` to get dict) |
| `message.id` | str | Unique message ID |
| `message.timestamp` | JS Date | When message was enqueued |
| `message.ack()` | method | Acknowledge (remove from queue) |
| `message.retry()` | method | Return to queue for retry |

---

## Response

Python-friendly wrapper around JavaScript Response.

```python
from workers import Response

# Text
Response("Hello World!")
Response("Not Found", status=404)
Response("OK", headers={"Content-Type": "text/plain", "Cache-Control": "max-age=3600"})

# JSON
Response.json({"key": "value"})
Response.json({"error": "not found"})  # Note: no status param on .json()

# Binary
Response(image_bytes, headers={"Content-Type": "image/png"})

# Redirect
Response(None, status=302, headers={"Location": "/new-path"})

# WebSocket upgrade
Response(None, status=101, web_socket=client_ws)

# Empty with headers only
Response(None, status=204, headers={"X-Custom": "value"})
```

### Response helper pattern

```python
def html_response(body: str, status: int = 200, headers: dict | None = None) -> Response:
    h = {"Content-Type": "text/html; charset=utf-8"}
    if headers:
        h.update(headers)
    return Response(body, status=status, headers=h)

def json_response(data: dict, status: int = 200) -> Response:
    import json
    return Response(json.dumps(data), status=status,
                    headers={"Content-Type": "application/json"})

def feed_response(xml: str, content_type: str = "application/rss+xml") -> Response:
    return Response(xml, headers={
        "Content-Type": f"{content_type}; charset=utf-8",
        "Cache-Control": "public, max-age=3600",
    })
```

---

## FFI

### import js — Access JavaScript Globals

```python
from js import fetch, console, Response as JsResponse, Object, JSON, URL
from js import Headers, HTMLRewriter, WebSocket, WebSocketPair
```

When using `js.Response` directly (not the `workers.Response` wrapper), use `.new()`:

```python
from js import Response as JsResponse
return JsResponse.new("Hello!")  # .new() required for JS constructors
```

### to_js — Python to JavaScript

```python
from js import Object
from pyodide.ffi import to_js

# CRITICAL: Always use dict_converter for dicts
# Without it, Python dicts become JS Map (not Object), breaking most JS APIs
python_dict = {"name": "test", "count": 42}
js_object = to_js(python_dict, dict_converter=Object.fromEntries)

# Lists convert directly
js_array = to_js([1, 2, 3])

# Primitives (str, int, float, bool) convert automatically — no to_js needed
```

### to_py — JavaScript to Python

**`to_py()` is a METHOD on JsProxy objects, NOT a standalone function.**

```python
# WRONG — ImportError!
from pyodide.ffi import to_py
result = to_py(js_object)

# CORRECT — method on JsProxy
data = await request.json()       # Returns JsProxy
python_dict = data.to_py()        # Convert to Python dict

# D1 results
results = await self.env.DB.prepare("SELECT * FROM feeds").all()
rows = results.results.to_py()    # Convert JsProxy array to Python list
```

### create_proxy — Python Callables for JS APIs

Required when passing Python functions to JS APIs that **retain references** (e.g., `addEventListener`, `HTMLRewriter.on`):

```python
from pyodide.ffi import create_proxy

class MetaInjector:
    def element(self, element):
        element.prepend('<meta property="og:title" content="..." />', html=True)

handler = create_proxy(MetaInjector())
rewriter = HTMLRewriter.new()
rewriter.on("head", handler)
result = rewriter.transform(response.js_object)

# Destroy when done (except in long-lived DOs)
handler.destroy()
```

### Safe conversion helper

Production pattern for recursive JsProxy-to-Python conversion:

```python
_MAX_CONVERSION_DEPTH = 50

def _to_py_safe(value, depth=0):
    """Recursively convert JsProxy to native Python, with depth limit."""
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
    """Check if value is JavaScript undefined (wrapped as JsProxy)."""
    if value is None:
        return False
    return str(type(value)) == "<class 'pyodide.ffi.JsProxy'>" and str(value) == "undefined"
```

### JS null creation

Python `None` → JS `undefined` (NOT `null`). For APIs that need `null` (e.g., D1):

```python
import js

# js.eval("null") is disallowed in Workers
# Use JSON.parse instead:
JS_NULL = js.JSON.parse("null")
```

### Python-to-JS helper

```python
def _to_js_value(value):
    """Convert Python value to JavaScript, handling dicts correctly."""
    if not HAS_PYODIDE:
        return value  # Test environment
    if isinstance(value, dict):
        return to_js(value, dict_converter=js.Object.fromEntries)
    return to_js(value)
```

---

## D1 Database

### Query Methods

```python
# SELECT all rows
results = await self.env.DB.prepare("SELECT * FROM feeds WHERE is_active = ?").bind(1).all()
# results.results — JsProxy array of row objects
# results.success — bool
# results.meta — query metadata

# SELECT first row only
row = await self.env.DB.prepare("SELECT * FROM feeds WHERE id = ?").bind(feed_id).first()
# row — single JsProxy row object, or None

# INSERT / UPDATE / DELETE (no return data)
await self.env.DB.prepare("INSERT INTO feeds (url, title) VALUES (?, ?)").bind(url, title).run()
# returns meta (changes, last_row_id, etc.)

# Raw execution (no bind)
results = await self.env.DB.prepare("PRAGMA table_list").run()

# Batch queries (multiple statements in one round-trip)
results = await self.env.DB.batch([
    self.env.DB.prepare("INSERT INTO feeds (url) VALUES (?)").bind(url1),
    self.env.DB.prepare("INSERT INTO feeds (url) VALUES (?)").bind(url2),
])
```

### Parameter Binding

```python
# Positional parameters (?)
stmt = self.env.DB.prepare("SELECT * FROM entries WHERE feed_id = ? AND published_at > ?")
results = await stmt.bind(feed_id, cutoff_date).all()

# ALWAYS use bind() for user input — prevents SQL injection
# NEVER use f-strings or string concatenation for SQL
```

### Row Conversion

D1 results are JsProxy objects. Convert at the boundary:

```python
from typing import TypedDict

class FeedRow(TypedDict):
    id: int
    url: str
    title: str
    is_active: int

def feed_rows_from_d1(results) -> list[FeedRow]:
    """Convert D1 JsProxy results to typed Python dicts."""
    if not results or not results.results:
        return []
    rows = results.results.to_py()
    return [dict(row) for row in rows]  # Ensure plain dicts
```

---

## KV Storage

```python
# Get
value = await self.env.MY_KV.get("key")                         # text (default)
value = await self.env.MY_KV.get("key", type="json")            # parsed JSON
value = await self.env.MY_KV.get("key", type="arrayBuffer")     # binary

# Put
await self.env.MY_KV.put("key", "value")
await self.env.MY_KV.put("key", "value", expirationTtl=3600)    # TTL in seconds
await self.env.MY_KV.put("key", "value", expiration=1700000000) # Unix timestamp

# Delete
await self.env.MY_KV.delete("key")

# List
keys = await self.env.MY_KV.list()
keys = await self.env.MY_KV.list(prefix="user:", limit=100)
```

---

## R2 Object Storage

```python
# Get
obj = await self.env.MY_BUCKET.get("file.txt")
if obj:
    content = await obj.text()       # string
    binary = await obj.arrayBuffer() # bytes

# Put
await self.env.MY_BUCKET.put("file.txt", "content")
await self.env.MY_BUCKET.put("image.png", binary_data,
    httpMetadata={"contentType": "image/png"})

# Delete
await self.env.MY_BUCKET.delete("file.txt")

# List
listed = await self.env.MY_BUCKET.list(prefix="uploads/", limit=100)
```

---

## Queues

### Producer (sending messages)

```python
from js import Object
from pyodide.ffi import to_js

def to_js_obj(obj):
    return to_js(obj, dict_converter=Object.fromEntries)

# Send a message
await self.env.FEED_QUEUE.send(to_js_obj({"feed_id": 1, "url": "https://..."}))

# Send plain text
await self.env.FEED_QUEUE.send("hello", contentType="text")
```

### Consumer (receiving messages)

```python
class Default(WorkerEntrypoint):
    async def queue(self, batch):
        for message in batch.messages:
            try:
                body = message.body.to_py()  # Convert JsProxy to dict
                await self.process_message(body)
                message.ack()                # Success — remove from queue
            except Exception as e:
                print(f"Error processing message {message.id}: {e}")
                message.retry()              # Failure — re-enqueue for retry
```

### Dead-letter queue

Messages that exhaust `max_retries` are sent to the dead-letter queue:

```python
# Send to DLQ manually
await self.env.DEAD_LETTER_QUEUE.send(to_js_obj({
    "original_message": body,
    "error": str(e),
    "timestamp": time.time(),
}))
```

---

## Vectorize

```python
# Query (find similar vectors)
from pyodide.ffi import to_js
from js import Object

query_vector = [0.1, 0.2, ...]  # 768-dim float array
js_vector = to_js(query_vector)
js_options = to_js({"topK": 50, "returnValues": True}, dict_converter=Object.fromEntries)

matches = await self.env.SEARCH_INDEX.query(js_vector, js_options)
# matches.matches — JsProxy array of {id, score, values?}

# Insert vectors
await self.env.SEARCH_INDEX.upsert([
    to_js({"id": str(entry_id), "values": embedding_vector}, dict_converter=Object.fromEntries)
])

# Delete vectors
await self.env.SEARCH_INDEX.deleteByIds([str(entry_id)])
```

**Note**: Vectorize has no local simulation — use `"remote": true` in wrangler.jsonc during development.

---

## Workers AI

```python
# Text generation
response = await self.env.AI.run("@cf/openai/gpt-oss-120b", {
    "instructions": "You are a concise assistant.",
    "input": "What is Python?",
})
result = response.output  # string

# Embeddings
response = await self.env.AI.run("@cf/baai/bge-small-en-v1.5", {
    "text": ["Hello world", "Another sentence"],
})
embeddings = response.data  # JsProxy array of float arrays
# Convert: embeddings_py = [list(e) for e in embeddings.to_py()]

# Image classification, translation, etc. — same .run() pattern
response = await self.env.AI.run("@cf/model-name", input_data)
```

---

## Durable Objects

### Defining a Durable Object

```python
from workers import DurableObject, Response
from pyodide.ffi import to_js

class MyCounter(DurableObject):
    def __init__(self, state, env):
        super().__init__(state, env)
        # self.ctx — DurableObjectState (storage, alarms, WebSockets)
        # self.env — Cloudflare bindings

    async def fetch(self, request):
        count = await self.ctx.storage.get("count") or 0
        count += 1
        await self.ctx.storage.put("count", count)
        return Response(f"Count: {count}")

    async def alarm(self):
        """Triggered by self.ctx.storage.setAlarm(timestamp)."""
        print("Alarm fired!")
```

### Using a Durable Object from a Worker

```python
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # Get or create DO instance by name
        do_id = self.env.MY_COUNTER.idFromName("global-counter")
        stub = self.env.MY_COUNTER.get(do_id)

        # Call fetch on the DO
        response = await stub.fetch(request)
        return response

        # Or call custom RPC methods
        count = await stub.increment()
```

### DO Storage API

```python
# Key-value storage
await self.ctx.storage.get("key")
await self.ctx.storage.put("key", to_js(value))
await self.ctx.storage.delete("key")

# SQL storage (SQLite)
cursor = self.ctx.storage.sql.exec("SELECT * FROM messages")

# Alarms
await self.ctx.storage.setAlarm(Date.now() + 60000)  # 60s from now

# WebSocket management
self.state.acceptWebSocket(server_ws)
websockets = self.state.getWebSockets()
```

### DO WebSocket Pattern

```python
from js import WebSocketPair
import json

class ChatRoom(DurableObject):
    async def fetch(self, request):
        client, server = WebSocketPair.new().object_values()
        self.state.acceptWebSocket(server)
        return Response(None, status=101, web_socket=client)

    async def webSocketMessage(self, ws, message):
        for client_ws in self.state.getWebSockets():
            client_ws.send(message)

    async def webSocketClose(self, ws, code, reason, wasClean):
        pass

    async def webSocketError(self, ws, error):
        pass
```

---

## Static Assets

```python
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # Serve static files from the assets/ directory
        return await self.env.ASSETS.fetch(request)
```

For hybrid (static + dynamic):

```python
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path

        # Static files
        if path.startswith("/static/"):
            return await self.env.ASSETS.fetch(request)

        # Dynamic routes
        if path == "/":
            return html_response(self.render_homepage())

        return Response("Not Found", status=404)
```

---

## Workflows

### Defining a Workflow

```python
from workers import WorkflowEntrypoint, WorkerEntrypoint, Response

class MyWorkflow(WorkflowEntrypoint):
    async def run(self, event, step):
        # Step 1 — each step is durable (retried on failure)
        @step.do("fetch data")
        async def fetch_data():
            response = await fetch("https://api.example.com/data")
            return await response.json()  # Must be JSON-serializable

        data = await fetch_data()

        # Step 2 — sleep
        await step.sleep("wait", "10 seconds")

        # Step 3 — use result from step 1
        @step.do("process data")
        async def process_data():
            return {"processed": True, "count": len(data)}

        return await process_data()
```

### DAG Dependencies (parallel steps)

```python
class MyWorkflow(WorkflowEntrypoint):
    async def run(self, event, step):
        @step.do("step_a")
        async def step_a():
            return "A done"

        @step.do("step_b")
        async def step_b():
            return "B done"

        # step_c depends on both step_a and step_b
        @step.do("step_c", depends=[step_a, step_b], concurrent=True)
        async def step_c(result_a, result_b):
            return f"Got: {result_a}, {result_b}"

        return await step_c()
```

### Concurrent steps with asyncio.gather

```python
import asyncio

@step.do("step_a")
async def step_a():
    return "A"

@step.do("step_b")
async def step_b():
    return "B"

# Like Promise.all — runs both steps concurrently
results = await asyncio.gather(step_a(), step_b())
```

### Triggering a Workflow

```python
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        # Create a new workflow instance
        instance = await self.env.MY_WORKFLOW.create()
        return Response(f"Started: {instance.id}")

        # Check status
        instance = await self.env.MY_WORKFLOW.get(workflow_id)
        status = await instance.status()
        return Response.json(status)
```

---

## Service Bindings (RPC)

Python Workers can expose custom methods callable from other Workers:

```python
# Python Worker (RPC server)
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("RPC server running")

    async def highlight_code(self, code: str, language: str = None) -> dict:
        """Custom RPC method — callable via Service Binding."""
        from pygments import highlight
        from pygments.lexers import get_lexer_by_name
        from pygments.formatters import HtmlFormatter
        lexer = get_lexer_by_name(language, stripall=True)
        formatter = HtmlFormatter()
        return {"html": highlight(code, lexer, formatter)}
```

---

## Logging

```python
# Python print — appears in wrangler tail and dashboard
print("Hello from Python Worker!")

# Python logging module
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logger.info("Processing request")

# JavaScript console (via FFI)
from js import console
console.log("From JS console")
```

### Structured logging pattern

```python
import json, time

def log_event(event_type: str, **fields):
    fields["event_type"] = event_type
    fields["timestamp"] = time.time()
    print(json.dumps(fields, default=str))
```

---

## Reading Bundled Files

```python
from pathlib import Path

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        html = Path(__file__).parent / "index.html"
        return Response(html.read_text(), headers={"Content-Type": "text/html"})
```
