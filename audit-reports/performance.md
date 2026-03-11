# Performance Audit Report

**Date:** 2026-03-11
**Scope:** Static analysis of `src/` (17 modules) for patterns that degrade latency, memory, or throughput under load.

---

## Critical Findings

### 1. N+1 Database Queries in `_upsert_entry` Loop

**File:** `src/main.py`, lines 978-1010
**Impact:** Latency -- O(n) sequential awaits to D1 per feed fetch; dominant wall-time contributor.

When processing a feed, `_process_single_feed` iterates over every entry and calls `_upsert_entry` one at a time. Each `_upsert_entry` issues:

1. An `INSERT ... ON CONFLICT ... RETURNING id` query (line 1031)
2. A `UPDATE feeds SET last_entry_at ...` query (line 1065) for every successfully inserted entry
3. An `_index_entry_for_search` call that does an AI embedding + Vectorize upsert (lines 1080-1081)

For a feed with 20 entries, that is **40+ sequential D1 round-trips** plus 20 AI calls -- all awaited in series. D1 does not support multi-statement batching within a single `.prepare()`, but the `last_entry_at` update (item 2) could be done once after the loop using the latest `published_at` rather than once per entry.

**Recommendation:**
- Move the `UPDATE feeds SET last_entry_at` out of the per-entry loop; track the maximum `published_at` across entries and issue a single update after the loop.
- Investigate D1 batch API (`db.batch([stmt1, stmt2, ...])`) to batch the entry upserts.

---

### 2. N+1 Queue Sends in Scheduler

**File:** `src/main.py`, lines 622-634
**Impact:** Latency on cron -- sequential `await FEED_QUEUE.send()` for every active feed.

The scheduler enqueues each active feed one at a time in a `for` loop. With 50 feeds, that is 50 sequential awaits. Cloudflare Queues supports `sendBatch` for up to 100 messages per call.

A second occurrence is the feed recovery loop (lines 656-680) which issues both a D1 UPDATE and a queue send per disabled feed, sequentially.

**Recommendation:**
- Collect messages into a list, then send them with a single `sendBatch` call (or batches of 100).

---

### 3. Regex Recompilation on Every Sanitize Call (`BleachSanitizer.clean`)

**File:** `src/models.py`, lines 319-361
**Impact:** CPU/latency -- 5 `re.sub()` calls with inline patterns per entry, every call recompiles.

`BleachSanitizer.clean()` is called once per entry during feed processing (via `_sanitize_html`). It uses five `re.sub()` calls with raw string patterns:

```python
html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
cleaned = re.sub(r'<a\s+href="(https?://[^"]+)"([^>]*)>', ..., cleaned, flags=re.IGNORECASE)
cleaned = re.sub(r'\s*href="[^"]*javascript:[^"]*"', "", cleaned, flags=re.IGNORECASE)
cleaned = re.sub(r"<img\s+[^>]*>", add_img_attrs, cleaned, flags=re.IGNORECASE)
```

Python's `re` module does cache recently compiled patterns internally (up to `_MAXCACHE = 512`), so in practice these will be served from the module-level LRU cache after the first call. However, each cache lookup still incurs a hash + dict lookup per call. More importantly, `import re` and `import bleach` are done **inside the method body** on every call. In Pyodide, repeated `import` lookups are more expensive than in CPython because the module system has additional overhead.

**Recommendation:**
- Pre-compile the five regex patterns as module-level constants (like `xml_sanitizer.py` already does correctly).
- Move the `import re` and `import bleach` to the top of `models.py` (module-level).

---

### 4. Regex Recompilation in `normalize_entry_content`

**File:** `src/utils.py`, lines 156-165
**Impact:** CPU -- a complex multi-group regex is compiled on every call.

`normalize_entry_content` is called once per entry during HTML generation (line 1764 of `main.py`). The regex pattern is a multi-line, multi-group pattern that is passed to `re.match()` with the raw string each time. With 500 entries on the homepage, that is 500 pattern lookups against Python's internal regex cache.

**Recommendation:**
- Pre-compile the pattern as a module-level `_HEADING_RE = re.compile(...)` constant.

