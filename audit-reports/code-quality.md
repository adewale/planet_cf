# Code Quality Audit Report

**Date:** 2026-03-11
**Scope:** `src/` (17 files, ~9400 LOC) and supporting infrastructure
**Method:** Manual line-by-line reading of all source modules, cross-referencing with tests and vulture whitelist

---

## 1. Duplication

### 1a. `_build_phrase_query` and `_build_single_word_query` are identical

**Files:** `src/search_query.py` lines 94-118 and 120-144

Both methods produce the exact same SQL and params. The only difference is that `_build_single_word_query` passes `self._words_truncated` instead of `False` for `words_truncated`, but a phrase search will never have `_words_truncated=True` anyway (words are only parsed for non-phrase queries).

**Action:** Delete `_build_single_word_query`. In `build()`, route both phrase and single-word cases to `_build_phrase_query` (renamed to `_build_simple_query`), passing `self._words_truncated` unconditionally.

### 1b. Phrase-detection logic duplicated between `main.py` and `SearchQueryBuilder.from_raw_query`

**Files:** `src/main.py` lines 2290-2298 and `src/search_query.py` lines 208-234

`_search_entries` manually detects quoted phrases, strips quotes, and passes `is_phrase_search` to `SearchQueryBuilder`. Meanwhile, `SearchQueryBuilder.from_raw_query` does exactly the same detection and stripping. The `from_raw_query` classmethod is never called in production -- it only exists for tests.

**Action:** Use `SearchQueryBuilder.from_raw_query(query)` in `_search_entries` instead of hand-rolling the detection. Remove the duplicate detection code from `main.py`.

### 1c. Feed-list SQL queries repeated for OPML export and FOAF

**Files:** `src/main.py` lines 2155-2159 and 2193-2197

Both `_export_opml` and `_serve_foaf` run `SELECT url, title, site_url FROM feeds ORDER BY title` and build nearly identical `template_feeds` lists. The only difference: FOAF defaults `site_url` to `f["url"]` while OPML defaults to `""`.

**Action:** Extract a shared `_get_feed_list_for_export()` method that returns the raw feed rows. Let each caller apply its own default for `site_url`.

### 1d. Feed XML template entry preparation is near-identical across Atom, RSS, and RSS 1.0

**Files:** `src/main.py` lines 2081-2098, 2104-2126, 2133-2151

All three `_generate_*_feed` methods build a list comprehension that calls `strip_xml_control_chars` on title, author, and content with minor per-format differences (CDATA escaping, truncation, field names). The `strip_xml_control_chars` calls on title and author are identical in all three.

**Action:** Extract a helper like `_prepare_feed_entry(entry, content_mode)` that strips XML control chars from common fields and lets callers specify content handling ("full", "cdata", "truncated").

### 1e. OPML parsing duplicated between `admin.parse_opml` and `main._import_opml`

**Files:** `src/admin.py` lines 57-97 and `src/main.py` lines 3039-3069

`admin.py` has a tested `parse_opml()` function that handles XXE protection, feed extraction, and limit enforcement. But `main._import_opml` does not call it -- it re-implements the same XML parsing, DTD-forbid, outline iteration, and limit enforcement inline. The `parse_opml` and `validate_opml_feeds` functions in `admin.py` are unused in production (only whitelisted for vulture and tested independently).

**Action:** Refactor `_import_opml` to call `parse_opml()` and `validate_opml_feeds()` from `admin.py`. Remove the duplicate XML parsing from `main.py`.

### 1f. Route table defined twice: `_create_router` and `create_default_routes`

**Files:** `src/main.py` lines 1367-1414 and `src/route_dispatcher.py` lines 230-275

The route table is defined inline in `Default._create_router()` and again in `create_default_routes()`. The two are nearly identical but have diverged: `_create_router` includes `/foafroll.xml` while `create_default_routes` does not. This is exactly the "divergent copies" antipattern the MEMORY.md warns about.

**Action:** Make `_create_router` call `create_default_routes()` as its base, then add any instance-specific routes. Add a test that the two stay in sync (or eliminate one).

---

## 2. Internal Inconsistency

### 2a. Import aliasing style: underscore-prefix vs direct

**File:** `src/main.py` lines 88-153

Some imports from `utils` are aliased with underscore prefixes (`_html_response`, `_log_op`, `_format_date_label`) while the same module's constant `ERROR_MESSAGE_MAX_LENGTH` is imported directly. The underscore aliases serve no purpose -- they do not avoid name collisions and they obscure the origin when reading the code. Other modules (`config`, `wrappers`, `templates`) are imported without aliases.

**Action:** Remove the underscore aliases. Import functions directly from `utils`. If the intent is to mark them as "private to this module", that ship has sailed -- they are used on nearly every line.

### 2b. Cookie parsing lives in two modules with inconsistent APIs

**Files:** `src/auth.py` (`parse_cookie_value`) and `src/oauth_handler.py` (`extract_oauth_state_from_cookies`)

