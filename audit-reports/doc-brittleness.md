# Documentation Brittleness Audit

Audit date: 2026-03-11
Scope: `docs/`, `README.md`

---

## Category 1: Fragile References

These are references to specific line numbers, function locations, or class names that will break when the code is refactored.

### 1.1 PERFORMANCE.md: Line number reference to wrangler.jsonc

**File:** `docs/PERFORMANCE.md`, line 172
**Text:** `The python_dedicated_snapshot compatibility flag (wrangler.jsonc:23)`

The flag is currently at line 24 of `wrangler.jsonc`. This reference was already wrong by one line, and any comment or config change at the top of the file will shift it further.

**Recommended rewrite:**
```
The `python_dedicated_snapshot` compatibility flag in `wrangler.jsonc`
uses Cloudflare's pre-built Python snapshot for faster cold starts.
```

Simply drop the line number. The flag name is unique enough to find with a search.

---

### 1.2 PERFORMANCE.md: 15 "see function in file" references

`docs/PERFORMANCE.md` contains 12 parenthetical cross-references like:

- `(see _build_cache_control() in src/utils.py)` (line 9)
- `(see _run_scheduler() in src/main.py)` (lines 23, 131)
- `(see _process_single_feed() in src/main.py)` (lines 41, 140)
- `(see _record_feed_error() in src/main.py)` (line 144)
- `(see _ensure_database_initialized() in src/main.py)` (lines 150, 166)
- `(see _generate_html() in src/main.py)` (line 160)
- `(see _apply_retention_policy() in src/main.py)` (line 162)
- `(see ContentSanitizer.clean() in src/models.py)` (line 186)
- `(see normalize_entry_content() in src/utils.py)` (line 190)
- `(see truncate_summary() in src/content_processor.py)` (line 194)
- `(see env property and _create_router() in src/main.py)` (line 176)

Every function rename, move to a new module, or extraction into a helper will silently break one of these. The `ContentSanitizer.clean()` reference is already wrong -- the class is actually `BleachSanitizer` in `src/models.py`. `ContentSanitizer` only exists as a `Protocol` in `docs/SPEC.md`, not in the actual source.

**Recommended rewrite:** Remove all `(see X() in src/Y.py)` parentheticals. The surrounding prose already explains what the code does. If a reader needs the implementation, `grep -r "_build_cache_control" src/` is more reliable than a stale pointer. Example:

Before:
```
Every HTML and feed response includes (see `_build_cache_control()` in `src/utils.py`):
```
After:
```
Every HTML and feed response includes:
```

If you want to preserve navigability, use a single "Code Map" section at the bottom of the file listing function-to-file mappings, and state that it may drift.

---

### 1.3 ARCHITECTURE.md: Function-to-file binding

**File:** `docs/ARCHITECTURE.md`, lines 289, 392
- `(defined in src/wrappers.py)` -- correct today
- `Feed formats are controlled by theme-based frozensets in src/main.py` -- correct today

These are less fragile because they reference modules, not line numbers. But moving wrappers or themes to dedicated modules would break them. Keep these but remove any if they reference specific functions.

---

### 1.4 OBSERVABILITY.md: Handler function names in status table

**File:** `docs/OBSERVABILITY.md`, lines 449-458

The table maps admin actions to handler functions:

| Action | Handler |
|--------|---------|
| Add feed | `_add_feed()` |
| OPML import | `_import_opml()` |
| Remove feed | `_remove_feed()` |
| Toggle feed | `_update_feed()` |
| Reindex | `_reindex_all_entries()` |
| DLQ retry | `_retry_dlq_feed()` |

These names are correct today, but the table exists only to confirm "this is done." The handler names add no value to a user trying to understand the observability system.

**Recommended rewrite:** Drop the Handler column. The table should say what emits events, not which private function does it:

```markdown
| Admin Action | Status |
|--------------|--------|
| Add feed | Emits AdminActionEvent |
| OPML import | Emits AdminActionEvent |
| Remove feed | Emits AdminActionEvent |
| Toggle feed | Emits AdminActionEvent |
| Reindex | Emits AdminActionEvent |
| DLQ retry | Emits AdminActionEvent |
```

---

## Category 2: Over-Specified Details

Documentation that mirrors code so closely that any change to the code makes the docs wrong.

