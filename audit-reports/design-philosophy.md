# Design Philosophy Compliance Audit

**Date:** 2026-03-11
**Scope:** `src/` codebase (17 files) audited against principles stated in SPEC.md, ARCHITECTURE.md, DESIGN_GUIDE.md, PERFORMANCE.md, OBSERVABILITY.md, LESSONS_LEARNED.md, TESTING.md, LITE_MODE.md, and README.md.

---

## Methodology

Each stated design principle was extracted from the project's own documentation, then the `src/` codebase was scanned for compliance. Principles are grouped by source document. For each principle: a brief statement, evidence of compliance, any violations found, and a per-principle score.

Scoring: FULL (no violations found), HIGH (minor or cosmetic issues), PARTIAL (structural violations present), LOW (principle is largely ignored).

---

## Principle 1: Security First (SPEC.md 1.2)

> "XSS prevention, HTML sanitization, SSRF protection"

### XSS / HTML Sanitization

**Compliance: FULL**

- `BleachSanitizer` in `src/models.py` (line 256) sanitizes all feed content with explicit allowlists for tags, attributes, and protocols.
- `script` and `style` tags are stripped with content before bleach runs (regex pre-processing).
- `javascript:` URLs are stripped from `href` attributes as a post-processing step.
- External links get `rel="noopener noreferrer"` and `target="_blank"` automatically.
- All entry content passes through `_sanitize_html()` in `main.py` (line 1025) before storage.
- Lazy loading (`loading="lazy"`) and missing `alt` attributes are added to images.

### SSRF Protection

**Compliance: FULL**

- `is_safe_url()` in `main.py` (line 238) blocks: localhost variants, private IP ranges (RFC 1918), loopback, link-local, IPv6 ULA (fc00::/7).
- Cloud metadata endpoints blocked: `169.254.169.254`, `100.100.100.200`, `192.0.0.192`, `metadata.google.internal`, `metadata.azure.internal`, `instance-data`.
- URL validation runs both before fetch (line 892) and after redirects (line 926), preventing redirect-based SSRF bypass.
- OPML import also validates each feed URL (line 3075).
- Admin add-feed validates URL (line 2823).
- Only `http`/`https` schemes allowed.

**No violations found.**

---

## Principle 2: Boundary Layer for JS/Python Types (LESSONS_LEARNED.md 2, 17, 21)

> "Create a thin boundary layer at the edge that converts all JS types to Python types immediately. Application code NEVER sees JsProxy objects."

### Compliance: HIGH (minor leakage into main.py)

**Strengths:**
- `src/wrappers.py` implements the full boundary layer: `SafeD1`, `SafeAI`, `SafeVectorize`, `SafeQueue`, `SafeEnv`, `SafeHeaders`, `SafeFormData`, `SafeFeedInfo`.
- `SafeEnv` wraps the raw environment on first access via a property override on the Worker class (line 308-321 of main.py).
- Row factory functions (`feed_row_from_js`, `entry_row_from_js`, `admin_row_from_js`, `audit_row_from_js`) handle all D1 result conversion.
- `safe_http_fetch()` normalizes HTTP responses across Pyodide and test environments.
- `_to_d1_value()` converts `None` to `JS_NULL` for D1 binds.

**Violations (minor):**
- `main.py` directly calls `_to_py_safe()` in 15+ locations, `_to_py_list()` in 3 locations, and `_is_js_undefined()` in 1 location. These are internal boundary helpers with underscore-prefix convention, yet they are imported and used directly in business logic rather than being encapsulated within wrapper classes.
- Specific examples:
  - Line 705: `health = _to_py_safe(health_result)` -- should be handled by SafeD1's `.first()` return.
  - Line 781, 796: `_to_py_safe(message.body)` -- queue message bodies are converted inline rather than through a SafeQueue consumer wrapper.
  - Line 969, 980: feedparser entries converted with `_to_py_list` and `_to_py_safe` inline.
  - Line 1059, 1246, 2241, 2859, 2967: scattered `_to_py_safe()` calls on D1 results.

These are not correctness bugs (the conversion is happening), but they violate the stated principle that "all JsProxy conversion happens in the boundary layer ONLY." The boundary layer should fully encapsulate these conversions so `main.py` never needs to import `_to_py_safe` directly.

**Assessment:** The architecture is sound and the boundary does exist. The leakage is a code hygiene issue, not a safety gap. Score: HIGH.

---

## Principle 3: Good Netizen Behavior (SPEC.md 1.2)

