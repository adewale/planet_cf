---
name: cloudflare-python-workers
description: Comprehensive skill for building Cloudflare Workers in Python. Covers the Pyodide runtime, JavaScript/Python FFI boundary, all bindings (D1, KV, R2, Queues, Vectorize, Workers AI, Durable Objects, Workflows), package management, testing strategies, and production patterns.
version: 0.1.0
runtime: Pyodide (CPython 3.12+ compiled to WebAssembly)
status: Open Beta (requires python_workers compatibility flag)
last_verified: 2026-02-08
references:
  - python-workers
---

# Cloudflare Python Workers Skill

Consolidated skill for building Cloudflare Workers in Python. Use the decision trees below to navigate, then load the detailed reference files from `references/python-workers/`.

## Authentication (Required Before Deploy)

```bash
npx wrangler whoami        # check current auth
npx wrangler login         # interactive OAuth (one-time)
# or: CLOUDFLARE_API_TOKEN env var for CI/CD
```

## Quick Decision Trees

### "I need to set up a Python Worker"

```
New project?
├─ Quick start with pywrangler         -> README.md
├─ Understand the runtime (Pyodide)    -> README.md
├─ Configure wrangler.jsonc            -> configuration.md
├─ Add Python packages                 -> configuration.md (Package Management)
├─ Migrate from pre-Dec 2025 Worker    -> gotchas.md (#15)
└─ Set up testing                      -> patterns.md (Testing)
```

### "I need to use a Cloudflare binding from Python"

```
Which binding?
├─ SQL database (D1)                   -> api.md (D1) + patterns.md (D1)
├─ Key-value storage (KV)             -> api.md (KV)
├─ Object storage (R2)                -> api.md (R2)
├─ Message queues (Queues)            -> api.md (Queues) + patterns.md (Queues)
├─ Vector embeddings (Vectorize)      -> api.md (Vectorize)
├─ AI inference (Workers AI)          -> api.md (Workers AI)
├─ Stateful coordination (DOs)        -> api.md (Durable Objects)
├─ Static file serving                -> api.md (Static Assets)
├─ Long-running jobs (Workflows)      -> api.md (Workflows)
├─ Environment variables / secrets    -> configuration.md (Secrets)
└─ Worker-to-Worker RPC              -> api.md (Service Bindings)
```

### "I need to cross the JS/Python boundary"

```
FFI task?
├─ Convert JS object to Python dict   -> api.md (FFI) — to_py / _to_py_safe
├─ Convert Python dict to JS object   -> api.md (FFI) — to_js with dict_converter
├─ Handle None vs null vs undefined   -> gotchas.md (#5)
├─ Use JS globals (fetch, console)    -> api.md (FFI) — import js
├─ Pass Python function to JS API     -> api.md (FFI) — create_proxy
├─ D1 results are JsProxy objects     -> patterns.md (D1 Row Conversion)
└─ Deep/recursive conversion          -> patterns.md (Safe JsProxy Conversion)
```

### "I need to handle different trigger types"

```
Which trigger?
├─ HTTP requests (fetch)              -> api.md (fetch handler)
├─ Cron schedules (scheduled)         -> api.md (scheduled handler)
├─ Queue messages (queue)             -> api.md (queue handler)
├─ Multiple triggers in one Worker    -> patterns.md (Multi-Handler Worker)
└─ Durable Object alarms              -> api.md (Durable Objects)
```

### "I need to debug or test"

```
Testing task?
├─ Unit test with mock bindings       -> patterns.md (Testing — Unit Tests)
├─ Integration test flows             -> patterns.md (Testing — Integration Tests)
├─ E2E against live Cloudflare        -> patterns.md (Testing — E2E Tests)
├─ Mock D1 / Vectorize / AI / Queue   -> patterns.md (Testing — Mock Bindings)
├─ Test code that uses Pyodide FFI    -> patterns.md (Testing — HAS_PYODIDE)
└─ Run tests (pytest)                 -> configuration.md (Test Setup)
```

### "Something isn't working"

```
Common issues?
├─ TypeError / ImportError with FFI   -> gotchas.md (#4, #5, #6)
├─ D1 returns JsProxy not dict        -> gotchas.md (#5) + patterns.md (D1)
├─ None vs null in D1 queries         -> gotchas.md (#5)
├─ Sync HTTP library fails            -> gotchas.md (#3)
├─ Package not found / won't install  -> gotchas.md (#8, #15)
├─ Cold start too slow                -> gotchas.md (#7)
├─ PRNG fails at module level         -> gotchas.md (#9)
├─ "python_workers flag required"     -> gotchas.md (#1)
├─ HTMLRewriter memory limit          -> gotchas.md (#12)
├─ Queue messages not processing      -> gotchas.md (#14)
└─ js.eval() is disallowed            -> gotchas.md (#6)
```

## Reference Files

All in `references/python-workers/`:

| File | Contents |
|------|----------|
| `README.md` | Runtime overview, quick start, project structure, the `workers` module |
| `api.md` | All handler signatures, all binding APIs (D1, KV, R2, Queues, Vectorize, AI, DOs, Workflows, Static Assets), FFI functions, Response class |
| `configuration.md` | wrangler.jsonc (full reference), pyproject.toml, compatibility flags, secrets, CPU limits, deployment, test setup |
| `patterns.md` | FFI boundary layer, D1 row conversion, queue processing, search (Vectorize+AI), routing, auth, error handling, observability, testing (3-tier with mock bindings), Jinja2 SSR, security |
| `gotchas.md` | All 15+ known issues: FFI conversion, None/null/undefined, sync libs, cold starts, PRNG, HTMLRewriter, package compat, etc. |

## Reading Order

| Task | Files to Read |
|------|---------------|
| New Python Worker project | `README.md` → `configuration.md` → `api.md` |
| Add a binding | `api.md` (binding section) → `configuration.md` (binding config) → `patterns.md` |
| Debug FFI issues | `gotchas.md` → `patterns.md` (FFI section) → `api.md` (FFI section) |
| Set up testing | `patterns.md` (Testing section) → `configuration.md` (Test Setup) |
| Production readiness | `gotchas.md` → `patterns.md` (Security + Testing) |

## Anti-Patterns

### SQL Injection

```python
# NEVER - string interpolation
result = await env.DB.prepare(f"SELECT * FROM users WHERE id = {user_id}").all()

# ALWAYS - prepared statements with bind()
result = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(user_id).all()
```

### Sync HTTP Libraries

```python
# NEVER - sync libraries block the event loop
import requests
response = requests.get("https://api.example.com")

# ALWAYS - async libraries
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get("https://api.example.com")
```

### Raw JsProxy in Business Logic

```python
# NEVER - pass JsProxy objects to application code
results = await env.DB.prepare("SELECT * FROM feeds").all()
return results.results  # JsProxy! Breaks JSON serialization, iteration, etc.

# ALWAYS - convert at the boundary
results = await env.DB.prepare("SELECT * FROM feeds").all()
rows = _to_py_safe(results.results)  # Native Python list of dicts
```

### Module-Level PRNG

```python
# NEVER - PRNG at module level breaks Wasm snapshots
import random
random.seed(42)  # Deployment FAILS

# ALWAYS - PRNG inside handlers
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        random.seed(42)  # OK here
```

### Hardcoded Secrets

```bash
# NEVER - secrets in wrangler.jsonc or code
"vars": { "API_KEY": "sk-abc123" }

# ALWAYS - use wrangler secret
npx wrangler secret put API_KEY
# Access via self.env.API_KEY
```