`auth.py` provides a generic `parse_cookie_value(header, name)` function. `oauth_handler.py` has its own `extract_oauth_state_from_cookies` that hand-parses cookies instead of calling `parse_cookie_value`. Both do the same `split(";")` / `startswith(name=)` dance.

**Action:** Have `extract_oauth_state_from_cookies` delegate to `parse_cookie_value("oauth_state")`. This also removes the magic number `12` (length of `"oauth_state="`).

### 2c. Thin wrapper methods on `Default` class that add no logic

**File:** `src/main.py` lines 2049-2075

Eleven one-liner methods like `_get_retention_days`, `_get_max_entries_per_feed`, `_get_search_top_k` etc. each just call `get_X(self.env)`. They add indirection without value -- callers could call `get_retention_days(self.env)` directly, which is equally readable and removes 50+ lines.

Two exceptions are legitimate: `_get_theme` (adds logging for missing themes) and `_get_deployment_context` (builds a dict). The rest are pure pass-through.

**Action:** Inline the pass-through wrappers. Keep `_get_theme` and `_get_deployment_context` since they add behavior.

### 2d. Inconsistent `self._is_safe_url` vs module-level `is_safe_url`

**File:** `src/main.py` lines 1194-1199 and 238-288

`_is_safe_url` is a one-line method that delegates to the module-level `is_safe_url`. Some call sites use `self._is_safe_url(url)`, others could call `is_safe_url(url)` directly (e.g., it is already a module-level function). The method exists "so it can be tested directly", per the docstring, but `is_safe_url` is already module-level and directly testable.

**Action:** Remove `_is_safe_url` method. Call `is_safe_url()` directly at all call sites.

### 2e. Error response formatting inconsistency: HTML vs JSON

**File:** `src/main.py`

Admin feed operations (`_remove_feed`, `_add_feed`, `_import_opml`) return HTML error pages via `_admin_error_response`. But `_update_feed` returns `_json_error`. `_list_feeds` returns JSON. `_view_dlq` returns JSON. The choice between HTML and JSON error responses appears arbitrary rather than based on a clear convention (e.g., "form submissions get HTML, API calls get JSON").

**Action:** Document the convention. Suggestion: POST-from-form routes return HTML errors; PUT/DELETE/GET-API routes return JSON errors. Then audit each admin handler to match.

---

## 3. Simplification and Subtraction

### 3a. `models.py` is mostly dead code in production

**File:** `src/models.py` (371 lines)

Only `BleachSanitizer` is imported by production code (`main.py`). Everything else -- `FeedJob`, `Session`, `ParsedEntry`, `FeedRow`, `EntryRow`, `AdminRow`, `Ok`, `Err`, `Result`, `FetchError`, `NoOpSanitizer`, `FeedId`, `EntryId`, `AdminId`, `AuditAction`, `FeedStatus`, `ContentType` -- is used only in tests or not at all. The entire vulture whitelist for `models.py` (lines 21-82) exists to suppress warnings about these unused symbols.

Notable: `ParsedEntry.from_feedparser` duplicates logic now handled by `EntryContentProcessor` in `content_processor.py`. The `Result[T, E]` / `Ok` / `Err` types are defined but never used in any error handling path. The TypedDict row types (`FeedRow`, `EntryRow`, `AdminRow`) are never used for type annotations -- all code uses `dict[str, Any]`.

**Action:**
- Move `BleachSanitizer` and `NoOpSanitizer` to their own module (e.g., `sanitizer.py`) since they are content-processing concerns, not "models".
- Mark `ParsedEntry.from_feedparser` as deprecated or remove it -- `EntryContentProcessor` is the canonical entry processor.
- Either start using the TypedDict types for annotations (which would catch bugs) or remove them. They currently document intent but provide zero type safety because nothing references them.
- Either start using `Result[T, E]` / `FetchError` in the error handling paths or remove them. Dead abstractions mislead future contributors into thinking they are part of the architecture.

### 3b. `format_feed_validation_result` in `admin.py` is unused in production

**File:** `src/admin.py` lines 132-160

This function creates a dict with keys `valid`, `title`, `site_url`, `entry_count`, `final_url`, `error`. But `_validate_feed_url` in `main.py` builds the same dict shape inline -- it never calls `format_feed_validation_result`. The function only exists in the vulture whitelist and tests.

**Action:** Either use it in `_validate_feed_url` (replace the inline dict construction) or delete it.

### 3c. `format_datetime` and `xml_escape` in `utils.py` are unused in production

**File:** `src/utils.py` lines 129-134 and 271-276

Both are whitelisted in vulture. `xml_escape` is never called from `src/` -- all XML escaping is done via templates or `strip_xml_control_chars`. `format_datetime` is referenced only in docs.

**Action:** Move to test helpers or delete. They add to the surface area of `utils.py` without being used.

### 3d. `process_entry` convenience function in `content_processor.py` is unused in production

**File:** `src/content_processor.py` lines 193-204

