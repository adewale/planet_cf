# Python Workers — Gotchas

All known issues, pitfalls, and workarounds for Python Workers. Numbered for cross-referencing from `SKILL.md` decision trees.

---

## Table of Contents

**Runtime & Configuration**
- [#1: Missing Compatibility Flag](#1-missing-compatibility-flag)
- [#2: Legacy Handler Pattern](#2-legacy-handler-pattern)
- [#3: Sync HTTP Libraries Don't Work](#3-sync-http-libraries-dont-work)

**FFI / JavaScript-Python Boundary**
- [#4: to_py Is a Method, Not a Function](#4-to_py-is-a-method-not-a-function)
- [#5: None vs null vs undefined](#5-none-vs-null-vs-undefined)
- [#6: js.eval() Is Disallowed](#6-jseval-is-disallowed)
- [#7: Dict Becomes Map Without dict_converter](#7-dict-becomes-map-without-dict_converter)

**Performance**
- [#8: Cold Start Performance](#8-cold-start-performance)
- [#9: PRNG Cannot Be Seeded During Initialization](#9-prng-cannot-be-seeded-during-initialization)
- [#10: CPU Time vs Wall Clock Time](#10-cpu-time-vs-wall-clock-time)

**Binding-Specific**
- [#11: D1 Results Are JsProxy](#11-d1-results-are-jsproxy)
- [#12: HTMLRewriter Memory Limit with Data URLs](#12-htmlrewriter-memory-limit-with-data-urls)
- [#13: Vectorize Has No Local Simulation](#13-vectorize-has-no-local-simulation)
- [#14: Queue Message Body Is JsProxy](#14-queue-message-body-is-jsproxy)

**Packages**
- [#15: Native/Compiled Packages Don't Work](#15-nativecompiled-packages-dont-work)
- [#16: Package Installation Failures](#16-package-installation-failures)

**Development**
- [#17: Dev Registry Breaks JS-to-Python RPC](#17-dev-registry-breaks-js-to-python-rpc)
- [#18: Standard Library Limitations](#18-standard-library-limitations)

---

## #1: Missing Compatibility Flag

**Error**: `Error: Python Workers require the python_workers compatibility flag`

**Fix**:

```jsonc
{
  "compatibility_flags": ["python_workers"]
}
```

For Workflows, also add `"python_workflows"` (and sometimes `"experimental"`).

---

## #2: Legacy Handler Pattern

**Error**: `TypeError: on_fetch is not defined`

**Cause**: The `@handler` + `on_fetch` function pattern was deprecated August 2025.

```python
# WRONG (deprecated)
from workers import handler

@handler
async def on_fetch(request, env):
    return Response("Hello")

# CORRECT (current)
from workers import WorkerEntrypoint, Response

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("Hello")
```

The `scheduled` handler also changed — it's now a method on `WorkerEntrypoint`, not a standalone function with `@handler`.

To temporarily keep the old pattern, add `"disable_python_no_global_handlers"` compatibility flag.

---

## #3: Sync HTTP Libraries Don't Work

**Error**: `RuntimeError: cannot use blocking call in async context`

**Cause**: Python Workers are async-only. Sync libraries (requests, urllib3) rely on raw sockets, which are blocked by the browser security model that Pyodide enforces.

```python
# FAILS
import requests
response = requests.get("https://api.example.com")  # RuntimeError

# WORKS — httpx async
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get("https://api.example.com")

# WORKS — aiohttp
import aiohttp
async with aiohttp.ClientSession() as session:
    async with session.get("https://api.example.com") as response:
        data = await response.json()

# WORKS — js.fetch via FFI
from js import fetch
response = await fetch("https://api.example.com")
data = await response.json()
```

---

## #4: to_py Is a Method, Not a Function

**Error**: `ImportError: cannot import name 'to_py' from 'pyodide.ffi'`

**Cause**: Unlike `to_js` which is a standalone function, `to_py()` is a **method on JsProxy objects**.

```python
# WRONG
from pyodide.ffi import to_py
result = to_py(js_object)

# CORRECT — method on the object
data = await request.json()        # Returns JsProxy
python_dict = data.to_py()         # Method call on JsProxy

results = await env.DB.prepare("...").all()
rows = results.results.to_py()     # Method call on JsProxy
```

---

## #5: None vs null vs undefined

**Three distinct values** cross the JS/Python boundary:

| Python | JavaScript | When it happens |
|--------|------------|-----------------|
| `None` | `undefined` | Default — Python `None` becomes JS `undefined` |
| `JS_NULL` | `null` | Must be explicitly created (see below) |
| `None` (from JsProxy) | `null` | JS `null` converts to Python `None` via `.to_py()` |

**The problem**: D1 SQL expects `null` for NULL values, but Python `None` maps to `undefined`, which D1 treats differently.

```python
# WRONG — sends undefined to D1, not null
await env.DB.prepare("UPDATE feeds SET etag = ? WHERE id = ?").bind(None, feed_id).run()

# CORRECT — create JS null explicitly
JS_NULL = js.JSON.parse("null")  # Can't use js.eval("null") — see #6
await env.DB.prepare("UPDATE feeds SET etag = ? WHERE id = ?").bind(JS_NULL, feed_id).run()
```

**Also watch for**: JS `undefined` arriving as a JsProxy in Python. Use `_is_js_undefined()` to detect:

```python
def _is_js_undefined(value):
    if value is None:
        return False
    return str(type(value)) == "<class 'pyodide.ffi.JsProxy'>" and str(value) == "undefined"
```

---

## #6: js.eval() Is Disallowed

**Error**: `EvalError: Code generation from strings disallowed for this context`

**Cause**: Workers security policy blocks `eval()` and `Function()` constructor.

```python
# WRONG — EvalError
JS_NULL = js.eval("null")

# CORRECT — use JSON.parse
JS_NULL = js.JSON.parse("null")
```

This also means you cannot use `js.eval()` for any purpose. Use specific APIs instead.

---

## #7: Dict Becomes Map Without dict_converter

**Symptom**: Cloudflare APIs reject your Python dict, or return unexpected results

**Cause**: `to_js()` on a Python dict creates a JavaScript `Map`, not a plain `Object`. Most Cloudflare APIs expect plain objects.

```python
from pyodide.ffi import to_js
from js import Object

# WRONG — creates JS Map
js_obj = to_js({"topK": 50})  # Map, not Object!

# CORRECT — creates JS Object
js_obj = to_js({"topK": 50}, dict_converter=Object.fromEntries)
```

**Always** use `dict_converter=Object.fromEntries` when converting dicts for Cloudflare APIs. Wrap it in a helper:

```python
def _to_js_value(value):
    if isinstance(value, dict):
        return to_js(value, dict_converter=js.Object.fromEntries)
    return to_js(value)
```

---

## #8: Cold Start Performance

**Symptom**: First request takes 1-10+ seconds

**Cause**: Python Workers run Pyodide (CPython → WebAssembly). Cold starts are inherently slower than JavaScript Workers (~50ms).

**Benchmarks (Dec 2025)**:
- Without snapshots: ~10s for FastAPI/Pydantic
- With snapshots: ~1s (10x improvement)
- JavaScript Workers: ~50ms

**Mitigation**:
1. Add `"python_dedicated_snapshot"` compatibility flag (worker-specific snapshot)
2. Minimize top-level imports — move heavy imports inside handlers if possible
3. Pre-compile templates at build time (avoid Jinja2 parsing at runtime)
4. Use module-level constants (they're captured in the snapshot)
5. For <100ms latency requirements, consider JavaScript Workers

Wasm memory snapshots happen automatically at deploy time — no extra configuration beyond the flag.

---

## #9: PRNG Cannot Be Seeded During Initialization

**Error**: Deployment fails with user error

**Cause**: WebAssembly memory snapshots assert PRNG state is unchanged after snapshotting. Module-level calls to random/entropy fail.

```python
import random, secrets, uuid

# WRONG — all of these fail at module level
random.seed(42)
token = secrets.token_hex(16)
id = uuid.uuid4()

# CORRECT — inside handlers
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        random.seed(42)            # OK
        token = secrets.token_hex(16)  # OK
        id = uuid.uuid4()         # OK
```

This applies to ANY entropy-consuming call: `random.*`, `secrets.*`, `uuid.uuid4()`, `os.urandom()`.

---

## #10: CPU Time vs Wall Clock Time

**Symptom**: Worker killed for "exceeded CPU time" despite fast wall clock time

**Cause**: CPU time only counts computation, not I/O wait. Heavy Python parsing (feedparser, JSON, bleach, XML) can consume CPU quickly.

**Fix**: Increase CPU limit:

```jsonc
"limits": { "cpu_ms": 60000 }  // 60 seconds (default 30s paid, 10ms free)
```

| Plan | Default | Max |
|------|---------|-----|
| Free | 10ms | 10ms |
| Paid | 30ms | 900,000ms (15 min) |

---

## #11: D1 Results Are JsProxy

**Symptom**: TypeError when iterating D1 results, JSON serialization fails, attribute access returns unexpected values

**Cause**: D1 query results are JavaScript objects wrapped as JsProxy. They look like Python dicts but aren't.

```python
# WRONG — results.results is JsProxy, not a Python list
results = await env.DB.prepare("SELECT * FROM feeds").all()
for row in results.results:    # Might work but row is JsProxy
    print(row["title"])        # Might fail or return JsProxy

# CORRECT — convert at the boundary
results = await env.DB.prepare("SELECT * FROM feeds").all()
rows = results.results.to_py()  # Python list of dicts
for row in rows:
    print(row["title"])         # Native Python string
```

For production code, use typed conversion functions:

```python
def feed_rows_from_d1(results) -> list[FeedRow]:
    if not results or not results.results:
        return []
    return [dict(row) for row in results.results.to_py()]
```

---

## #12: HTMLRewriter Memory Limit with Data URLs

**Error**: `TypeError: Parser error: The memory limit has been exceeded`

**Cause**: Large inline `data:` URLs (>10MB) in HTML trigger parser memory limits. Common with Jupyter notebooks that embed base64 images.

```python
# WRONG — HTMLRewriter processes large data: URLs
response = await fetch("https://origin/notebook.html")
return response  # Crashes if HTML has large data: URLs

# CORRECT — stream directly without HTMLRewriter
response = await fetch("https://origin/notebook.html")
return Response(await response.text(), headers={"Content-Type": "text/html"})
```

**Workarounds**:
- Don't use HTMLRewriter on content with embedded data URLs
- Pre-process to extract data URLs to external files
- Use `text/plain` content type to bypass the parser entirely

---

## #13: Vectorize Has No Local Simulation

**Symptom**: Vectorize calls fail in local development

**Cause**: There is no local emulation for Vectorize. You must connect to the remote service.

**Fix**: Add `"remote": true` to the Vectorize binding:

```jsonc
"vectorize": [{
  "binding": "SEARCH_INDEX",
  "index_name": "my-index",
  "remote": true            // REQUIRED for local dev
}]
```

Also applies to Workers AI: `"ai": { "binding": "AI", "remote": true }`.

---

## #14: Queue Message Body Is JsProxy

**Symptom**: TypeError when accessing queue message fields

**Cause**: `message.body` in queue handlers is a JsProxy object.

```python
# WRONG — body is JsProxy
async def queue(self, batch):
    for msg in batch.messages:
        feed_id = msg.body["feed_id"]   # May fail or return JsProxy

# CORRECT — convert first
async def queue(self, batch):
    for msg in batch.messages:
        body = msg.body.to_py()         # Python dict
        feed_id = body["feed_id"]       # Native Python int/str
```

---

## #15: Native/Compiled Packages Don't Work

**Error**: `ModuleNotFoundError: No module named 'numpy'` (if not in Pyodide) or build/import errors

**Cause**: Only pure Python packages and packages included in Pyodide work. Native C extensions cannot be compiled to WebAssembly automatically.

**How to check**: Visit https://pyodide.org/en/stable/usage/packages-in-pyodide.html

**Common packages that DO work** (in Pyodide):
- numpy, pandas, scipy, pillow, matplotlib
- feedparser, httpx, aiohttp, jinja2, bleach, beautifulsoup4
- pydantic, fastapi, langchain-core

**Common packages that DON'T work**:
- psycopg2 (use D1 instead)
- lxml (use xml.etree.ElementTree)
- cryptography (use hashlib/hmac from stdlib)

**Request new packages**: https://github.com/cloudflare/workerd/discussions/categories/python-packages

---

## #16: Package Installation Failures

**Error**: `Failed to install package X`

**Causes**:
- Package has native dependencies (see #15)
- Package not in Pyodide ecosystem
- Version conflict with Pyodide's bundled packages
- Network issues during `pywrangler deploy`

**Debugging**:
```bash
# Check if package is pure Python
pip show <package>  # Look for "Location" — if it's in .so/.pyd files, it's native

# Test locally
uv run pywrangler dev  # Will fail fast if package can't load
```

---

## #17: Dev Registry Breaks JS-to-Python RPC

**Error**: `Network connection lost` when calling Python Worker from JavaScript Worker

**Cause**: Dev registry doesn't properly route RPC between Workers in separate terminals.

```bash
# WRONG — separate terminals
# Terminal 1: npx wrangler dev (JS worker)
# Terminal 2: npx wrangler dev (Python worker)

# CORRECT — single wrangler instance
npx wrangler dev -c ts/wrangler.jsonc -c py/wrangler.jsonc
```

---

## #18: Standard Library Limitations

**Not functional** (can be imported but won't work):
- `multiprocessing` — no process spawning in WebAssembly
- `threading` — no threads in WebAssembly
- `socket` — raw sockets blocked by browser security model

**Cannot import** (depend on removed `termios`):
- `pty`, `tty`

**Limited**:
- `decimal` — only C implementation (`_decimal`), no `_pydecimal`
- `webbrowser` — not available

**Excluded entirely**: `curses`, `dbm`, `ensurepip`, `fcntl`, `grp`, `idlelib`, `lib2to3`, `msvcrt`, `pwd`, `resource`, `syslog`, `termios`, `tkinter`, `venv`, `winreg`, `winsound`

---

## Quick Reference Table

| # | Issue | Error Signature | Fix |
|---|-------|-----------------|-----|
| 1 | Missing flag | `python_workers compatibility flag` | Add `"python_workers"` to flags |
| 2 | Old handler | `on_fetch is not defined` | Use `WorkerEntrypoint` class |
| 3 | Sync HTTP | `blocking call in async context` | Use `httpx` or `aiohttp` |
| 4 | to_py import | `cannot import name 'to_py'` | Use `.to_py()` method on JsProxy |
| 5 | None/null/undefined | D1 NULL issues | Use `js.JSON.parse("null")` |
| 6 | js.eval blocked | `Code generation disallowed` | Use `js.JSON.parse()` |
| 7 | Dict→Map | API rejects dict | Use `dict_converter=Object.fromEntries` |
| 8 | Slow cold start | First request 1-10s | Add `python_dedicated_snapshot` flag |
| 9 | PRNG at init | Deploy fails | Move random/secrets into handlers |
| 10 | CPU exceeded | Worker killed | Increase `cpu_ms` in limits |
| 11 | D1 JsProxy | TypeError on results | Call `.to_py()` on `results.results` |
| 12 | HTMLRewriter OOM | Memory limit exceeded | Don't rewrite content with data: URLs |
| 13 | No local Vectorize | Vectorize calls fail | Use `"remote": true` |
| 14 | Queue JsProxy | TypeError on msg.body | Call `msg.body.to_py()` |
| 15 | Native packages | ModuleNotFoundError | Use Pyodide-compatible alternatives |
| 16 | Install failure | Failed to install | Check Pyodide compatibility |
| 17 | RPC broken in dev | Network connection lost | Use single wrangler instance |
| 18 | Stdlib missing | ImportError | Check stdlib limitations |

---

## Limits Quick Reference

| Resource | Free | Paid |
|----------|------|------|
| Requests/day | 100,000 | Unlimited |
| CPU time/invocation | 10ms | 30ms default, up to 15 min |
| Worker size | 10MB | 10MB |
| Subrequests/request | 50 | 1,000 |
| D1 database size | 500MB | 10GB |
| D1 rows read/day | 5M | 50B |
| KV reads/day | 100,000 | 10M+ |
| R2 Class A ops/month | 1M | Pay per use |
| Queue messages/month | 1M | Pay per use |
| Vectorize dimensions | 1,536 max | 1,536 max |
| Vectorize vectors/index | 200,000 (free) | 5M (paid) |