### 2.1 LESSONS_LEARNED.md: Full ALLOWED_TAGS/ALLOWED_ATTRS listings

**File:** `docs/LESSONS_LEARNED.md`, lesson 11 (lines 321-341)

The doc reproduces the complete `ALLOWED_TAGS` and `ALLOWED_ATTRS` lists from `src/models.py`. The actual code now has 28 allowed tags; the doc lists 26 (missing at least some that may have been added since the doc was written). Any addition or removal of a tag creates a silent divergence.

**Recommended rewrite:**
```markdown
## 11. Content Sanitization is Non-Negotiable

Feed content can contain XSS payloads. All HTML is sanitized before storage using
`bleach.clean()` with a strict allowlist of safe tags and attributes.

The allowlist is defined in `BleachSanitizer` in `src/models.py`. It permits
structural HTML (headings, lists, tables, code blocks, images) and strips
everything else, including scripts and event handlers.
```

This conveys the same lesson without duplicating the list.

---

### 2.2 LESSONS_LEARNED.md: Inline code samples that shadow real code

Several lessons include Python code blocks that look like they are from the codebase but are actually simplified versions. Examples:

- **Lesson 9** (line 280): `create_session()` / `verify_session()` -- simplified versions of the actual `src/auth.py` functions. If auth.py changes signing scheme, these become misleading.
- **Lesson 12** (line 352): `queue()` handler pattern -- shows `msg.ack()` and `msg.retry()`, but the actual queue handler in `src/main.py` uses a different structure.
- **Lesson 13** (line 371): `log_op()` simplified implementation shows `datetime.utcnow()` but real `log_op()` in `src/utils.py` has a different signature (`event_type` parameter, typed kwargs).

These are teaching examples, not documentation of the actual code, but readers may treat them as authoritative.

**Recommended rewrite:** Add a note at the top of LESSONS_LEARNED.md:

```markdown
> Code examples in this document illustrate concepts, not actual implementations.
> For current code, see the `src/` directory.
```

---

### 2.3 PERFORMANCE.md: Hardcoded constant values

**File:** `docs/PERFORMANCE.md`, lines 194-201

```
Summaries are capped at 500 characters
...
- 5 entries per feed per day (window function)
- 100 entries per feed total (configurable via RETENTION_MAX_ENTRIES_PER_FEED)
- 500 entries global cap (DEFAULT_QUERY_LIMIT)
```

These match the current code (`SUMMARY_MAX_LENGTH = 500`, `DEFAULT_QUERY_LIMIT = 500`). But if any constant changes, the doc becomes silently wrong.

**Recommended rewrite:** Reference the constant names without hardcoding the values:

```markdown
Summaries are capped at `SUMMARY_MAX_LENGTH` characters for feed formats
that use summaries.

Three layers of result limiting prevent unbounded response sizes:
- Per feed per day limit (window function in the homepage query)
- Per feed total limit (configurable via `RETENTION_MAX_ENTRIES_PER_FEED`)
- Global cap (`DEFAULT_QUERY_LIMIT` in `src/config.py`)
```

---

### 2.4 README.md: Specific default values table

**File:** `README.md`, lines 21-37

The "Feed Processing Defaults" table hardcodes 8 specific default values (30 seconds, 60 seconds, 100 entries, 3 failures, 90 days, 10 failures, etc.). All are currently correct. But this table will silently diverge if any default is tuned.

**Recommended approach:** Keep the table but add a note: "Defaults are defined in `src/config.py`. The values below reflect initial settings and may have been updated since this README was last edited." This signals to maintainers that the table may need refreshing.

Alternatively, have a test that validates the README table against `src/config.py` constants.

---

### 2.5 DESIGN_GUIDE.md: Exact CSS values

**File:** `docs/DESIGN_GUIDE.md`

The entire document is a detailed specification of CSS values: exact hex colors, pixel sizes, rem values, border-radius values, box-shadow values. This is inherently a mirror of `assets/static/style.css`. If someone updates the CSS without updating this doc, the guide becomes misleading.

**Recommended approach:** This is the one doc where specificity is the point -- it is a design reference. Accept the maintenance burden, but add a note at the top:

```markdown
> This guide documents the **default** theme's design tokens.
> Source of truth: `assets/static/style.css` for the root instance, or
> `examples/<instance>/assets/static/style.css` per instance.
> If values here conflict with the CSS, the CSS wins.
```

---

### 2.6 CONVERSION_GUIDE.md: Hardcoded color/font tables

**File:** `docs/CONVERSION_GUIDE.md`, lines 305-320

Tables list exact hex colors and font families for Planet Python and Planet Mozilla themes. These will become wrong if anyone adjusts the theme CSS.

**Recommended rewrite:** Replace with a process instruction:

```markdown
Use browser DevTools on the original site and the converted instance to verify
colors and fonts match. Key elements to check: primary headings, links,
visited links, body text, header background, footer background.
```

---

## Category 3: Staleness Risk

Instructions that reference specific versions, temporary workarounds, or "current" states that will age poorly.

### 3.1 TESTING.md: Approximate test counts

**File:** `docs/TESTING.md`, lines 25-44

```
~1180+ tests, runs in ~2 seconds
...
~85+ tests, runs in ~2 seconds
...
34 tests
```

Actual current counts: 1263 unit+integration tests (not ~1180+), 110 integration tests (not ~85+), 72 e2e tests (not 34). These are already stale.

Similarly, ARCHITECTURE.md line 305 says "88 tests" and "82 tests" for wrapper tests -- both match current code, but will drift.

**Recommended rewrite:** Use order-of-magnitude descriptions instead of specific counts:

```markdown
### Unit Tests (tests/unit/)
Pure unit tests using mock Cloudflare bindings. Over a thousand tests, runs in seconds.

### Integration Tests (tests/integration/)
Tests that verify end-to-end flows using mock bindings. About a hundred tests.

### E2E Tests (tests/e2e/)
Tests against real Cloudflare infrastructure. Dozens of tests, requires a running
test-planet instance.
```

Or, if exact counts matter, have a CI job that updates the counts.

---

### 3.2 OBSERVABILITY.md: "FIXED" status annotations

**File:** `docs/OBSERVABILITY.md`, lines 427-458

Three "Known Gaps" sections are marked `Status: FIXED` with strikethrough headings. These are changelog artifacts, not documentation. A reader looking at "Known Gaps" section 1 sees "~~Retention Policy Timing~~ (FIXED)" and has to parse the strikethrough to understand it is no longer a gap.

**Recommended rewrite:** Move completed items to a "Resolved" section at the bottom, or delete them entirely. The Known Gaps section should only contain actual gaps:

```markdown
## Known Gaps

### 1. No Cross-Request Correlation
...
### 2. No Retry Correlation
...
```

Add a collapsed "Previously resolved" section if you want the history preserved.

---

### 3.3 SPEC.md: "Version 1.0 Draft" / "Status: Proposal"

**File:** `docs/SPEC.md`, line 3-4

```
Version: 1.0 Draft
Status: Proposal
```

The project is deployed at `www.planetcloudflare.dev` with 1263 tests and production traffic. Calling this a "proposal" signals that the spec may not reflect reality.

**Recommended rewrite:** Either update to `Status: Active` or remove the status line. If the spec has diverged from implementation (common for "proposal" docs), add a disclaimer:

```markdown
> This specification was written before implementation and may not reflect
> the current codebase in all details. For authoritative behavior, see the
> source code and tests.
```

---

### 3.4 CONVERSION_GUIDE.md: "Results Achieved" section

**File:** `docs/CONVERSION_GUIDE.md`, lines 396-403

```
| Planet Python | 67.58% | 86.69% | ~95% |
| Planet Mozilla | 79.79% | 91.54% | ~95% |
```

These are point-in-time pixel-match percentages from when the conversions were first done. They will become meaningless as the original sites change their layouts (or go offline).

**Recommended rewrite:** Move to a "History" section and date-stamp it:

```markdown
## Conversion History

Initial conversion results (February 2026):
| Site | Pixel Match | Notes |
|------|------------|-------|
| Planet Python | ~87% | Remaining diff is dynamic content |
| Planet Mozilla | ~92% | Remaining diff is dynamic content |
```

---

### 3.5 CLI_PROPOSAL.md: Entire document is a proposal for unbuilt features

**File:** `docs/CLI_PROPOSAL.md`

This is a 700+ line proposal for a `planet` CLI tool that does not exist. The document references current scripts accurately but proposes new commands and patterns that were never implemented.