> "Conditional requests (ETag/Last-Modified), rate limiting, respect for Retry-After"

### Compliance: FULL

- **Conditional requests:** ETag and Last-Modified stored per feed. Sent as `If-None-Match` and `If-Modified-Since` on subsequent fetches (lines 897-900). 304 responses handled correctly (line 941).
- **Retry-After:** HTTP 429/503 detected (line 931), `Retry-After` header parsed and stored (line 936). `RateLimitError` exception does not increment `consecutive_failures` (line 850), preserving the feed's health status.
- **User-Agent:** Identifies as `PlanetCF/1.0` with contact URL and email (config.py line 22). Customizable via `USER_AGENT_TEMPLATE`.

**No violations found.**

---

## Principle 4: Static Output / On-Demand Generation with Edge Caching (SPEC.md 1.2, ARCHITECTURE.md 2.1)

> "Generate fast-loading HTML that can be cached at the edge. No KV. No R2. Just D1 and Cloudflare's built-in edge cache."

### Compliance: FULL

- All HTML/RSS/Atom/OPML responses use `Cache-Control: public, max-age=3600, stale-while-revalidate=3600` via `_build_cache_control()` in `src/utils.py` (line 199-201).
- No KV or R2 bindings anywhere in the codebase. Confirmed by grep: zero references to KV namespaces or R2 buckets in `src/`.
- Comments in code explicitly reinforce this: "No KV caching -- edge cache handles repeat requests" (line 1562), "stateless, no KV" (line 2568).
- Pre-warming: Scheduler fetches `/`, `/titles`, `/feed.atom`, `/feed.rss` after processing (line 745-746), ensuring edge cache is always warm.
- Admin/search routes correctly bypass cache with `no-store` (line 2555) or `cacheable=False` route config.

**No violations found.**

---

## Principle 5: Reliability / Graceful Failure Handling (SPEC.md 1.2, 3.4)

> "Handle feed failures gracefully without blocking other feeds. One feed per queue message for complete isolation."

### Compliance: FULL

- Each feed enqueued as separate queue message (line 614-634). Code comment: "Do NOT batch multiple feeds into one message."
- Per-feed timeout via `asyncio.wait_for()` (line 827, 3254).
- Failed messages retry via queue infrastructure. After 3 retries, DLQ.
- Auto-deactivation after configurable consecutive failures (default 10).
- Auto-recovery: scheduler retries a configurable number of disabled feeds per hour (line 639-674).
- DLQ messages are logged and acked (line 778-791).

**No violations found.**

---

## Principle 6: No Filesystem at Runtime (LESSONS_LEARNED.md 4, PERFORMANCE.md)

> "Cloudflare Workers Python runs in WebAssembly inside V8 isolates. There is no filesystem. Templates must be embedded as Python strings at build time."

### Compliance: FULL

- Zero `open()`, `os.path`, or `pathlib` calls anywhere in `src/`. Confirmed by grep.
- Templates embedded in `src/templates.py` as string constants.
- `EmbeddedLoader` (Jinja2 custom loader) serves templates from in-memory dict.
- CSS/JS served via Workers Static Assets from `assets/` directory, never loaded by the Worker.

**No violations found.**

---

## Principle 7: Wide Events / One Event per Unit of Work (OBSERVABILITY.md)

> "One event per unit of work, not one event per function call."

### Compliance: FULL

- Four event types implemented in `src/observability.py`: `RequestEvent`, `FeedFetchEvent`, `SchedulerEvent`, `AdminActionEvent`.
- Each maps to exactly one unit of work: HTTP request, queue message, cron invocation, admin action.
- Route-specific fields (search_*, generation_*, oauth_*) are null for non-applicable routes, following the wide event pattern.
- `emit_event()` called exactly once per unit of work completion.
- Indexing stats aggregated onto `FeedFetchEvent` (not separate events).
- Retention stats aggregated onto `SchedulerEvent`.

**No violations found.**

---

## Principle 8: Stateless Sessions via Signed Cookies (LESSONS_LEARNED.md 9)

> "HMAC-signed cookies containing session data. No server-side session storage."

### Compliance: FULL

- `src/auth.py` implements `create_signed_cookie()` and `verify_signed_cookie()` using `hmac` + `hashlib.sha256` with `hmac.compare_digest()` for timing-safe comparison.
- Cookies are `HttpOnly; Secure; SameSite=Lax; Path=/` (line 169).
- Expiration checked with configurable grace period (default 5s for clock skew).
- No session storage in D1, KV, or anywhere else.
- Auth module is pure functions with no Worker class dependency.

