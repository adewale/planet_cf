# Cloudflare Python Workers

## Overview

Cloudflare Python Workers run Python 3.12+ via **Pyodide** (CPython compiled to WebAssembly) inside V8 isolates. No special toolchain or precompilation is needed — the Workers runtime provides the Python execution environment directly.

**Status**: Open Beta (requires `python_workers` compatibility flag)
**Runtime**: Pyodide (CPython 3.12+ → WebAssembly inside V8)
**Pricing**: Free tier 100,000 requests/day, 10ms CPU; Paid unlimited requests, configurable CPU

## Key Characteristics

- **Async-only** — all handlers are `async def`, only async I/O libraries work
- **Full binding access** — D1, KV, R2, Queues, Vectorize, Workers AI, Durable Objects, Workflows via `self.env`
- **Pyodide FFI** — seamless bridge to JavaScript APIs, but requires careful type conversion
- **WebAssembly memory snapshots** — fast cold starts via three-tier snapshot system
- **Pure Python + Pyodide packages** — PyPI packages that are pure Python or in Pyodide's ecosystem

## Quick Start

```bash
# Prerequisites: uv (Python package manager) + Node.js (for wrangler)
mkdir my-worker && cd my-worker
uv init
uv tool install workers-py
uv run pywrangler init       # creates wrangler config, selects template
```

Create `src/entry.py`:

```python
from workers import WorkerEntrypoint, Response

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return Response("Hello from Python Worker!")
```

```bash
uv run pywrangler dev        # local dev server at http://localhost:8787
uv run pywrangler deploy     # deploy to Cloudflare's global network
```

## How It Works

### Runtime Architecture

1. Python code runs inside Pyodide (CPython compiled to WebAssembly) in a V8 isolate
2. Pyodide's FFI bridges JavaScript and Python — all Cloudflare bindings work via this bridge
3. JavaScript objects appear as `JsProxy` in Python; conversion must be explicit for mutable types

### Deployment Lifecycle

1. `pywrangler deploy` uploads Python code + packages to the Workers API
2. Cloudflare validates the code, creates a V8 isolate, injects Pyodide
3. Scans and executes import statements, takes a **WebAssembly memory snapshot**
4. Deploys the snapshot alongside code to the global network
5. On request: restores snapshot (fast), then runs handler

### Cold Start Optimization

Three-tier snapshot system:
- **Baseline**: Shared Pyodide runtime
- **Package**: Pyodide + common package imports
- **Dedicated**: Worker-specific snapshot (add `python_dedicated_snapshot` flag)

Performance: ~1s with snapshots (down from ~10s without). Still ~20x slower than JS Workers (~50ms).

## Project Structure

```
project-root/
├── src/
│   ├── main.py              # Worker entrypoint (fetch/scheduled/queue handlers)
│   ├── models.py            # Type definitions, domain models
│   ├── wrappers.py          # JS/Python FFI boundary layer
│   ├── config.py            # Configuration getters from env
│   └── ...                  # Feature modules
├── tests/
│   ├── unit/                # Fast tests with mock bindings (~1s)
│   ├── integration/         # End-to-end flows with mock bindings (~2s)
│   └── e2e/                 # Against live Cloudflare infrastructure
├── migrations/              # D1 SQL migration files
├── assets/                  # Static files (CSS, JS, images)
├── templates/               # Jinja2 HTML templates (if doing SSR)
├── scripts/                 # Build, deploy, seed scripts
├── wrangler.jsonc           # Cloudflare Workers configuration
├── pyproject.toml           # Python dependencies
├── Makefile                 # Dev commands (test, lint, deploy)
└── package.json             # Node deps (just wrangler)
```

**Important**: When `main = "src/main.py"`, import sibling modules as `from models import ...` (NOT `from src.models import ...`). The `src/` directory is the import root.

## The `workers` Module

| Export | Purpose |
|--------|---------|
| `WorkerEntrypoint` | Base class for Worker entrypoint (has `fetch`, `scheduled`, `queue`) |
| `DurableObject` | Base class for Durable Object classes |
| `WorkflowEntrypoint` | Base class for Workflow definitions |
| `Response` | Python-friendly wrapper around JS Response |
| `Request` | Type hint for the request parameter |
| `fetch` | Python wrapper for the JS `fetch()` API |

## Handler Types

A single `WorkerEntrypoint` class can handle all three trigger types:

| Handler | Trigger | Signature |
|---------|---------|-----------|
| `fetch` | HTTP request | `async def fetch(self, request)` |
| `scheduled` | Cron trigger | `async def scheduled(self, controller)` |
| `queue` | Queue message batch | `async def queue(self, batch)` |

```python
class Default(WorkerEntrypoint):
    async def fetch(self, request):
        """HTTP requests — serve web pages, API endpoints."""
        return Response("Hello!")

    async def scheduled(self, controller):
        """Cron triggers — periodic tasks like feed scheduling."""
        await self.env.QUEUE.send({"action": "refresh"})

    async def queue(self, batch):
        """Queue consumer — process enqueued work."""
        for msg in batch.messages:
            body = msg.body.to_py()
            await self.process(body)
            msg.ack()
```

## Supported Packages

- **Pure Python packages** from PyPI
- **Pyodide packages** (compiled to WebAssembly): numpy, pandas, pillow, matplotlib, etc.
- Only **async** HTTP clients: `httpx`, `aiohttp` (NOT `requests`, `urllib3`)
- Full list: https://pyodide.org/en/stable/usage/packages-in-pyodide.html

## Python Standard Library

Full stdlib available **except**:
- **Not functional**: `multiprocessing`, `threading`, `socket` (can import, won't work)
- **Cannot import**: `pty`, `tty` (depend on removed `termios`)
- **Limited**: `decimal` (C impl only), `webbrowser` (unavailable)
- **Excluded**: `curses`, `dbm`, `tkinter`, `venv`, `idlelib`, and other OS-specific modules

## Primary Use Cases

- HTTP APIs and web applications
- Feed/content aggregation with scheduled processing
- AI/ML pipelines (embeddings, inference, RAG search)
- Queue-driven async data processing
- Full-stack SSR apps (Jinja2, FastAPI)
- Durable stateful objects (chat, counters, coordination)

## Official Resources

- [Python Workers Overview](https://developers.cloudflare.com/workers/languages/python/)
- [Python Workers Basics](https://developers.cloudflare.com/workers/languages/python/basics/)
- [How Python Workers Work](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/)
- [Python Packages](https://developers.cloudflare.com/workers/languages/python/packages/)
- [Python FFI](https://developers.cloudflare.com/workers/languages/python/ffi/)
- [Python Workflows](https://developers.cloudflare.com/workflows/python/)
- [pywrangler CLI](https://github.com/cloudflare/workers-py)
- [Python Workers Examples](https://github.com/cloudflare/python-workers-examples)
- [Pyodide Package List](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)
