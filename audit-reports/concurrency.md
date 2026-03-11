# Concurrency Audit Report -- Planet CF

**Date:** 2026-03-11
**Scope:** All 17 files in `src/` (async Python on Cloudflare Workers/Pyodide)
**Auditor:** Claude Opus 4.6

---

## Executive Summary

Planet CF runs on Cloudflare Workers' Python (Pyodide) runtime, which uses a
**single-threaded event loop per isolate**. There are no threads and no true
OS-level parallelism within one isolate. This dramatically reduces the attack
surface for classical concurrency bugs. The codebase does not use
`asyncio.gather`, `asyncio.create_task`, threading, or any explicit locks.

That said, several issues arise from **cross-request shared state within an
isolate**, **cross-isolate races against D1** (which is a shared external
database), and **check-then-act patterns** that span multiple await points.

**Severity scale:** CRITICAL > HIGH > MEDIUM > LOW > INFO

### Findings Summary

| # | Severity | Category | Location |
|---|----------|----------|----------|
| 1 | MEDIUM | Shared mutable state | `_db_initialized` class attribute |
| 2 | MEDIUM | Shared mutable state | `_router` / `_cached_safe_env` class attributes |
| 3 | MEDIUM | Atomicity gap | Scheduler feed recovery: read-then-update-then-enqueue |
| 4 | LOW | Atomicity gap (TOCTOU) | Reindex cooldown check |
| 5 | LOW | Cross-isolate race | Retention policy deleting entries being read |
| 6 | LOW | Shared mutable state | `_compiled_patterns` dict on RouteDispatcher |
| 7 | INFO | Module-level singleton | `_sanitizer = BleachSanitizer()` |
| 8 | INFO | Logger setup guard | `if not logger.handlers` |
| 9 | INFO | Absent concern | No task leaks or deadlock risk |

---

## Detailed Findings

### Finding 1: `_db_initialized` Class-Level Flag (MEDIUM)

**File:** `src/main.py`, line 359

```python
class Default(WorkerEntrypoint):
    _db_initialized: bool = False  # Class attribute shared across instances
```

**Race scenario:** `_db_initialized` is a **class attribute**, not an instance
attribute. On Cloudflare Workers, the same isolate may handle multiple requests
concurrently via the event loop. Two requests arriving simultaneously on a cold
isolate both enter `_ensure_database_initialized()`:

1. Request A checks `self._db_initialized` -- sees `False`
2. Request A begins `await self.env.DB.prepare(...)` -- yields to event loop
3. Request B checks `self._db_initialized` -- still `False` (not yet set)
4. Request B also begins the same DB check
5. Both run the schema creation / drift check concurrently

**Impact:** Low in practice because `CREATE TABLE IF NOT EXISTS` and
`PRAGMA table_info` are idempotent, and D1's SQLite serializes writes. The
real cost is redundant I/O on cold start. However, setting the flag in the
`except` block (line 472) means a failed init permanently skips retries for
the **entire isolate lifetime**, even if the D1 error was transient.

**Recommendation:** Convert to an instance attribute set in `__init__` or use
a sentinel tri-state (`None` / initializing / done) to avoid double work and
distinguish permanent vs. transient failures.

---

### Finding 2: `_router` and `_cached_safe_env` Class Attributes (MEDIUM)

**File:** `src/main.py`, lines 305-306

```python
class Default(WorkerEntrypoint):
    _cached_safe_env: SafeEnv | None = None
    _router: RouteDispatcher | None = None
```

**Race scenario:** These are class-level attributes. If the Cloudflare Workers
runtime creates multiple `Default` instances sharing the same class object
(unlikely but not contractually excluded by the runtime), mutations via
`object.__setattr__(self, ...)` on one instance would shadow the class
attribute on that instance. But `_create_router()` at line 1369 reads
`self._router` then writes `self._router` -- if two concurrent requests both
see `None` before the first completes, two routers are created and the last
write wins.

**Impact:** Harmless because `RouteDispatcher` is stateless after
construction -- the extra allocation is wasted work, not a bug. Similarly,
`_cached_safe_env` is per-request env-dependent and correctly invalidated
by the setter.

**Recommendation:** Declare these as instance attributes in `__init__` (or
use `__init_subclass__`) rather than class attributes to eliminate any
ambiguity about sharing across instances.

---

