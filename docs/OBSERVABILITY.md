# Planet CF Observability Guide

This document describes Planet CF's approach to observability, the wide event model we use, current coverage, and known gaps.

## Philosophy: Wide Events (Canonical Log Lines)

We follow the **wide event** pattern (also called "canonical log lines") from Honeycomb and Charity Majors' observability philosophy. The core principle:

> **One event per unit of work, not one event per function call.**

### Why Wide Events?

Traditional logging scatters context across many log lines:

```
[INFO] Request received: GET /search?q=workers
[DEBUG] Parsing query string
[DEBUG] Generating embedding...
[DEBUG] Embedding generated in 120ms
[DEBUG] Querying Vectorize...
[DEBUG] Found 15 matches
[DEBUG] Querying D1 for keyword matches...
[DEBUG] Rendering template...
[INFO] Request completed: 200 OK in 450ms
```

Problems:
- Correlating these requires parsing timestamps or adding request IDs everywhere
- Each line is low-value in isolation
- Can't query "show me slow searches with zero results"
- Log volume explodes

Wide events consolidate everything into one high-dimensional event:

```json
{
  "event_type": "request",
  "request_id": "a1b2c3d4e5f6g7h8",
  "method": "GET",
  "path": "/search",
  "route": "/search",
  "status_code": 200,
  "wall_time_ms": 450,
  "search_query": "workers",
  "search_query_length": 7,
  "search_embedding_ms": 120,
  "search_vectorize_ms": 180,
  "search_d1_ms": 45,
  "search_results_total": 15,
  "search_semantic_matches": 12,
  "search_keyword_matches": 8,
  "outcome": "success"
}
```

Benefits:
- Single event contains all context for debugging
- Natural queries: `WHERE search_results_total = 0 AND wall_time_ms > 1000`
- Event volume = operation volume (not log line volume)
- Every field is queryable, filterable, groupable

---

## Unit of Work Definitions

We emit exactly **one event per unit of work**:

| Unit of Work | Trigger | Event Type | Description |
|--------------|---------|------------|-------------|
| HTTP request | `fetch()` | `RequestEvent` | One per incoming HTTP request |
| Queue message | `queue()` | `FeedFetchEvent` | One per feed fetch from queue |
| Cron invocation | `scheduled()` | `SchedulerEvent` | One per hourly cron run |
| Admin operation | Admin handlers | `AdminActionEvent` | One per admin action |