---

### 5. Redundant `_get_planet_config` and `_get_theme` Calls per Request

**File:** `src/main.py` (grep count: ~20 calls to `_get_planet_config`, ~18 calls to `_get_theme`)
**Impact:** Minor latency -- repeated `getattr()` + string operations per request.

Within a single request, `_get_planet_config()` and `_get_theme()` are called multiple times (e.g., in `_generate_html`, `_serve_atom`, `_search_entries`, error handlers). Each call does `getattr(self.env, ...)` lookups against the underlying JS environment object. While individually cheap, on the search path this adds up: `_search_entries` calls `_get_planet_config()` up to 4 times and `_get_theme()` up to 4 times in the various error branches + final render.

The theme check also includes a `_log_op("theme_not_found", ...)` call with a dict lookup against `_EMBEDDED_TEMPLATES` on every invocation.

**Recommendation:**
- Cache `planet` and `theme` at the top of each request handler method and pass them down, rather than re-reading from env on each use. The `_generate_html` method already partially does this (line 1601, 1821) but the search method does not.

---

## Moderate Findings

### 6. Sequential Feed Recovery: N Updates + N Queue Sends

**File:** `src/main.py`, lines 656-687
**Impact:** Latency in cron -- each disabled feed gets a sequential `UPDATE` + `send`.

For `feed_recovery_limit` disabled feeds (default 2), the scheduler issues:
- One `UPDATE feeds SET is_active = 1, ...` per feed
- One `FEED_QUEUE.send(...)` per feed

With the default limit of 2 this is negligible, but if increased, it becomes a bottleneck. The recovery limit is configurable via env var.

**Recommendation:**
- Batch the updates into a single `UPDATE ... WHERE id IN (...)` statement.

---

### 7. Full Table Scan in `_view_feed_health` Correlated Subquery

**File:** `src/main.py`, lines 3322-3346
**Impact:** Throughput -- `(SELECT COUNT(*) FROM entries e WHERE e.feed_id = f.id)` is a correlated subquery executed once per feed row.

This runs for every feed in the health dashboard. With 50 feeds and 5000 entries, the database executes 50 index lookups. While D1/SQLite handles this reasonably with the `idx_entries_feed` index, the approach does not scale if the entries table grows large.

**Recommendation:**
- Replace with a single `GROUP BY feed_id` join or CTE.

---

### 8. `_check_schema_drift` Runs PRAGMA Per Table on First Request

**File:** `src/main.py`, lines 530-559
**Impact:** First-request latency -- 4 sequential `PRAGMA table_info()` queries.

On the first request to a worker isolate, if the database is already initialized, `_check_schema_drift` runs `PRAGMA table_info(...)` for each of the 4 tables (`feeds`, `entries`, `admins`, `audit_log`). These are sequential awaits.

This only runs once per isolate lifetime, so the impact is limited to cold starts. Given Pyodide already has a ~2-3s cold start, these extra 4 D1 round-trips add to the first-request latency.

**Recommendation:**
- Consider making schema drift checking opt-in (e.g., only when a `DEBUG_SCHEMA_CHECK` env var is set), or run it in the scheduler instead of on first HTTP request.

---

### 9. Unbatched Retention Deletion

**File:** `src/main.py`, lines 1959-1968
**Impact:** Latency during cron -- retention deletes entries in batches of 50, but each batch is a sequential await.

The retention policy deletes entries in batches of 50 via:
```python
for i in range(0, len(deleted_ids), 50):
    batch = deleted_ids[i : i + 50]
    ...
    await self.env.DB.prepare(f"DELETE FROM entries WHERE id IN ({placeholders})").bind(*batch).run()
```

With 500 entries to delete, that is 10 sequential D1 calls. The Vectorize deletion is done in a single call (line 1944), so only the D1 side is batched.

**Recommendation:**
- Increase batch size (D1 supports up to 100 bind parameters per statement).
- Alternatively, use a subquery: `DELETE FROM entries WHERE id IN (SELECT id FROM ...)` to do it in one statement.

