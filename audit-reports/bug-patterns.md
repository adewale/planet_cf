# Bug Pattern Audit Report

**Date:** 2026-03-11
**Scope:** All 17 files in `src/` (~3700 LOC)
**Auditor:** Claude Opus 4.6

---

## 1. Type Coercion Surprises

### 1.1 `get_config_value` treats `0` as falsy, returns default instead

**File:** `src/config.py:85`
```python
return value_type(value) if value else default
```

**What goes wrong:** If an operator intentionally sets an environment variable to `0` (e.g., `FEED_TIMEOUT_SECONDS=0` to disable timeouts, or `SEARCH_TOP_K=0`), the `if value` check treats `0` as falsy and silently returns the default instead. The integer `0` is a valid value that should be passed to `value_type()`, but it is discarded.

**Fix:** Change to `if value is not None`.

**Severity:** Medium -- most configs make no sense at 0, but `FEED_RECOVERY_LIMIT=0` is a legitimate way to say "don't recover any feeds" and would be ignored.

---

### 1.2 `_safe_str` treats empty string `""` as falsy, returns `None`

**File:** `src/wrappers.py:174`
```python
return str(py_val) if py_val else None
```

**What goes wrong:** If a database column or form field contains the empty string `""`, `_safe_str` returns `None` instead of `""`. This means any legitimate empty-string value (e.g., an author field explicitly set to `""`) silently becomes `None`, which then flows into D1 binds. Since `entry_bind_values` and `feed_bind_values` use `_safe_str`, empty strings in feed metadata become SQL NULLs -- subtly different from empty strings for queries like `WHERE author IS NOT NULL`.

**Fix:** Change to `return str(py_val) if py_val is not None else None`.

**Severity:** Low -- empty strings and NULLs are treated similarly in most of the codebase, but it violates the boundary layer's contract of lossless conversion.

---

### 1.3 `_to_py_safe` converts digit-only strings to integers

**File:** `src/wrappers.py:152-155`
```python
str_val = str(value)
if str_val.isdigit():
    return int(str_val)
return str_val
```

**What goes wrong:** This is the "last resort" fallback in `_to_py_safe`. If a JsProxy value's string representation happens to be all digits (e.g., a string identifier like `"000123"`), it is silently converted to `int(123)`, losing the leading zeros and changing the type. This also converts any string that looks numeric (e.g., zip codes, numeric GUIDs) into integers.

**Severity:** Low -- this only fires for JsProxy values that cannot be converted via `to_py()`, which is a rare edge case.

---

### 1.4 `feed_row_from_js` returns empty dict `{}` on falsy row

**File:** `src/wrappers.py:517-518`
```python
if not py_row:
    return {}
```

**What goes wrong:** If `_to_py_safe(row)` returns `0`, `""`, or an empty list `[]`, the `not py_row` check treats these as falsy and returns `{}`. Callers like `_remove_feed` check `if not feed:` -- an empty dict `{}` is also falsy, so this works. But `entry_row_from_js` has the same pattern, and callers do `entry_id = result.get("id")` on the empty dict, getting `None`. The inconsistency is that the return type is `dict` but functionally signals "nothing" by returning `{}`, while `admin_row_from_js` returns `None` for the same case. Callers must use different checks depending on which factory they called.

**Severity:** Low -- current callers handle both cases, but it is a latent trap for future code.

---

## 2. Silent Data Loss

### 2.1 OPML import counts conflict-skipped feeds as "imported"

**File:** `src/main.py:3080-3093`
```python
try:
    await (
        self.env.DB.prepare("""
        INSERT INTO feeds (url, title, site_url, is_active)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(url) DO NOTHING
    """)
        .bind(xml_url, title, html_url)
        .run()
    )
    imported += 1
```

**What goes wrong:** The SQL uses `ON CONFLICT(url) DO NOTHING`, meaning if a feed URL already exists, it is silently skipped. But the Python code unconditionally increments `imported += 1` regardless of whether the row was actually inserted. The admin sees "Imported 15 feeds" when perhaps only 3 were new. The `_validate_opml_feeds` helper in `admin.py` does proper dedup, but the `_import_opml` method in `main.py` does not use it.