**No violations found.**

---

## Principle 9: Smart Defaults / "Just Work" Configuration (README.md)

> "Planet CF is designed to 'just work' with minimal configuration. All configuration values have sensible defaults."

### Compliance: FULL

- `src/config.py` centralizes all defaults with a registry pattern (`_INT_CONFIG_REGISTRY`).
- Every config value has a documented default: content days (7), retention (90 days), max entries per feed (100), timeouts, thresholds, etc.
- `get_config_value()` handles missing/invalid env vars gracefully with logging.
- Database auto-initialization on first request (`_ensure_database_initialized`).
- Theme fallback to `default` if specified theme doesn't exist.
- Content display fallback: shows 50 most recent entries when date range is empty.

**No violations found.**

---

## Principle 10: Content-First Design (DESIGN_GUIDE.md)

> "Articles are the star; clean white cards on muted background. No visual noise."

### Compliance: FULL (design principle, verified in templates)

- Templates use semantic HTML: `<article>` elements for entries.
- Date groupings use subtle uppercase labels.
- System font stacks with no web font downloads (confirmed in PERFORMANCE.md and CSS).
- Inline SVG icons instead of external image requests.

**Not applicable to audit at code level** -- this is a CSS/template principle. Templates are compiled into `src/templates.py` and appear to follow the stated design.

---

## Principle 11: Lite Mode / Two Deployment Modes (LITE_MODE.md)

> "Lite mode removes Vectorize and Workers AI bindings entirely. Route guards return 404 for /search, /auth/*, and /admin/* routes."

### Compliance: FULL

- `is_lite_mode()` in `src/instance_config.py` checks `INSTANCE_MODE` env var.
- Routes marked `lite_mode_disabled=True`: `/search`, `/auth/*`, `/admin/*` (confirmed in `route_dispatcher.py` lines 250-273).
- Check at dispatch time returns 404 JSON error for disabled routes (line 1463-1467).
- `SafeEnv` handles missing AI/Vectorize bindings with `getattr(..., None)` (line 489-492).
- Templates conditionally hide search/admin links with `{% if not is_lite_mode %}`.

**No violations found.**

---

## Principle 12: Hybrid Search with Exact-Match Priority (LESSONS_LEARNED.md 5, 15)

> "Three-tier ranking: exact title matches first (score 1.0), semantic matches (by similarity), keyword-only (by date)."

### Compliance: HIGH

- Search implementation in main.py includes semantic (Vectorize), keyword (D1 LIKE), and title matching.
- `SearchQueryBuilder` in `src/search_query.py` handles query construction.
- LIKE query parameters are escaped for special characters.

**Minor concern:** The ranking priority is documented thoroughly in LESSONS_LEARNED.md but the implementation spans many lines in main.py making it harder to verify the exact three-tier priority without tracing through the full search handler. The principle is structurally followed.

---

## Principle 13: Two-Tier Testing Strategy (LESSONS_LEARNED.md 20, TESTING.md)

> "test_safe_wrappers.py -- CPython tests with Python mocks. test_wrappers_ffi.py -- Pyodide FFI boundary tests with fake JS types."

### Compliance: FULL (verified by documentation and test structure)

- Both test files exist in the test suite per TESTING.md.
- Three test tiers: unit (~1180+), integration (~85+), E2E (34).
- FFI tests use `pyodide_fakes` fixture with `FakeJsProxy`, `JsNull`, `JsUndefined`.
- E2E tests run against real Cloudflare infrastructure.

**Not code-audited** (tests are outside `src/`), but the stated strategy is consistent with the codebase design.

---

## Principle 14: Type Safety / Semantic Types (SPEC.md 5, models.py)

> "Leverage Python's type system for safety, documentation, and IDE support. All types are defined in src/models.py."

### Compliance: HIGH

- `src/models.py` defines `FeedId`, `EntryId`, `AdminId` as `NewType` aliases, plus `FeedJob`, `Session`, `ParsedEntry` as frozen dataclasses.
- `AuditAction`, `FeedStatus`, `ContentType` as `Literal` types.
- `FeedJob` and `Session` have proper serialization methods.
- `main.py` uses `TypeAlias` for Cloudflare runtime types (`ScheduledEvent`, `QueueBatch`, `WorkerEnv`, etc.).