**Risk:** A new contributor may read this and believe the `planet` CLI exists, or start building it without realizing the proposal was shelved.

**Recommended rewrite:** Add a prominent status banner:

```markdown
> **Status: Proposal (not implemented)**
> This document proposes a CLI tool that has not been built.
> Current administration uses the scripts described in `README.md`.
```

---

### 3.6 TESTING.md: Specific test file references

**File:** `docs/TESTING.md`, lines 29-30

```
- `test_safe_wrappers.py` -- CPython tests with Python mocks (88 tests)
- `test_wrappers_ffi.py` -- Pyodide FFI boundary tests with fake JS types (82 tests)
```

The test counts (88 and 82) are currently correct but will drift with any test addition. The file names are stable.

**Recommended rewrite:**

```markdown
- `test_safe_wrappers.py` -- CPython tests with Python mocks
- `test_wrappers_ffi.py` -- Pyodide FFI boundary tests with fake JS types
```

Drop the counts. If you want counts, add `# test count checked by CI` annotations.

---

### 3.7 CONVERSION_GUIDE.md: External URLs as asset sources

**File:** `docs/CONVERSION_GUIDE.md`, lines 25-43

```bash
curl -o examples/planet-python/static/images/python-logo.gif \
  https://planetpython.org/images/python-logo.gif
```

These `curl` commands reference live URLs on external sites. When Planet Python or Planet Mozilla change their URL structure or go offline, these commands break.

**Recommended rewrite:** Frame as a process, not a recipe:

```markdown
Download the original site's logo, background images, and CSS files.
Use the browser's DevTools Network tab to find all asset URLs, then
download them into `examples/<name>/assets/static/`.
```

---

## Category 4: Structural Issues

### 4.1 PERFORMANCE.md doubles as an architecture doc

`docs/PERFORMANCE.md` describes caching strategy, asset delivery, feed fetching, database optimization, and runtime behavior. Much of this overlaps with `docs/ARCHITECTURE.md`. When one is updated, the other may not be. For example, both describe the caching strategy and both describe the boundary layer.

**Recommended approach:** Move the "what" and "where" details to ARCHITECTURE.md. Keep PERFORMANCE.md focused on "why these choices are fast" and "what are the bottlenecks."

---

### 4.2 LESSONS_LEARNED.md Quick Reference table duplicates lessons

**File:** `docs/LESSONS_LEARNED.md`, lines 488-508

The "Quick Reference: Common Gotchas" table at the bottom restates the lessons above. When a new lesson is added, the author must remember to update this table too.

**Recommended approach:** Either auto-generate this table or remove it. The lessons themselves serve as the reference.

---

## Summary of Recommendations

| Priority | Action | Files |
|----------|--------|-------|
| High | Remove all `(see X() in src/Y.py)` cross-references | PERFORMANCE.md |
| High | Fix `ContentSanitizer` reference (should be `BleachSanitizer`) | PERFORMANCE.md |
| High | Remove line number reference `wrangler.jsonc:23` | PERFORMANCE.md |
| High | Add status banner to CLI_PROPOSAL.md | CLI_PROPOSAL.md |
| High | Update SPEC.md status from "Proposal" to "Active" or add disclaimer | SPEC.md |
| Medium | Replace hardcoded test counts with ranges | TESTING.md, ARCHITECTURE.md |
| Medium | Replace hardcoded constant values with constant names | PERFORMANCE.md, README.md |
| Medium | Move OBSERVABILITY.md "FIXED" items out of Known Gaps | OBSERVABILITY.md |
| Medium | Remove duplicated ALLOWED_TAGS listing | LESSONS_LEARNED.md |
| Medium | Add "source of truth" note to DESIGN_GUIDE.md | DESIGN_GUIDE.md |
| Medium | Add "code examples are conceptual" note to LESSONS_LEARNED.md | LESSONS_LEARNED.md |
| Low | Replace external curl URLs with process instructions | CONVERSION_GUIDE.md |
| Low | Date-stamp "Results Achieved" section | CONVERSION_GUIDE.md |
| Low | Remove handler name column from observability table | OBSERVABILITY.md |
| Low | Remove Quick Reference duplicate table | LESSONS_LEARNED.md |