### Finding 3: Scheduler Feed Recovery -- Read-Update-Enqueue Gap (MEDIUM)

**File:** `src/main.py`, lines 643-687

```python
# 1. Read disabled feeds
disabled_result = await self.env.DB.prepare("""
    SELECT id, url, ... FROM feeds WHERE is_active = 0 ...
""").all()

# 2. For each: re-enable in DB
await self.env.DB.prepare("""
    UPDATE feeds SET is_active = 1, consecutive_failures = 0, ...
    WHERE id = ?
""").bind(feed["id"]).run()

# 3. Enqueue for fetch
await self.env.FEED_QUEUE.send({...})
```

**Race scenario:** Between steps 1 and 2, a concurrent scheduler run (from
another isolate, or a manual `_trigger_regenerate` call from the admin UI)
could also select the same disabled feeds and attempt to re-enable them. Both
isolates would:

- Re-enable the same feed (harmless, idempotent UPDATE)
- **Enqueue the same feed twice** in the queue

The feed would then be fetched concurrently by two queue consumers, doubling
I/O and potentially producing duplicate entry upserts (though `ON CONFLICT`
prevents data duplication).

**Impact:** Wasted resources (double fetches) and noisy observability events.
Not a data corruption bug because the DB upsert is idempotent.

**Recommendation:** Use an atomic `UPDATE ... WHERE is_active = 0 RETURNING`
to claim feeds in a single statement, eliminating the read-then-update gap.
Only enqueue feeds that were actually updated (RETURNING gives you the rows).

---

### Finding 4: Reindex Cooldown TOCTOU (LOW)

**File:** `src/main.py`, lines 3389-3408

```python
# Check: When was the last reindex?
last_reindex = await self.env.DB.prepare("""
    SELECT created_at FROM audit_log WHERE action = 'reindex' ...
""").first()

# ... time passes (other awaits) ...

# Act: Perform the reindex (no second check)
for entry in entries:
    await self._index_entry_for_search(...)

# Log to audit_log
await ctx.log_action(admin["id"], "reindex", ...)
```

**Race scenario:** Two admins click "Reindex" nearly simultaneously from
different browsers. Both check the audit_log, both see the cooldown has
elapsed, both proceed. The audit_log entry from the first reindex is only
written after it completes, so the second reindex's cooldown check will not
see it.

**Impact:** Two concurrent reindex operations run against Vectorize,
wasting AI embedding calls and potentially causing rate limiting from the
Workers AI API. Not a data integrity issue.

**Recommendation:** Insert a sentinel audit_log row at the start of the
reindex (before the loop), or use a D1-based advisory lock (e.g.,
`INSERT OR IGNORE INTO reindex_lock ...`).

---

### Finding 5: Retention Policy vs. Concurrent Reads (LOW)

**File:** `src/main.py`, lines 1878-1973

**Race scenario:** The retention policy runs during the scheduler cron. It
queries entry IDs to delete, then deletes vectors, then deletes D1 rows in
batches of 50. Between the ID query and the DELETE, a concurrent `fetch()`
request serving the homepage could read those same entries from D1 and render
them into HTML. The user sees entries that are being deleted.

Additionally, the vector delete (Vectorize) and D1 delete are not atomic.
If vector deletion succeeds but D1 deletion fails partway, orphaned entries
exist in D1 without corresponding vectors. Conversely, if D1 deletion
succeeds but Vectorize fails, orphaned vectors exist.

**Impact:** Transient UX inconsistency (user sees an entry that disappears
on next page load). The orphan scenario is handled gracefully -- search
results simply won't find entries without vectors, and entries without
matching search results just lack semantic search capability.

**Recommendation:** Acceptable as-is. The code already handles Vectorize
errors gracefully (line 1946-1954) and continues with D1 deletion.

---

### Finding 6: `_compiled_patterns` Dict on RouteDispatcher (LOW)

**File:** `src/route_dispatcher.py`, lines 138, 157-168

```python
class RouteDispatcher:
    def __init__(self, routes):
        self._compiled_patterns: dict[str, re.Pattern] = {}

    def _compile_pattern(self, pattern: str) -> re.Pattern:
        if pattern in self._compiled_patterns:
            return self._compiled_patterns[pattern]
        compiled = re.compile(regex)
        self._compiled_patterns[pattern] = compiled
        return compiled
```