**Minor gap:** The semantic `NewType` aliases (`FeedId`, `EntryId`) are defined in `models.py` but used inconsistently in `main.py` -- most `feed_id` parameters are typed as `int` rather than `FeedId`. This reduces the value of the semantic types since the type checker cannot catch `feed_id`/`entry_id` mixups.

---

## Principle 15: Performance / Pyodide Cold-Start Mitigation (PERFORMANCE.md)

> "stale-while-revalidate + cron pre-warming ensures real visitors almost never hit a cold Worker."

### Compliance: FULL

- `stale-while-revalidate=3600` on all cacheable responses (utils.py line 201).
- Cron pre-warming fetches 4 key pages after each scheduler run (main.py line 745).
- `python_dedicated_snapshot` compatibility flag mentioned in docs.
- Per-isolate caching of `SafeEnv` and `RouteDispatcher`.
- All D1/AI/Vectorize operations use `async/await`.
- Window functions for efficient SQL queries.
- Lazy image loading.
- System font stacks (zero web font downloads).

**No violations found.**

---

## Consistency Check: Do the Principles Contradict Each Other?

### No contradictions found.

The principles form a coherent architecture:

1. **"No filesystem" + "embedded templates"** -- consistent. Templates are compiled at build time, not loaded at runtime.
2. **"No KV/R2" + "edge caching"** -- consistent. The edge cache handles repeat requests; the Worker generates on cache miss.
3. **"Security first" + "smart defaults"** -- no tension. Defaults are secure (HttpOnly cookies, bleach sanitization). Security is not traded for convenience.
4. **"Lite mode" + "full mode"** -- consistent. Route guards cleanly disable paid features. `SafeEnv` handles missing bindings.
5. **"Boundary layer" + "wide events"** -- consistent. The boundary converts types; observability aggregates metrics. They operate at different layers.
6. **"One event per unit of work" + "structured logging"** -- the project uses both: wide events (`emit_event`) for observability and operational logs (`log_op`) for debugging. This is stated explicitly in the code and docs.

---

## Summary Scorecard

| # | Principle | Source | Score |
|---|-----------|--------|-------|
| 1 | Security First (XSS, SSRF) | SPEC.md | FULL |
| 2 | Boundary Layer (JS/Python) | LESSONS_LEARNED.md | HIGH |
| 3 | Good Netizen (ETags, Retry-After) | SPEC.md | FULL |
| 4 | On-Demand + Edge Cache, No KV/R2 | ARCHITECTURE.md | FULL |
| 5 | Reliability / Queue Isolation | SPEC.md | FULL |
| 6 | No Filesystem at Runtime | LESSONS_LEARNED.md | FULL |
| 7 | Wide Events / One per Work Unit | OBSERVABILITY.md | FULL |
| 8 | Stateless Signed Sessions | LESSONS_LEARNED.md | FULL |
| 9 | Smart Defaults | README.md | FULL |
| 10 | Content-First Design | DESIGN_GUIDE.md | FULL |
| 11 | Lite Mode Route Guards | LITE_MODE.md | FULL |
| 12 | Hybrid Search, Exact-Match First | LESSONS_LEARNED.md | HIGH |
| 13 | Two-Tier Testing (FFI + Mock) | TESTING.md | FULL |
| 14 | Type Safety / Semantic Types | SPEC.md | HIGH |
| 15 | Performance / Cold-Start Mitigation | PERFORMANCE.md | FULL |

**Overall Compliance: 12/15 FULL, 3/15 HIGH, 0 PARTIAL, 0 LOW**

---

## Recommendations

### 1. Encapsulate boundary conversions (Principle 2)

Move the 15+ direct `_to_py_safe()` calls in `main.py` into wrapper methods. Specifically:
- Queue message body conversion should be handled by a `SafeQueueMessage` wrapper.
- feedparser results should go through a `SafeFeedParser` wrapper (similar to `SafeFeedInfo`).
- Stray `_to_py_safe()` calls on D1 results (lines 705, 719, 1059, 1246, 2241) suggest SafeD1 `.first()` isn't always used, or its return value is being double-converted.

### 2. Enforce semantic types (Principle 14)

Change `feed_id: int` parameters to `feed_id: FeedId` throughout `main.py` to get actual type-checker enforcement. The `NewType` aliases exist but buy nothing if they're not used consistently.

### 3. Document search ranking flow (Principle 12)

The three-tier search ranking is thoroughly documented in LESSONS_LEARNED.md but the implementation is spread across a large handler. Consider extracting the ranking logic into a dedicated function with the three tiers clearly labeled.
