# Documentation vs Code Sync Audit

**Date:** 2026-03-11
**Scope:** README.md, docs/ARCHITECTURE.md, docs/SPEC.md, docs/MULTI_INSTANCE.md,
docs/LITE_MODE.md, docs/TESTING.md, docs/OBSERVABILITY.md vs src/ implementation.

---

## Summary

- **17 discrepancies found** (6 high, 7 medium, 4 low)
- Most issues are stale counts, phantom env vars, and missing route documentation
- SPEC.md is the most drifted document (proposal-era code that never matched implementation)
- ARCHITECTURE.md and OBSERVABILITY.md are very well maintained

---

## 1. API Docs vs Implementation

### 1.1 [HIGH] README: Missing routes in "Public Pages" table

**Doc (README.md, lines 189-199):**
```
| `/`           | Main aggregated feed page |
| `/titles`     | Titles-only view          |
| `/feed.atom`  | Atom feed                 |
| `/feed.rss`   | RSS 2.0 feed              |
| `/feed.rss10` | RSS 1.0 (RDF) feed        |
| `/feeds.opml` | OPML export               |
| `/search`     | Semantic search           |
```

**Code (src/main.py, lines 1367-1412):**
Three routes exist in code but are not documented:
- `/foafroll.xml` -- FOAF feed (registered at line 1384, served at line 2191)
- `/health` -- Health check endpoint (registered at line 1385, served at line 2218)
- `/index.html` and `/titles.html` -- Aliases for `/` and `/titles`

**Recommendation:** Add `/health` and `/foafroll.xml` to the README table.
The `.html` aliases are minor and can be omitted from docs.

### 1.2 [MEDIUM] ARCHITECTURE.md: Missing `_THEMES_WITH_FOAF` from frozenset table

**Doc (docs/ARCHITECTURE.md, lines 393-397):**
```
| Frozenset                    | Controls                      | Themes            |
| `_THEMES_HIDE_SIDEBAR_LINKS` | Hides RSS/titles-only sidebar | `planet-cloudflare` |
| `_THEMES_WITH_RSS10`          | Enables RSS 1.0 (RDF) feed   | `planet-mozilla`  |
```

**Code (src/main.py, line 228):**
```python
_THEMES_WITH_FOAF: frozenset[str] = frozenset({"planet-mozilla"})
```

A third frozenset `_THEMES_WITH_FOAF` controls FOAF/foafroll.xml visibility
for the planet-mozilla theme and is absent from the docs table.

**Recommendation:** Add `_THEMES_WITH_FOAF` row to the ARCHITECTURE.md table.

### 1.3 [LOW] `create_default_routes()` in route_dispatcher.py is stale

**Code (src/route_dispatcher.py, lines 230-275):**
`create_default_routes()` defines routes that are never called anywhere in the
codebase. The actual router is built in `Default._create_router()` (main.py line 1367).
The `create_default_routes()` function is missing `/foafroll.xml` and has no
callers.

**Recommendation:** Either delete `create_default_routes()` or keep it in sync
and add a test that verifies it matches `_create_router()`.

---

## 2. Setup and Install Instructions

### 2.1 [LOW] README migration step only mentions 001_initial.sql

**Doc (README.md, line 135):**
```bash
npx wrangler d1 execute planetcf --remote --file=migrations/001_initial.sql
```

**Code:** There are 5 migration files:
```
migrations/001_initial.sql
migrations/002_seed_admins.sql
migrations/003_add_first_seen.sql
migrations/004_add_last_entry_at.sql
migrations/005_create_applied_migrations.sql
```

The README says to run only `001_initial.sql`. However, the auto-init feature
in `_ensure_database_initialized()` (main.py lines 361-472) creates all core
tables with all columns, making the other migrations only needed for *existing*
databases that were created before those migrations.

**Recommendation:** This is arguably correct for new installs (auto-init handles
it), but add a note: "For existing databases, also apply migrations 002-005."