### Event Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ RequestEvent (HTTP Request)                                  │
│ ├── Base: method, path, status_code, wall_time_ms           │
│ ├── search_* fields (populated for /search route)           │
│ ├── generation_* fields (populated for / route)             │
│ └── oauth_* fields (populated for /auth/* routes)           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ FeedFetchEvent (Queue Message)                               │
│ ├── Feed context: feed_id, feed_url, feed_domain            │
│ ├── HTTP: latency_ms, status, cached, redirected            │
│ ├── Parsing: entries_found, entries_added                   │
│ └── indexing_* fields (aggregated from all entries)         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ SchedulerEvent (Cron Invocation)                             │
│ ├── scheduler_* fields (D1 query, queue send timing)        │
│ └── retention_* fields (cleanup stats)                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ AdminActionEvent (Admin Operation)                           │
│ ├── Admin context: username, admin_id, action               │
│ ├── import_* fields (OPML import stats)                     │
│ ├── reindex_* fields (search reindex stats)                 │
│ └── dlq_* fields (dead letter queue operations)             │
└─────────────────────────────────────────────────────────────┘
```

---

## Event Schemas

### RequestEvent

Emitted once per HTTP request. Route-specific fields are null for non-applicable routes.

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Always "request" |
| `request_id` | string | 16-char hex unique ID |
| `correlation_id` | string | For tracing request chains (e.g., from scheduler) |
| `timestamp` | string | ISO 8601 UTC |
| `method` | string | HTTP method |
| `path` | string | Request path |
| `route` | string | Route pattern (/, /search, /admin/*) |
| `user_agent` | string | Truncated to 200 chars |
| `referer` | string | Truncated to 200 chars |
| `status_code` | int | HTTP response status |
| `response_size_bytes` | int | Response body size |
| `wall_time_ms` | float | Total request duration |
| `cache_status` | string | hit/miss/bypass |
| `content_type` | string | html/atom/rss/search/admin/static |
| `outcome` | string | success/error |
| `error_type` | string? | Exception class name |
| `error_message` | string? | Truncated to 200 chars |
| `worker_version` | string | Worker version from DEPLOYMENT_VERSION env var |
| `deployment_environment` | string | Deployment environment from DEPLOYMENT_ENVIRONMENT env var |

**Search fields** (null unless route=/search):

| Field | Type | Description |
|-------|------|-------------|
| `search_query` | string? | Search query (truncated) |
| `search_query_length` | int? | Original query length |
| `search_embedding_ms` | float? | AI embedding generation time |
| `search_vectorize_ms` | float? | Vectorize query time |
| `search_d1_ms` | float? | D1 keyword search time |
| `search_results_total` | int? | Final result count |
| `search_semantic_matches` | int? | Vectorize matches after threshold |
| `search_keyword_matches` | int? | D1 LIKE matches |
| `search_words_truncated` | bool? | True if query exceeded MAX_SEARCH_WORDS |
| `search_exact_title_matches` | int? | Exact title matches |
| `search_title_in_query_matches` | int? | Title-in-query matches |
| `search_query_in_title_matches` | int? | Query-in-title matches |
| `search_semantic_error` | string? | Error from semantic search |
| `search_keyword_error` | string? | Error from keyword search |

**Generation fields** (null unless route=/):

| Field | Type | Description |
|-------|------|-------------|
| `generation_d1_ms` | float? | D1 query time for entries |
| `generation_render_ms` | float? | Jinja2 template render time |
| `generation_entries_total` | int? | Entries in response |
| `generation_feeds_healthy` | int? | Feeds without errors |
| `generation_trigger` | string? | http/cron/admin_manual |
| `generation_used_fallback` | bool? | True if fallback entries shown |

**OAuth fields** (null unless route=/auth/*):

| Field | Type | Description |
|-------|------|-------------|
| `oauth_stage` | string? | redirect/callback |
| `oauth_provider` | string? | github |
| `oauth_success` | bool? | Authentication succeeded |
| `oauth_username` | string? | Authenticated username |

### FeedFetchEvent

Emitted once per queue message (one feed fetch).

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Always "feed_fetch" |
| `request_id` | string | 16-char hex unique ID |
| `queue_message_id` | string | Queue message ID |
| `timestamp` | string | ISO 8601 UTC |
| `feed_id` | int | Database feed ID |
| `feed_url` | string | Feed URL |
| `feed_url_original` | string? | URL before redirect (if redirected) |
| `feed_domain` | string | Extracted domain |
| `feed_title` | string? | Feed title |
| `feed_consecutive_failures` | int | Failure streak count |
| `feed_auto_deactivated` | bool | True if feed was auto-deactivated this fetch |
| `http_latency_ms` | float | HTTP request time |
| `http_status` | int? | HTTP response status |
| `http_cached` | bool | 304 Not Modified |
| `http_redirected` | bool | Followed redirect |
| `response_size_bytes` | int | Response body size |
| `etag_present` | bool | ETag in response |
| `last_modified_present` | bool | Last-Modified in response |
| `entries_found` | int | Entries parsed from feed |
| `entries_added` | int | New entries stored |
| `parse_errors` | int | Parsing error count |
| `upsert_failures` | int | Count of failed entry upserts |
| `content_fetched_count` | int | Count of entries where full content was fetched |
| `indexing_attempted` | int | Entries sent for indexing |
| `indexing_succeeded` | int | Successfully indexed |
| `indexing_failed` | int | Indexing failures |
| `indexing_total_ms` | float | Total indexing time |
| `indexing_embedding_ms` | float | Embedding generation time |
| `indexing_upsert_ms` | float | Vectorize upsert time |
| `indexing_text_truncated` | int | Entries with truncated content |
| `wall_time_ms` | float | Total processing time |
| `outcome` | string | success/error |
| `error_type` | string? | Exception class name |
| `error_message` | string? | Truncated error |
| `error_retriable` | bool? | Should retry |
| `worker_version` | string | Worker version |
| `deployment_environment` | string | Deployment environment from DEPLOYMENT_ENVIRONMENT env var |
| `queue_attempt` | int | Retry attempt number |
| `correlation_id` | string | Propagated from scheduler through queue for tracing |

### SchedulerEvent

Emitted once per cron invocation.

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Always "scheduler" |
| `request_id` | string | 16-char hex unique ID |
| `timestamp` | string | ISO 8601 UTC |
| `scheduler_d1_ms` | float | D1 query time |
| `scheduler_queue_ms` | float | Queue send time |
| `feeds_queried` | int | Feeds found in D1 |
| `feeds_active` | int | Active feeds |
| `feeds_enqueued` | int | Messages sent to queue |
| `retention_d1_ms` | float | Retention D1 time |
| `retention_vectorize_ms` | float | Vector deletion time |
| `retention_entries_scanned` | int | Entries evaluated |
| `retention_entries_deleted` | int | Entries removed |
| `retention_vectors_deleted` | int | Vectors removed |
| `retention_errors` | int | Deletion errors |
| `retention_days` | int | Retention period config |
| `retention_max_per_feed` | int | Max entries config |
| `wall_time_ms` | float | Total cron duration |
| `outcome` | string | success/error |
| `error_type` | string? | Exception class name |
| `error_message` | string? | Truncated error |
| `worker_version` | string | Worker version from DEPLOYMENT_VERSION env var |
| `deployment_environment` | string | Deployment environment from DEPLOYMENT_ENVIRONMENT env var |
| `correlation_id` | string | Generated per scheduler run, propagated to feeds |

### AdminActionEvent

Emitted once per admin action.

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Always "admin_action" |
| `request_id` | string | 16-char hex unique ID |
| `timestamp` | string | ISO 8601 UTC |
| `admin_username` | string | GitHub username |
| `admin_id` | int | Admin database ID |
| `action` | string | add_feed/remove_feed/toggle_feed/import_opml/reindex/retry_dlq |
| `target_type` | string? | feed/feeds/entry/search_index |
| `target_id` | int? | Target resource ID |
| `wall_time_ms` | float | Operation duration |
| `outcome` | string | success/error |
| `error_type` | string? | Exception class name |
| `error_message` | string? | Truncated error |
| `worker_version` | string | Worker version from DEPLOYMENT_VERSION env var |
| `deployment_environment` | string | Deployment environment from DEPLOYMENT_ENVIRONMENT env var |

**OPML import fields** (action=import_opml):

| Field | Type | Description |
|-------|------|-------------|
| `import_file_size` | int? | OPML file size bytes |
| `import_feeds_parsed` | int? | Feeds found in file |
| `import_feeds_added` | int? | Successfully imported |
| `import_feeds_skipped` | int? | Skipped (duplicate/unsafe) |
| `import_errors` | int? | Import error count |

**Reindex fields** (action=reindex):

| Field | Type | Description |
|-------|------|-------------|
| `reindex_entries_total` | int? | Entries to reindex |
| `reindex_entries_indexed` | int? | Successfully indexed |
| `reindex_entries_failed` | int? | Failed to index |
| `reindex_total_ms` | float? | Total reindex time |

**DLQ fields** (action=retry_dlq):

| Field | Type | Description |
|-------|------|-------------|
| `dlq_feed_id` | int? | Feed being retried |
| `dlq_original_error` | string? | Why it was in DLQ |
| `dlq_action` | string? | retry/discard |

---

## Tail Sampling Strategy

Not all events need to be stored. We use **tail sampling** (decide after the event completes):

```python
def should_sample(event, debug_feed_ids=None, sample_rate=0.10):
    # 100% of errors
    if event.outcome == "error":
        return True

    # 100% of slow operations (above p95 thresholds)
    if event.event_type == "feed_fetch" and event.wall_time_ms > 10000:
        return True
    if event.event_type == "request" and event.wall_time_ms > 1000:
        return True
    if event.event_type == "scheduler" and event.wall_time_ms > 60000:
        return True

    # 100% of zero-result searches (important UX signal)
    if event.search_results_total == 0:
        return True

    # 100% of debug feeds (for troubleshooting specific feeds)
    if event.feed_id in debug_feed_ids:
        return True

    # Sample 10% of successful fast operations
    return random.random() < sample_rate
```

**Thresholds**:
- Feed fetch: >10s is slow (timeout is 60s)
- HTTP request: >1s is slow
- Scheduler: >60s is slow
- Admin action: >30s is slow

---

## Example Queries

With Workers Observability, you can run SQL-like queries on events:

**Slow searches with results**:
```sql
SELECT timestamp, search_query, search_results_total, wall_time_ms
FROM events
WHERE event_type = 'request'
  AND route = '/search'
  AND wall_time_ms > 500
  AND search_results_total > 0
ORDER BY wall_time_ms DESC
```

**Feed error rate by domain**:
```sql
SELECT
  feed_domain,
  COUNT(*) as total,
  SUM(CASE WHEN outcome = 'error' THEN 1 ELSE 0 END) as errors,
  AVG(wall_time_ms) as avg_ms
FROM events
WHERE event_type = 'feed_fetch'
GROUP BY feed_domain
ORDER BY errors DESC
```

**Zero-result searches (content gap analysis)**:
```sql
SELECT search_query, COUNT(*) as searches
FROM events
WHERE event_type = 'request'
  AND route = '/search'
  AND search_results_total = 0
GROUP BY search_query
ORDER BY searches DESC
```

**Indexing success rate per feed**:
```sql
SELECT
  feed_id,
  feed_domain,
  SUM(indexing_attempted) as attempted,
  SUM(indexing_succeeded) as succeeded,
  SUM(indexing_failed) as failed
FROM events
WHERE event_type = 'feed_fetch'
GROUP BY feed_id, feed_domain
HAVING failed > 0
```

---

## Coverage Analysis: What's Tracked

### Fully Covered

| Operation | Event | Key Metrics |
|-----------|-------|-------------|
| Homepage generation | RequestEvent | D1 time, render time, entry count |
| Search | RequestEvent | Embedding time, Vectorize time, result counts |
| Feed fetching | FeedFetchEvent | HTTP time, parse stats, **indexing aggregates** |
| Scheduler + Retention | SchedulerEvent | D1 time, queue time, enqueue count, **retention stats** |
| Add feed | AdminActionEvent | Validation, insert, queue time |
| Remove feed | AdminActionEvent | Feed lookup, delete time |
| Toggle feed | AdminActionEvent | State change, D1 update |
| OPML import | AdminActionEvent | Parse stats, import counts |
| DLQ retry | AdminActionEvent | Feed info, queue send, original error |
| Reindex | AdminActionEvent | Entry count, success/fail counts, total time |

### Partially Covered

| Operation | Event | What's Missing |
|-----------|-------|----------------|
| Atom/RSS generation | RequestEvent | No timing breakdown (only wall_time) |
| Admin dashboard | RequestEvent | No render timing |
| Session verification | RequestEvent | No timing for cookie verification |
| Feed metadata update | FeedFetchEvent | No timing for metadata extraction |

---

## Known Gaps (Updated 2026-01-16)

### 1. ~~Retention Policy Timing~~ (FIXED)

**Status**: ✅ FIXED

Retention now runs in `_run_scheduler()` and populates SchedulerEvent with:
- `retention_d1_ms`, `retention_vectorize_ms`
- `retention_entries_scanned`, `retention_entries_deleted`, `retention_vectors_deleted`
- `retention_errors`, `retention_days`, `retention_max_per_feed`

### 2. ~~Indexing Stats Not Aggregated~~ (FIXED)

**Status**: ✅ FIXED

`_upsert_entry()` now returns indexing stats, and `_process_single_feed()` aggregates them onto FeedFetchEvent:
- `indexing_attempted`, `indexing_succeeded`, `indexing_failed`
- `indexing_total_ms`, `indexing_embedding_ms`, `indexing_upsert_ms`
- `indexing_text_truncated`

### 3. ~~Missing Admin Actions~~ (FIXED)

**Status**: ✅ FIXED - All admin actions now emit AdminActionEvent

| Action | Handler | Status |
|--------|---------|--------|
| Add feed | `_add_feed()` | ✅ Emits event |
| OPML import | `_import_opml()` | ✅ Emits event |
| Remove feed | `_remove_feed()` | ✅ Emits event |
| Toggle feed | `_update_feed()` | ✅ Emits event |
| Reindex | `_reindex_all_entries()` | ✅ Emits event |
| DLQ retry | `_retry_dlq_feed()` | ✅ Emits event |

Note: `_trigger_regenerate()` is deferred - it just re-runs the scheduler which already emits SchedulerEvent.

### 4. No Cross-Request Correlation

**Problem**: Related operations have separate request_ids:
- Admin adds feed (AdminActionEvent: request_id=abc)
- Scheduler enqueues it (SchedulerEvent: request_id=def)
- Queue processes it (FeedFetchEvent: request_id=ghi)
- User sees it on homepage (RequestEvent: request_id=jkl)

**Impact**: Can't trace "show me everything that happened to this feed".

**Recommendation**: Add `feed_id` to relevant events, use it as correlation key.

### 5. No Retry Correlation

**Problem**: Queue retries are separate FeedFetchEvents with no link to original attempt.

**Impact**: Can't query "show me feeds that succeeded on retry".

**Current Partial Solution**: `queue_attempt` field shows attempt number, but no `original_message_id`.

### 6. Silent Drops Not Visible

**Problem**: When sampling drops an event, there's no record.

**Impact**:
- Metrics may undercount successes
- Can't verify sampling is working correctly

**Recommendation**: Emit lightweight "sampled_out" events or add counters.

### 7. Database Query Counts

**Problem**: We track D1 query TIME but not COUNT.

**Impact**: Can't detect N+1 query patterns.

**Recommendation**: Add `d1_query_count` fields.

### 8. Cache Status Not Populated

**Problem**: `cache_status` field exists but is empty for most routes.

**Impact**: Can't analyze cache hit rates.

**Recommendation**: Check `cf-cache-status` header or use Cache API.

### 9. Specific Entry Failures Lost

**Problem**: Indexing failures are counted (indexing_failed=2) but we don't know WHICH entries failed.

**Impact**: Can't debug why specific entries fail to index.

**Recommendation**: Add structured error details or separate low-volume error log.

### 10. Queue Backpressure

**Problem**: No visibility into queue depth or processing lag.

**Impact**: Can't detect when queue is backing up.

**Recommendation**: Query queue metrics API if available, or track time-since-scheduled.

---

## Recommended Improvements (Priority Order)

### P0 (Critical) - ✅ COMPLETE
1. ~~**Aggregate indexing stats**: Update `_process_single_feed()` to populate indexing_* fields~~ ✅ DONE
2. ~~**Move retention to scheduler**: Architectural fix for correct observability~~ ✅ DONE

### P1 (High) - ✅ COMPLETE
3. ~~**Add missing AdminActionEvents**: remove_feed, toggle_feed, dlq_retry, reindex~~ ✅ DONE
4. **Add feed_id correlation**: Allow tracing operations for a specific feed (DEFERRED - feed_id already on FeedFetchEvent)

### P2 (Medium)
5. **D1 query counts**: Detect N+1 patterns
6. **Cache status population**: Understand CDN behavior
7. **Retry correlation**: Link retry attempts

### P3 (Low)
8. **Sampling visibility**: Know what was dropped
9. **Queue backpressure**: Monitor queue health
10. **Entry-level error details**: Debug specific failures

---

## Dashboard Recommendations

### Operations Dashboard

| Panel | Query | Purpose |
|-------|-------|---------|
| Request latency p50/p90/p99 | `PERCENTILE(wall_time_ms) WHERE event_type='request'` | SLO tracking |
| Error rate | `COUNT(outcome='error') / COUNT(*)` | Reliability |
| Feed health | `COUNT(DISTINCT feed_id) WHERE consecutive_failures < 3` | Content freshness |
| Search zero-results | `COUNT(*) WHERE search_results_total = 0` | Content gaps |

### Feed Health Dashboard

| Panel | Query | Purpose |
|-------|-------|---------|
| Slowest feeds | `AVG(wall_time_ms) GROUP BY feed_domain ORDER BY DESC` | Performance |
| Highest error feeds | `SUM(outcome='error') GROUP BY feed_id` | Reliability |
| Most entries | `SUM(entries_added) GROUP BY feed_id` | Volume |

### Admin Activity Dashboard

| Panel | Query | Purpose |
|-------|-------|---------|
| Actions by admin | `COUNT(*) GROUP BY admin_username` | Audit |
| Actions by type | `COUNT(*) GROUP BY action` | Usage patterns |
| Failed actions | `WHERE outcome = 'error'` | Troubleshooting |

---

## References

- [Observability Engineering](https://www.oreilly.com/library/view/observability-engineering/9781492076438/) by Charity Majors, Liz Fong-Jones, George Miranda
- [A Practitioner's Guide to Wide Events](https://jeremymorrell.dev/blog/a-practitioners-guide-to-wide-events/)
- [Cloudflare Workers Observability](https://developers.cloudflare.com/workers/observability/)
- [Honeycomb's Guide to Observability](https://www.honeycomb.io/what-is-observability)