---

### 10. `D1Result` Class Created on Every `.all()` Call

**File:** `src/wrappers.py`, lines 289-297
**Impact:** Minor memory/GC pressure -- a new class definition is created inside the method body on every call.

`SafeD1Statement.all()` defines a `D1Result` class inside the method on every invocation. In CPython this would be cached, but in Pyodide the class object is recreated each time.

```python
async def all(self) -> Any:
    result = await self._stmt.all()
    class D1Result:  # New class created each call
        def __init__(self, results, success):
            ...
    return D1Result(...)
```

**Recommendation:**
- Move `D1Result` to module level as a `@dataclass` or `namedtuple`.

---

## Low-Impact Observations

### 11. `get_iso_timestamp()` Called on Every Log Line

**File:** `src/utils.py`, line 50
**Impact:** Negligible CPU -- `datetime.now(timezone.utc).isoformat()` plus a `.replace()` on every `log_op()` call.

This is standard practice and the overhead is minimal. No action needed.

### 12. `_to_py_safe` Recursion is Bounded

**File:** `src/wrappers.py`, line 115
**Impact:** None -- `_MAX_CONVERSION_DEPTH = 50` provides an explicit recursion guard. Good defensive coding.

### 13. `xml_sanitizer.py` Pre-compiles Its Regex

**File:** `src/xml_sanitizer.py`, line 28
**Impact:** Positive example -- `_ILLEGAL_XML_CHARS_RE` is compiled once at module level. This is the correct pattern that should be replicated in `models.py` and `utils.py`.

### 14. `RouteDispatcher._compile_pattern` Caches Compiled Patterns

**File:** `src/route_dispatcher.py`, lines 148-169
**Impact:** Positive example -- patterns are cached in `self._compiled_patterns` dict. No redundant compilation.

### 15. Edge Cache Pre-Warming Fires Sequentially

**File:** `src/main.py`, lines 741-748
**Impact:** Minor latency in cron -- 4 sequential `safe_http_fetch` calls for cache warming.

The scheduler pre-warms `/`, `/titles`, `/feed.atom`, `/feed.rss` sequentially. These could be fired concurrently with `asyncio.gather()`.

**Recommendation:**
- Use `asyncio.gather()` to parallelize the 4 fetch calls.

---

## Summary Table

| # | Finding | Category | Impact | Effort |
|---|---------|----------|--------|--------|
| 1 | N+1 DB queries in `_upsert_entry` loop | N+1 queries | **High** (latency) | Medium |
| 2 | N+1 queue sends in scheduler | N+1 queries | **High** (cron latency) | Low |
| 3 | Regex recompilation + inline imports in `BleachSanitizer.clean` | Hot-path alloc | **Medium** (CPU) | Low |
| 4 | Regex recompilation in `normalize_entry_content` | Hot-path alloc | **Medium** (CPU) | Low |
| 5 | Redundant `_get_planet_config`/`_get_theme` per request | Unnecessary work | **Low** (latency) | Low |
| 6 | Sequential feed recovery updates | N+1 queries | Low | Low |
| 7 | Correlated subquery in feed health | Unnecessary work | Low | Low |
| 8 | Schema drift check on first request | Blocking event loop | Low | Low |
| 9 | Unbatched retention deletion | N+1 queries | Low | Low |
| 10 | `D1Result` class created per call | Hot-path alloc | Low | Low |
| 15 | Sequential cache pre-warming | Unnecessary work | Low | Low |

---

## What Was NOT Found

- **Unbounded growth / missing eviction:** No in-memory caches or growing lists were found. The `_compiled_patterns` dict in `RouteDispatcher` is bounded by the number of routes (fixed at deploy time). The sanitizer is a module-level singleton with no state accumulation.
- **Blocking I/O in async context:** All I/O operations use `await`. No synchronous file reads or blocking calls were found in async paths.
- **Missing awaits:** All coroutine calls are properly awaited. No fire-and-forget patterns were found.
- **String concatenation in loops:** No `+=` string building in loops. The codebase uses list comprehensions and template rendering instead.