---

## 3. Architecture Descriptions

### 3.1 [MEDIUM] ARCHITECTURE.md import count is stale

**Doc (docs/ARCHITECTURE.md, line 612):**
```
Imports from ALL 15 other modules (see arrows below)
```

**Code:** `src/` contains 17 `.py` files (16 modules + `__init__.py`), so
main.py imports from 16 other modules, not 15.

Actual file count:
```
__init__.py, admin_context.py, admin.py, auth.py, config.py,
content_processor.py, instance_config.py, main.py, models.py,
oauth_handler.py, observability.py, route_dispatcher.py,
search_query.py, templates.py, utils.py, wrappers.py, xml_sanitizer.py
```

**Recommendation:** Update "15 other modules" to "16 other modules" (or
dynamically say "all other modules").

### 3.2 [MEDIUM] SPEC.md: Worker class name is `PlanetCF`, code uses `Default`

**Doc (docs/SPEC.md, lines 835, 946, 971, 1429, 1655):**
```python
class PlanetCF(WorkerEntrypoint):
```

**Code (src/main.py, line 296):**
```python
class Default(WorkerEntrypoint):
```

The SPEC.md is a design proposal that pre-dates the implementation. The actual
class is `Default`, following Cloudflare Workers Python convention.

**Recommendation:** Update SPEC.md to use `Default` or add a note that the
spec used `PlanetCF` as a working name. Since SPEC.md is labeled "Proposal"
this is low urgency but causes confusion.

### 3.3 [MEDIUM] SPEC.md: Schema missing `last_entry_at` and `first_seen` columns

**Doc (docs/SPEC.md, lines 374-461):**
The feeds schema is missing the `last_entry_at` column (added by migration 004).
The entries schema is missing the `first_seen` column (added by migration 003).

**Code (src/main.py, lines 396, 419):**
```python
# feeds table includes: last_entry_at TEXT
# entries table includes: first_seen TEXT DEFAULT CURRENT_TIMESTAMP
```

**Recommendation:** Update SPEC.md schema to include both columns.

### 3.4 [LOW] SPEC.md: `ContentSanitizer` Protocol not in actual code

**Doc (docs/SPEC.md, lines 724-726):**
```python
class ContentSanitizer(Protocol):
    def clean(self, html: str) -> str: ...
```

**Code (src/models.py):**
`ContentSanitizer` Protocol does not exist in the actual code. `BleachSanitizer`
and `NoOpSanitizer` both have a `clean()` method but there is no shared Protocol
class.

**Recommendation:** Either add the Protocol to the code (good practice) or
remove it from SPEC.md. Since SPEC.md is a proposal, this is low priority.

---

## 4. Config and Feature Flags

### 4.1 [HIGH] README: `GROUP_BY_DATE` and `SEARCH_ENABLED` documented but not implemented

**Doc (README.md, lines 65-67):**
```
| Group by date   | true | `GROUP_BY_DATE`   |
| Search enabled  | true | `SEARCH_ENABLED`  |
```

**Code:** Neither `GROUP_BY_DATE` nor `SEARCH_ENABLED` appears anywhere in
`src/`. Grepping the entire `src/` directory for these strings returns zero
matches. Entries are always grouped by date. Search is controlled by
`INSTANCE_MODE` (lite vs full), not by a `SEARCH_ENABLED` flag.

**Recommendation:** Remove both rows from README.md. Replace `SEARCH_ENABLED`
note with: "Search availability is controlled by `INSTANCE_MODE` (full or lite)."

### 4.2 [HIGH] Multiple undocumented environment variables

The following env vars are read by `src/` code but not documented in README.md
or docs/MULTI_INSTANCE.md's environment variable table:

| Env Var | Read in | Purpose |
|---------|---------|---------|
| `FEED_RECOVERY_ENABLED` | config.py:192 | Enable auto-recovery of disabled feeds (default: true) |
| `FEED_RECOVERY_LIMIT` | config.py:199 | Max disabled feeds to retry per cron (default: 2) |
| `PLANET_OWNER_EMAIL` | config.py:218 | Owner email for User-Agent template |
| `USER_AGENT_TEMPLATE` | config.py:212 | Custom User-Agent format string |
| `OAUTH_REDIRECT_URI` | main.py:3530 | Override OAuth callback URL |
| `DEPLOYMENT_VERSION` | main.py:343 | Worker version for observability |
| `DEPLOYMENT_ENVIRONMENT` | main.py:347 | Environment name for observability |
| `VERSION_METADATA` | main.py:337 | Cloudflare version metadata binding |
| `EMBEDDING_MAX_CHARS` | config.py:118 | Max chars to embed per entry (default: 2000) |
| `SEARCH_SCORE_THRESHOLD` | config.py:156 | Min similarity score (default: 0.3) |
| `SEARCH_TOP_K` | config.py:119 | Max semantic search results (default: 50) |
| `INSTANCE_MODE` | instance_config.py:28 | "full" or "lite" (default: "full") |
| `CONTENT_DAYS` | config.py:115 | Days of entries to display (default: 7) |
| `ENABLE_RSS10` | main.py:1828 | Enable RSS 1.0 format |
| `ENABLE_FOAF` | main.py:1831 | Enable FOAF feed |
| `HIDE_SIDEBAR_LINKS` | main.py:1835 | Hide sidebar RSS/titles links |

Some of these (`ENABLE_RSS10`, `ENABLE_FOAF`, `HIDE_SIDEBAR_LINKS`, `FOOTER_TEXT`)
ARE documented in MULTI_INSTANCE.md but NOT in README.md. Others are entirely
undocumented in any doc.

**Recommendation:** Add a comprehensive env var reference to either README.md or
a dedicated `docs/CONFIGURATION.md`, or expand the MULTI_INSTANCE.md table.

### 4.3 [HIGH] MULTI_INSTANCE.md env var table is incomplete

**Doc (docs/MULTI_INSTANCE.md, lines 219-234):**
The environment variables table lists 14 vars. Missing from that table:

- `CONTENT_DAYS` (mentioned in README but not here)
- `RETENTION_MAX_ENTRIES_PER_FEED` (mentioned in README but not here)
- `FEED_TIMEOUT_SECONDS` and `HTTP_TIMEOUT_SECONDS` (mentioned in README)
- `FEED_FAILURE_THRESHOLD` and `FEED_AUTO_DEACTIVATE_THRESHOLD`
- `FEED_RECOVERY_ENABLED` and `FEED_RECOVERY_LIMIT`
- `EMBEDDING_MAX_CHARS`, `SEARCH_SCORE_THRESHOLD`, `SEARCH_TOP_K`
- `INSTANCE_MODE`
- `PLANET_OWNER_EMAIL`, `USER_AGENT_TEMPLATE`
- `DEPLOYMENT_ENVIRONMENT`, `DEPLOYMENT_VERSION`
- `OAUTH_REDIRECT_URI`

**Recommendation:** This table should be the canonical env var reference.
Add the missing vars.

---

## 5. Test Counts

### 5.1 [MEDIUM] TESTING.md test counts are stale

**Doc (docs/TESTING.md, lines 25, 37, 44):**
```
- ~1180+ tests (unit)
- ~85+ tests (integration)
- 34 tests (E2E)
```

**Code (actual counts as of today):**
```
- 1153 unit tests
- 110 integration tests
- 72 E2E tests
- Total non-E2E: 1263 (runs in ~4s)
```

Integration tests are 110, not ~85+. E2E tests are 72, not 34 (doubled).
Unit test count of ~1180+ is now slightly overstated (1153 actual).

**Recommendation:** Update TESTING.md with current counts. Use exact numbers
rather than approximations since they drift.

### 5.2 [MEDIUM] MEMORY.md (project memory) test counts are stale