**Fix:** Check the `run()` result's `meta.changes` property (D1 returns 0 for DO NOTHING) or use `RETURNING id` to determine whether the insert actually happened.

**Severity:** Medium -- misleading user feedback; operator cannot tell if an import actually added feeds.

---

### 2.2 `_upsert_entry` ON CONFLICT does not update `summary`, `author`, or `url`

**File:** `src/main.py:1037-1040`
```python
ON CONFLICT(feed_id, guid) DO UPDATE SET
    title = excluded.title,
    content = excluded.content,
    updated_at = CURRENT_TIMESTAMP
```

**What goes wrong:** When a feed entry is updated (same feed_id + guid), only `title` and `content` are refreshed. The `summary`, `author`, and `url` fields are not updated. If an author corrects a typo in their name, fixes a broken link URL, or updates a summary, those changes are silently dropped on subsequent fetches.

**Severity:** Medium -- real feeds do change these fields, and the system silently ignores the updates.

---

### 2.3 Search indexing failure is silently swallowed

**File:** `src/main.py:1079-1101`
```python
try:
    indexing_stats = await self._index_entry_for_search(...)
except Exception as e:
    # Log but don't fail - entry is still usable without search
    _log_op("search_index_skipped", ...)
```

**What goes wrong:** This is a deliberate design choice (search is optional), but the failure is only logged -- there is no mechanism to retry or track which entries are missing from the search index. Over time, the search index can silently drift from the D1 database, with entries that were added during Vectorize downtime never appearing in search results. The reindex endpoint exists but must be manually triggered.

**Severity:** Low -- design trade-off, but worth noting there is no automatic self-healing.

---

### 2.4 `_log_admin_action` silently drops `None` values from details dict

**File:** `src/main.py:3498-3499`
```python
if v_py is not None:
    safe_details[k] = v_py
```

**What goes wrong:** If an audit log detail intentionally needs to record that a field is `None` (e.g., `{"original_url": None}` when a feed was not redirected), that key is silently removed from the JSON. The audit log entry will have a missing key rather than an explicit null, making it ambiguous whether the field was intentionally null or simply absent.

**Severity:** Low -- defensive coding for the JsProxy boundary, but loses semantic information.

---

## 3. Off-by-One in Boundaries

### 3.1 Reindex cooldown uses audit_log creation time, not completion time

**File:** `src/main.py:3389-3408`
```python
last_reindex = await self.env.DB.prepare("""
    SELECT created_at FROM audit_log
    WHERE action = 'reindex'
    ORDER BY created_at DESC
    LIMIT 1
""").first()
...
elapsed = (datetime.now(timezone.utc) - last_reindex_time).total_seconds()
if elapsed < REINDEX_COOLDOWN_SECONDS:
```

**What goes wrong:** The `created_at` in audit_log is written at the END of the reindex operation (line 3447), not the beginning. If a reindex takes 4 minutes and the cooldown is 5 minutes, the next reindex is available 5 minutes after the LAST one finished, not 5 minutes after it started. So the effective minimum interval is `cooldown + reindex_duration`. This is more conservative than intended.

However, if two requests arrive simultaneously and neither has written an audit_log entry yet, both pass the check and start parallel reindex operations.

**Severity:** Low -- the "too conservative" behavior is safe. The race condition is unlikely but could cause expensive duplicate work.

---

### 3.2 `has_more` pagination indicator is inexact

**File:** `src/main.py:3308`
```python
"has_more": len(entries) == limit,
```

**What goes wrong:** This is the classic "one more" fence-post: if there are exactly 100 audit log entries and the limit is 100, `has_more` is `True` -- the client requests the next page and gets 0 results. Conversely, if there are exactly 100 entries, the response incorrectly signals more pages exist. The correct pattern is to request `limit + 1` rows and check if you got more than `limit`.

**Severity:** Low -- only affects the audit log API, and the worst case is one empty page at the end.

---

### 3.3 Retention policy: entries at exact cutoff boundary may be kept or deleted depending on time precision