**Race scenario:** If two concurrent requests both try to compile the same
pattern for the first time, both see a cache miss, both compile, and both
write. The last write wins but both produce identical values, so no
corruption occurs.

**Impact:** None. The cache is a performance optimization; double compilation
produces identical `re.Pattern` objects.

**Recommendation:** None needed. This is a standard benign race for caches.

---

### Finding 7: Module-Level `_sanitizer` Singleton (INFO)

**File:** `src/main.py`, line 219

```python
_sanitizer = BleachSanitizer()
```

`BleachSanitizer` holds only class-level constants (`ALLOWED_TAGS`,
`ALLOWED_ATTRS`, `ALLOWED_PROTOCOLS`) and its `clean()` method uses only
local variables plus the `bleach.clean()` library call. It is effectively
stateless and thread-safe.

**Impact:** None.

---

### Finding 8: Logger Handler Guard (INFO)

**Files:** `src/utils.py` line 37, `src/observability.py` line 39

```python
if not logger.handlers:
    handler = logging.StreamHandler()
    ...
    logger.addHandler(handler)
```

In a multi-threaded Python runtime, this check-then-add pattern could add
duplicate handlers. However, Pyodide is single-threaded and module-level code
executes only once during import. Additionally, both modules use different
logger names (`src.main` vs `__name__`), so they do not conflict.

**Impact:** None in the Pyodide runtime.

---

### Finding 9: No Task Leaks or Deadlock Risk (INFO)

The codebase does not use `asyncio.create_task()`, `asyncio.gather()`, or
`asyncio.ensure_future()`. All async work is sequential within each handler
(scheduled, queue, fetch). The only concurrency primitive used is
`asyncio.wait_for()` (lines 827, 3254), which is used correctly as an
inline timeout wrapper that is immediately awaited.

There are no locks in the codebase, so deadlock is impossible.

There is no background work spawned and left unjoined.

---

## Cross-Isolate Considerations

Cloudflare Workers can run multiple isolates globally. The following D1
operations rely on database-level atomicity, which D1 (SQLite) provides:

1. **Entry upsert** (`ON CONFLICT(feed_id, guid) DO UPDATE`): Atomic. Two
   isolates processing the same feed entry will both succeed; the last write
   wins with identical data.

2. **Feed error recording** (`consecutive_failures = consecutive_failures + 1`
   with `CASE WHEN consecutive_failures + 1 >= ?`): This is a single atomic
   SQL statement. The code at line 1228-1237 correctly handles the "new value"
   semantics by checking `consecutive_failures + 1` in the CASE expression,
   avoiding the stale-read race that would occur if the check and increment
   were separate statements.

3. **Feed URL update after redirect**: The URL update and audit log insert
   are two separate statements (lines 1280-1300). If the update succeeds but
   the audit log insert fails, the URL is updated without an audit trail.
   This is acceptable for an operational concern like URL following.

---

## Architecture Assessment

The codebase is well-suited for the Cloudflare Workers concurrency model:

- **No shared mutable state across requests** (except the benign
  `_db_initialized` flag and route cache)
- **All external state is in D1** with proper SQL atomicity (`ON CONFLICT`,
  single-statement `UPDATE ... RETURNING`)
- **No fire-and-forget tasks** -- all async work is awaited inline
- **Queue processing is one-message-at-a-time** per feed, giving natural
  isolation

The main class of risks is **cross-isolate TOCTOU against D1**, which is
inherent to any distributed system using a shared database. The existing
mitigations (idempotent upserts, atomic UPDATE+CASE) are appropriate.

---

## Recommendations (Priority Order)

1. **(MEDIUM) Fix scheduler feed recovery** to use `UPDATE ... WHERE
   is_active = 0 RETURNING` instead of SELECT-then-UPDATE, preventing
   double-enqueue from concurrent scheduler runs.

2. **(MEDIUM) Convert `_db_initialized` to instance attribute** and
   distinguish transient vs. permanent init failures so a transient D1 error
   doesn't permanently skip initialization for the isolate's lifetime.

3. **(LOW) Add reindex advisory lock** via a sentinel audit_log row inserted
   before the reindex loop begins, to prevent concurrent reindex operations.

4. **(LOW) Convert `_router` and `_cached_safe_env` to instance attributes**
   for clarity, even though the current behavior is benign.