This function wraps `EntryContentProcessor(entry, feed_id).process()`. It exists in the vulture whitelist and is called in one test. Production code in `main.py` constructs the processor directly.

**Action:** Delete the wrapper. Tests can construct `EntryContentProcessor` directly (they already do in most cases).

### 3e. `log_admin_action` in `admin.py` is unused in production

**File:** `src/admin.py` lines 168-194

This function logs admin actions to structured logs. But `main.py` has its own `_log_admin_action` method that writes to the `audit_log` D1 table. The `admin.py` version just calls `log_op()` -- a one-liner that is never called from any production code path.

**Action:** Delete it. The audit trail lives in D1 via `_log_admin_action`, and operational logging happens through the observability events.

### 3f. `_classify_error` is an orphaned module-level function

**File:** `src/main.py` lines 195-209

This function classifies exceptions into categories. It is called in one place (the queue handler, line 866). It could be a method on the class, or better, moved to `observability.py` where `FeedFetchEvent.error_category` is defined.

**Action:** Move to `observability.py` as a standalone function. It has no dependencies on the Worker class.

### 3g. Oversized `main.py` at 3707 lines

**File:** `src/main.py`

The file contains the Worker class with 40+ methods spanning cron scheduling, queue processing, HTTP routing, HTML generation, feed fetching, search, OAuth, and admin CRUD. This makes it hard to navigate and review.

The existing extraction into modules (`auth.py`, `admin.py`, `admin_context.py`, `content_processor.py`, `search_query.py`, `oauth_handler.py`) demonstrates the right pattern, but the job is only half done. Several coherent chunks remain in `main.py`:

- Feed fetching logic (`_process_single_feed`, `_upsert_entry`, `_index_entry_for_search`, `_update_feed_success`, `_record_feed_error`, `_update_feed_url`, `_set_feed_retry_after`, `_update_feed_metadata`) -- ~350 lines that could be a `FeedProcessor` module
- HTML/XML generation (`_generate_html`, `_generate_atom_feed`, `_generate_rss_feed`, `_generate_rss10_feed`, `_export_opml`, `_serve_foaf`) -- ~300 lines that could be a `generators` module
- SSRF validation (`is_safe_url`, `BLOCKED_METADATA_IPS`) -- ~50 lines that belong in `utils.py` or their own module

**Action:** This is a large refactoring effort. Prioritize by pain: the feed processing and generation logic are the most self-contained and would benefit most from extraction. The SSRF logic is trivially movable.

### 3h. `_EXPECTED_COLUMNS` schema drift detection is maintenance overhead

**File:** `src/main.py` lines 475-528

The `_EXPECTED_COLUMNS` dict duplicates the schema definition from the `CREATE TABLE` statements ~100 lines above it. Any schema change requires updating both places. The drift check runs on every isolate startup and provides only a log warning (no remediation).

**Action:** Consider generating `_EXPECTED_COLUMNS` from the CREATE TABLE SQL, or remove the drift check entirely. For a single-developer or small-team project, the wrangler migration system already tracks schema changes.

### 3i. `D1Result` class recreated on every `.all()` call

**File:** `src/wrappers.py` lines 289-297

`SafeD1Statement.all()` defines a `D1Result` class inside the method body, meaning a new class object is created on every query. This is a minor inefficiency but also an odd pattern.

**Action:** Move `D1Result` to module level as a `@dataclass` or `NamedTuple`.

---

## Summary of Recommended Actions

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| High | 1e. Use `admin.parse_opml` in `_import_opml` | Small | Eliminates duplicated OPML parsing with XXE protection |
| High | 1f. Reconcile route tables | Small | Fixes silent divergence (missing `/foafroll.xml`) |
| High | 3a. Audit `models.py` dead code | Medium | Removes ~200 lines of unused abstractions |
| Medium | 1a. Merge identical search query builders | Small | Removes a confusing duplication |
| Medium | 1b. Use `from_raw_query` in production | Small | Single source of phrase-detection logic |
| Medium | 2a. Remove underscore import aliases | Small | Improves readability across 3700 lines |
| Medium | 2b. Unify cookie parsing | Small | Eliminates duplicated parsing logic |
| Medium | 2c. Inline pass-through config wrappers | Small | Removes ~50 lines of zero-value indirection |
| Medium | 3b-3e. Delete unused functions | Small | Shrinks vulture whitelist and maintenance surface |
| Low | 1c-1d. Extract feed list and entry prep helpers | Small | Reduces repetition in generation code |
| Low | 2d. Remove `_is_safe_url` wrapper | Trivial | One fewer indirection layer |
| Low | 2e. Formalize HTML-vs-JSON error convention | Medium | Consistency, but no bugs today |
| Low | 3g. Extract feed processing from `main.py` | Large | Structural improvement, but `main.py` works as-is |
| Low | 3h. Remove schema drift check | Small | Less maintenance, low-value feature |
| Low | 3i. Hoist `D1Result` to module level | Trivial | Minor code hygiene |