**File:** `src/main.py:1904-1906`
```python
cutoff_date = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime(
    "%Y-%m-%d %H:%M:%S"
)
```

And later:
```python
WHERE rn > ?
   OR COALESCE(published_at, first_seen) < ?
```

**What goes wrong:** The comparison uses `<` (strictly less than) against a timestamp with second-precision. An entry whose `published_at` is exactly equal to the cutoff is kept, which is correct. But because `strftime` truncates to seconds while `datetime.now()` has microsecond precision, there is a sub-second window where the cutoff shifts. In practice, this is negligible, but the same cutoff is used in two different places (`_generate_html` and `_apply_retention_policy`) with separate `datetime.now()` calls, meaning they compute slightly different cutoffs. An entry that is "just barely in range" for display might be deleted by retention in the same cron cycle.

**Severity:** Low -- the drift is sub-second, and in practice the retention days buffer (90 days vs 7 days display) prevents overlap.

---

## 4. Serialization Boundary Mismatch

### 4.1 `ParsedEntry.from_feedparser` generates `hash(title)` as GUID -- type becomes `int`

**File:** `src/models.py:103`
```python
guid = entry.get("id") or entry.get("link") or hash(entry.get("title", ""))
```

**What goes wrong:** When neither `id` nor `link` is present, `hash()` returns an integer. This integer is then passed as the GUID. On line 131, it is converted to `str(guid)`, so it becomes a string like `"-4829274822"`. But `hash()` output is non-deterministic across Python processes (due to hash randomization). A feed entry with no id/link would get a different GUID every time the worker cold-starts, causing duplicate entries in the database.

Note: `EntryContentProcessor.generate_guid()` in `content_processor.py` handles this case correctly with SHA256. The `ParsedEntry.from_feedparser` in `models.py` has the bug, but it appears that `EntryContentProcessor` is the one actually used in `_upsert_entry`. The `ParsedEntry` class in `models.py` appears to be dead code or an alternative path.

**Severity:** Low if `ParsedEntry.from_feedparser` is unused in production; High if it is ever called.

---

### 4.2 Queue message schema is implicitly defined, no validation on consumer side

**File:** `src/main.py:623-631` (producer) and `src/main.py:796-804` (consumer)

Producer:
```python
message = {
    "feed_id": feed["id"],
    "url": feed["url"],
    "etag": feed.get("etag"),
    "last_modified": feed.get("last_modified"),
    "scheduled_at": datetime.now(timezone.utc).isoformat(),
    "correlation_id": sched_event.correlation_id,
}
```

Consumer:
```python
feed_url = feed_job.get("url", "unknown")
feed_id = feed_job.get("feed_id", 0)
```

**What goes wrong:** There is no shared schema or validation. The consumer silently defaults to `"unknown"` for URL and `0` for feed_id if keys are missing. If the producer schema changes (e.g., renaming `url` to `feed_url`), the consumer would process every message with `url="unknown"` and `feed_id=0` instead of raising an error. The `FeedJob` dataclass in `models.py` defines the schema but is not used for deserialization.

**Severity:** Medium -- latent. The `FeedJob.from_dict()` method exists but is not used in the queue consumer, meaning schema drift would be silent.

---

## 5. Stale Closures

### 5.1 Lambda in date sorting captures loop variable reference

**File:** `src/main.py:1776-1778`
```python
for date_label in entries_by_date:
    entries_by_date[date_label].sort(
        key=lambda e: e.get("published_at") or "", reverse=True
    )
```

**What goes wrong:** This is actually fine -- the lambda captures `e` from its own parameter, not `date_label`. No stale closure here. Included for completeness of analysis.

**No bug found in stale closures pattern.** The codebase does not use callbacks or closures that capture mutable loop variables. The async patterns use `await` at each step rather than scheduling callbacks. This is a clean pattern.

---

## 6. Shallow Merge / Copy

### 6.1 `_update_feed` builds SQL dynamically from untrusted fields without schema validation

**File:** `src/main.py:2974-2984`
```python
if "is_active" in data:
    is_active = 1 if data["is_active"] else 0
    ...
if "title" in data:
    title = _safe_str(data["title"])
    ...
```