The auto-memory says "~1253 tests (1071 unit + 110 integration + 72 e2e)" but
the actual counts are 1153 unit + 110 integration + 72 E2E = 1335 total.
The unit count 1071 is especially outdated.

**Recommendation:** This is auto-managed memory; no action needed from the
user, but the staleness is noted for awareness.

---

## 6. Examples and Code Snippets

### 6.1 [HIGH] SPEC.md code snippets diverged significantly from implementation

The SPEC.md contains extensive code examples that were written as a design
proposal. Multiple areas have diverged:

| SPEC.md snippet | Actual code |
|-----------------|-------------|
| `class PlanetCF(WorkerEntrypoint)` | `class Default(WorkerEntrypoint)` |
| Queue handler: `message.body` used directly | Queue handler: `_to_py_safe(message.body)` required |
| SPEC Result type uses `Generic[T]` | Code uses PEP 695 `type Result[T, E] = Ok[T] \| Err[E]` |
| Schema missing `last_entry_at`, `first_seen` | Both exist in implementation |
| `ContentSanitizer` Protocol defined | Protocol not in code |
| `from src.types import ...` | Actual import is `from models import ...` |

**Recommendation:** Either (a) add a prominent "this is a historical design
document and may not match current code" disclaimer at the top, or (b) update
the code snippets to match reality. Option (a) is simpler given the document's
scope.

### 6.2 [LOW] ARCHITECTURE.md request flow lists `/foafroll.xml` correctly

The request flow header (ARCHITECTURE.md line 51) correctly lists `/foafroll.xml`
in the public pages enumeration, which is good. This is consistent with code.

---

## 7. Discrepancy Summary Table

| # | Severity | Location | Issue | Fix |
|---|----------|----------|-------|-----|
| 1.1 | HIGH | README.md | Missing `/health`, `/foafroll.xml` routes | Add to table |
| 1.2 | MEDIUM | ARCHITECTURE.md | Missing `_THEMES_WITH_FOAF` | Add row to frozenset table |
| 1.3 | LOW | route_dispatcher.py | `create_default_routes()` stale/unused | Delete or sync |
| 2.1 | LOW | README.md | Only mentions migration 001 | Add note about 002-005 |
| 3.1 | MEDIUM | ARCHITECTURE.md | "15 other modules" should be 16 | Update count |
| 3.2 | MEDIUM | SPEC.md | `PlanetCF` vs `Default` class name | Add disclaimer |
| 3.3 | MEDIUM | SPEC.md | Schema missing columns | Update schema |
| 3.4 | LOW | SPEC.md | `ContentSanitizer` Protocol absent | Low priority |
| 4.1 | HIGH | README.md | `GROUP_BY_DATE`, `SEARCH_ENABLED` phantom vars | Remove from table |
| 4.2 | HIGH | All docs | 16+ undocumented env vars | Add comprehensive table |
| 4.3 | HIGH | MULTI_INSTANCE.md | Env var table missing 15+ vars | Expand table |
| 5.1 | MEDIUM | TESTING.md | Test counts stale | Update counts |
| 5.2 | MEDIUM | MEMORY.md | Unit test count stale | Auto-managed |
| 6.1 | HIGH | SPEC.md | Code snippets diverged | Add disclaimer |

---

## Recommended Priority

**Do first (HIGH, quick wins):**
1. Remove `GROUP_BY_DATE` and `SEARCH_ENABLED` from README.md -- these are phantom env vars
2. Add `/health` and `/foafroll.xml` to README.md's route table
3. Add a disclaimer to top of SPEC.md marking it as historical design doc

**Do second (HIGH, more effort):**
4. Create comprehensive env var reference (consolidate README + MULTI_INSTANCE.md)

**Do later (MEDIUM):**
5. Update ARCHITECTURE.md frozenset table and module count
6. Update TESTING.md test counts
7. Update SPEC.md schema sections
