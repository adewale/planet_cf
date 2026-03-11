# Resource Management Audit Report

**Date:** 2026-03-11
**Scope:** `src/` (16 modules) and `scripts/` (10 scripts)
**Categories:** File handles, network connections, subprocesses, event listeners, temporary files

---

## Executive Summary

The codebase has strong resource management overall. The `src/` modules are clean -- the
Cloudflare Workers runtime has no filesystem, and all HTTP, database, queue, and AI
operations are delegated through well-structured wrapper classes in `wrappers.py`. The
`scripts/` directory has four actionable findings, all low severity, concentrated in
CLI seeding tools.

**Findings:** 4 actionable issues (0 critical, 0 high, 2 medium, 2 low)

---

## Findings

### 1. [MEDIUM] `scripts/seed_test_data.py` -- httpx.Client not using context manager

**Location:** `scripts/seed_test_data.py`, lines 181-187

```python
client = httpx.Client(base_url=base_url, timeout=120.0)
response = client.post(
    "/admin/reindex",
    cookies={"session": session_value},
    follow_redirects=True,
)
client.close()
```

**Issue:** If `client.post()` raises an exception, `client.close()` is never called.
The outer `try/except` on line 180 catches the exception but does not close the client.
The connection pool leaks until process exit.

**Fix:** Use a context manager:
```python
with httpx.Client(base_url=base_url, timeout=120.0) as client:
    response = client.post(...)
```

---

### 2. [MEDIUM] `scripts/convert_planet.py` -- requests.Session never closed

**Location:** `scripts/convert_planet.py`, line 127

```python
class PlanetConverter:
    def __init__(self, source_url: str, name: str, output_dir: Path):
        ...
        self.session = requests.Session()
```

**Issue:** `requests.Session` is created in `__init__` and used throughout the class
but is never explicitly closed. There is no `__del__`, `close()` method, or context
manager support. The session's connection pool (with keep-alive connections) leaks until
garbage collection or process exit.

**Fix:** Add a `close()` method and call it from `main()`, or make the class a context
manager:
```python
def close(self):
    self.session.close()

def __enter__(self):
    return self

def __exit__(self, *args):
    self.close()
```

---

### 3. [LOW] Module-level sqlite3 connections never closed (3 scripts)

**Locations:**
- `scripts/seed_admins.py`, line 22
- `scripts/seed_feeds_from_opml.py`, line 41
- `scripts/seed_test_data.py`, line 39

```python
_quote_conn = sqlite3.connect(":memory:")
```

**Issue:** Each script creates a module-level in-memory SQLite connection for `sql_quote()`
that is never closed. These are in-memory databases used solely for the `SELECT quote(?)`
utility, so no data is at risk, but the connections persist for the process lifetime.

**Impact:** Negligible in practice. These are short-lived CLI scripts and the connections
are cleaned up at process exit. The pattern is defensible for its purpose (safe SQL string
quoting without pulling in a library).

**Optional fix:** Use `atexit.register(_quote_conn.close)` or refactor `sql_quote()` to
open/close per call (minor perf cost).

---

### 4. [LOW] `src/wrappers.py` -- timeout_seconds parameter ignored in Pyodide path

**Location:** `src/wrappers.py`, lines 400-438

```python
async def safe_http_fetch(
    url: str,
    ...
    timeout_seconds: int = _DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> HttpResponse:
    if HAS_PYODIDE:
        # timeout_seconds is NOT passed to js_fetch
        js_response = await js_fetch(url, fetch_options)
    else:
        # timeout IS used
        async with httpx.AsyncClient(timeout=timeout_seconds, ...) as client:
```

**Issue:** The `timeout_seconds` parameter is accepted but only applied in the httpx
(test) code path. In production (Pyodide), `js_fetch` is called without any timeout.
This is not a resource leak per se, but it means a hung upstream server could block a
Worker indefinitely. The caller (`main.py`) mitigates this with `asyncio.wait_for()`
wrapping entire feed-processing operations, but individual HTTP calls within a
processing flow have no per-call timeout in production.

**Impact:** Low -- the outer `asyncio.wait_for()` timeout in `main.py` provides a
wall-time safety net, but individual hung requests within that window are not killed
independently.

**Note:** Cloudflare Workers' `fetch()` has its own internal timeout behavior (typically
30s for subrequests), which provides an implicit backstop not visible at the Python level.

---

## Non-Issues (Verified Clean)

### File Handles

- **`src/` modules:** No file I/O. Workers has no filesystem; templates are compiled
  into `src/templates.py` at build time.
- **`scripts/`:** All file reads use `Path.read_text()` / `Path.read_bytes()` (implicit
  close) or `with open(...)` context managers. No leaked file handles found.

### Network Connections (src/)

- **`wrappers.py` test path:** Uses `async with httpx.AsyncClient(...)` -- proper cleanup.
- **`wrappers.py` Pyodide path:** Uses `js_fetch` which returns a JS Response object.
  The Workers runtime manages the underlying connection.
- **SafeD1, SafeAI, SafeVectorize, SafeQueue:** Thin wrappers around JS bindings. The
  Workers runtime owns connection lifecycle.
- **`verify_deployment.py`:** Uses `with urllib.request.urlopen(...)` -- proper cleanup.
- **`visual_compare.py`:** Uses `async with async_playwright()` and explicit
  `await context.close()` / `await browser.close()` -- proper cleanup.

### Subprocesses

- All subprocess usage across scripts uses `subprocess.run()` which blocks until
  completion and cleans up the child process. No `Popen` objects left unwaited.
- Scripts checked: `seed_admins.py`, `seed_feeds_from_opml.py`, `seed_test_data.py`,
  `validate_deployment_ready.py`.

### Event Listeners / Handlers

- **Module-level logger handlers** in `src/observability.py` (lines 39-46) and
  `src/utils.py` (lines 36-42): Both register a `StreamHandler` once at import time
  with a guard (`if not logger.handlers`). Handlers are never removed. This is correct
  for the Workers model where each isolate has a short lifecycle.
- No other event listeners or signal handlers found.

### Temporary Files

- **`scripts/seed_feeds_from_opml.py`:** Creates `tempfile.NamedTemporaryFile(delete=False)`
  for OPML downloads, with cleanup in a `finally` block via `os.unlink(temp_file)`.
  Verified correct.
- No other temporary files created anywhere in the codebase.

### Context Managers (src/)

- **`src/admin_context.py`:** `admin_action_context()` is an `asynccontextmanager` with
  `try/finally` ensuring event emission. The `Timer` object's `__enter__`/`__exit__` are
  called directly (not via `with`) but within the `try/finally` -- safe.
- **`src/observability.py`:** `Timer` class implements `__enter__`/`__exit__` correctly.

---

## Recommendations

| Priority | Action | File |
|----------|--------|------|
| Medium | Use `with httpx.Client(...) as client:` context manager | `scripts/seed_test_data.py:181` |
| Medium | Add `close()` or context manager to `PlanetConverter` | `scripts/convert_planet.py:127` |
| Low | Consider `atexit` cleanup for module-level SQLite connections | 3 seed scripts |
| Low | Document that `timeout_seconds` is test-only in Pyodide path | `src/wrappers.py:400` |