**What goes wrong:** This is not strictly a shallow-merge bug, but it has a related pattern. The `data` dict comes from `request.json()`, and only two fields are recognized (`is_active`, `title`). If a caller sends `{"title": "New", "consecutive_failures": 0}`, the `consecutive_failures` field is silently ignored. This is safe (whitelist approach), but the lack of error feedback means the API appears to accept fields it actually ignores.

**Severity:** None -- the whitelist approach is correct defensive coding.

---

### 6.2 Entry dict mutation during `_generate_html` modifies the list in-place

**File:** `src/main.py:1758-1771`
```python
entry["published_at_display"] = _format_pub_date(group_date)
entry["content"] = _normalize_entry_content(...)
entry["display_author"] = _get_display_author(...)
entries_by_date[date_label].append(entry)
```

**What goes wrong:** The `entry` dicts from `entry_rows_from_d1` are modified in place by adding `published_at_display`, overwriting `content`, and adding `display_author`. These are the same dict objects returned by the row factory. Since `_generate_html` is called once per request and the dicts are not reused, this is not currently a bug. However, if `_generate_html` were ever called twice in the same request (e.g., generating both index and titles pages), the second call would see `content` already normalized, and `_normalize_entry_content` would be applied twice -- potentially stripping content that was not a duplicate heading.

**Severity:** Low -- not currently triggered, but a latent issue if code is refactored to reuse entry data.

---

## 7. Additional Findings

### 7.1 `_export_opml` exports ALL feeds (including inactive) but labels none as inactive

**File:** `src/main.py:2155-2158`
```python
SELECT url, title, site_url
FROM feeds
ORDER BY title
```

**What goes wrong:** The OPML export includes inactive and failing feeds without any indication of their status. If someone imports this OPML elsewhere, they get broken feeds. The query lacks a `WHERE is_active = 1` filter.

**Severity:** Medium -- exporting broken feeds pollutes other aggregators.

---

### 7.2 `relative_time` returns incorrect results for negative time deltas (future dates)

**File:** `src/utils.py:300-315`
```python
delta = now - dt
if delta.days > 30:
    months = (delta.days + 15) // 30
    ...
elif delta.days > 0:
    ...
elif delta.seconds > 3600:
    ...
```

**What goes wrong:** If `dt` is in the future (e.g., a feed publishes a post with a future date), `delta` will be negative. A negative `timedelta` has `delta.days = -1` and `delta.seconds` representing the remainder. The `delta.days > 30` check fails, `delta.days > 0` fails, then `delta.seconds > 3600` may succeed since `delta.seconds` for a negative timedelta is calculated as `86400 + actual_seconds`. This would display something like "23 hours ago" for a post that is actually 1 hour in the future.

**Severity:** Low -- future-dated posts are rare, and the display is merely confusing rather than harmful.

---

## Summary of Actionable Findings

| # | Pattern | Severity | File:Line | Quick Fix |
|---|---------|----------|-----------|-----------|
| 1.1 | Type coercion: `0` treated as falsy | Medium | config.py:85 | `if value is not None` |
| 2.1 | OPML import overcounts | Medium | main.py:3090 | Check `meta.changes` or `RETURNING id` |
| 2.2 | Entry upsert drops summary/author/url updates | Medium | main.py:1037-1040 | Add fields to `ON CONFLICT DO UPDATE` |
| 4.1 | Non-deterministic GUID from `hash()` | Medium* | models.py:103 | Use SHA256 (check if code path is used) |
| 4.2 | Queue schema not validated | Medium | main.py:796 | Use `FeedJob.from_dict()` |
| 7.1 | OPML exports inactive feeds | Medium | main.py:2155 | Add `WHERE is_active = 1` |
| 1.2 | Empty string becomes None | Low | wrappers.py:174 | `if py_val is not None` |
| 3.2 | Pagination `has_more` off-by-one | Low | main.py:3308 | Query `limit + 1` |
| 7.2 | Future dates display incorrectly | Low | utils.py:300 | Guard for negative deltas |

*Severity depends on whether `ParsedEntry.from_feedparser` is called in production.
