# Spec: Replace LIKE-based Keyword Search with FTS5

## Problem

Keyword search currently uses `LIKE '%term%'` patterns against the `entries` table
(`search_query.py:SearchQueryBuilder`). This performs a full table scan on every query.
As the entries table grows, search latency degrades linearly.

SQLite FTS5 provides an inverted index with O(log n) lookups and built-in BM25 relevance
ranking. Cloudflare D1 [supports FTS5](https://developers.cloudflare.com/d1/sql-api/sql-statements/).

## Scope

Replace the LIKE-based keyword leg of hybrid search with FTS5. The semantic/Vectorize
search path is **unchanged**. The hybrid ranking strategy (keyword-first, semantic-second)
is **unchanged**. The public API (query params, response shape) is **unchanged**.

### Out of Scope

- Vectorize/semantic search changes
- Search UI changes
- New search features (facets, filters, etc.)
- Changes to entry creation/update/delete flows beyond FTS index maintenance

## Architecture

### Current Flow

```
SearchQueryBuilder.build()
  → SQL: SELECT ... FROM entries e JOIN feeds f ... WHERE e.title LIKE ? OR e.content LIKE ?
  → Execute against D1
  → Return keyword_entries
```

### New Flow

```
FTS5SearchQueryBuilder.build()
  → SQL: SELECT ... FROM entries e JOIN feeds f ... JOIN entries_fts fts ON e.id = fts.rowid
         WHERE entries_fts MATCH ?
  → Execute against D1
  → Return keyword_entries
```

The rest of `_search_entries()` in `main.py` (result ranking, deduplication, semantic
merge) remains the same.

## Detailed Design

### 1. Migration: `006_create_fts5_index.sql`

Create the FTS5 virtual table and backfill it from existing data.

```sql
-- Create FTS5 virtual table for full-text search on entries.
-- Uses content-sync mode: the FTS index mirrors the entries table
-- but does not store a copy of the content (saves storage).
--
-- IMPORTANT: D1 requires lowercase 'fts5' (case-sensitive).
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title,
    content,
    content='entries',
    content_rowid='id',
    tokenize='unicode61'
);

-- Backfill: index all existing entries
INSERT INTO entries_fts(rowid, title, content)
    SELECT id, title, content FROM entries;
```

**Key decisions:**

- **`content='entries'` (content-sync / external content mode):** The FTS index does
  not duplicate the full text. It stores only the inverted index tokens. Reads come
  from the `entries` table via the `content_rowid` join. This saves significant D1
  storage since `entries.content` contains full HTML.
- **`tokenize='unicode61'`:** Handles Unicode text (CJK, Arabic, emoji, accented
  characters). This is the default FTS5 tokenizer and provides case-insensitive
  matching and Unicode folding out of the box.
- **Lowercase `fts5`:** D1 requires the module name in lowercase. Using uppercase
  `FTS5` returns "not authorized."

### 2. FTS Index Maintenance (Triggers vs Application-Level)

With `content='entries'` (external content mode), FTS5 does **not** automatically
stay in sync. We must keep it in sync explicitly.

**Approach: D1 triggers**

Add triggers in the same migration:

```sql
-- Keep FTS index in sync with entries table via triggers.
-- Required because content-sync FTS5 tables do not auto-update.

CREATE TRIGGER IF NOT EXISTS entries_fts_insert AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, title, content)
        VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_fts_delete AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, content)
        VALUES ('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS entries_fts_update AFTER UPDATE OF title, content ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, content)
        VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO entries_fts(rowid, title, content)
        VALUES (new.id, new.title, new.content);
END;
```

**Why triggers over application-level sync:**

- Triggers guarantee consistency even if entries are modified outside the search
  code path (e.g., retention cleanup `DELETE`, admin bulk operations).
- Zero application code changes needed for entry insert/update/delete paths.
- The triggers run within the same D1 transaction as the DML statement.

### 3. New Query Builder: `FTS5SearchQueryBuilder`

Replace `SearchQueryBuilder` in `src/search_query.py`. The new builder generates
FTS5 `MATCH` queries instead of `LIKE` patterns.

#### Public Interface (unchanged)

```python
@dataclass
class SearchQueryResult:
    sql: str
    params: tuple
    words_truncated: bool = False

@dataclass
class FTS5SearchQueryBuilder:
    query: str
    is_phrase_search: bool = False
    max_words: int = DEFAULT_MAX_SEARCH_WORDS

    def build(self, limit: int = 50) -> SearchQueryResult: ...

    @classmethod
    def from_raw_query(cls, raw_query: str, max_words: int = ...) -> "FTS5SearchQueryBuilder": ...
```

The `SearchQueryResult` dataclass is unchanged. `FTS5SearchQueryBuilder` is a
**drop-in replacement** for `SearchQueryBuilder` — same constructor signature,
same `build()` return type, same `from_raw_query()` factory.

#### FTS5 Query Syntax Mapping

| Search Mode | Current (LIKE) | New (FTS5 MATCH) |
|---|---|---|
| **Phrase** (`"error handling"`) | `LIKE '%error handling%'` | `MATCH '"error handling"'` |
| **Single word** (`python`) | `LIKE '%python%'` | `MATCH 'python'` |
| **Multi-word** (`python error`) | `LIKE '%python%' AND LIKE '%error%'` | `MATCH 'python error'` (implicit AND) |

FTS5's default query syntax uses implicit AND for multiple terms, which matches
the current LIKE multi-word behavior (all words must appear).

#### FTS5 Query Escaping

FTS5 has its own special characters that need escaping. Characters with special
meaning in FTS5 queries: `"`, `*`, `(`, `)`, `+`, `^`, `NEAR`, `OR`, `AND`, `NOT`.

Escaping strategy: wrap each user-supplied token in double quotes to treat it as
a literal string. This prevents FTS5 operator injection (analogous to the current
LIKE escaping).

```python
@staticmethod
def escape_fts5_token(value: str) -> str:
    """Escape a token for safe use in FTS5 MATCH expression.

    Wraps in double quotes and escapes internal double quotes by doubling them.
    This treats the value as a literal string, preventing FTS5 operator injection.
    """
    return '"' + value.replace('"', '""') + '"'
```

Examples:
- `python` → `"python"`
- `it's` → `"it's"`
- `test "quoted"` → `"test ""quoted"""`
- `DROP TABLE` → `"DROP" "TABLE"` (two quoted tokens, implicit AND)

#### Generated SQL

**Phrase search:**
```sql
SELECT e.id, e.feed_id, e.guid, e.url, e.title, e.author,
       e.content, e.summary, e.published_at, e.first_seen,
       f.title as feed_title, f.site_url as feed_site_url
FROM entries e
JOIN feeds f ON e.feed_id = f.id
JOIN entries_fts fts ON e.id = fts.rowid
WHERE entries_fts MATCH ?
ORDER BY e.published_at DESC
LIMIT ?
```
Params: `('"error handling"', 50)`

**Single word:**
```sql
-- Same SQL structure as phrase
```
Params: `('"python"', 50)`

**Multi-word:**
```sql
-- Same SQL structure as phrase
```
Params: `('"python" "error" "handling"', 50)` (implicit AND between quoted tokens)

Note: All three modes produce the **same SQL template**. Only the MATCH expression
in the bind parameter differs. This is a simplification over the current LIKE approach
which generates different SQL for each mode.

#### Prefix Search Bonus

FTS5 natively supports prefix matching with `*`. While not implementing new UI for
this yet, the builder should support it for future use. A single unquoted token
shorter than 3 characters could use prefix matching (`ab*`) to maintain parity with
LIKE's substring behavior for very short queries. However, for initial implementation,
we use exact token matching (which is a minor semantic change from LIKE substring
matching — see Behavioral Differences below).

### 4. Integration Point: `_search_entries()` in `main.py`

The only change in `main.py` is swapping the builder class:

```python
# Before:
builder = SearchQueryBuilder(
    query=query,
    is_phrase_search=is_phrase_search,
    max_words=MAX_SEARCH_WORDS,
)

# After:
builder = FTS5SearchQueryBuilder(
    query=query,
    is_phrase_search=is_phrase_search,
    max_words=MAX_SEARCH_WORDS,
)
```

Everything else in `_search_entries()` — semantic search, result ranking, dedup,
event metrics, template rendering — is unchanged.

### 5. Backward Compatibility: Keep `SearchQueryBuilder`

The old `SearchQueryBuilder` class is **not deleted**. It remains available as a
fallback and for tests that explicitly test LIKE behavior. The import in `main.py`
changes, but the old class stays in `search_query.py`.

## Behavioral Differences

FTS5 tokenized matching differs from LIKE substring matching in a few edge cases:

| Scenario | LIKE (current) | FTS5 (new) | Impact |
|---|---|---|---|
| **Substring in word** (`"cloud"` matching `"Cloudflare"`) | Matches | Does not match (token boundary) | Minor — full words still match. Prefix search (`cloud*`) can be added later. |
| **HTML tags in content** | Matches tags (`<div>`) | Tokenizer strips markup context | Neutral — users don't search for HTML tags. |
| **Special chars** (`test_func`) | Matches as substring | Tokenized as `test` and `func` | Matches more broadly (both words anywhere). |
| **Relevance ranking** | None (ORDER BY published_at) | BM25 available (not used in v1) | Future improvement possible. |
| **Case sensitivity** | D1 LIKE is case-insensitive | FTS5 unicode61 is case-insensitive | No change. |

These differences are acceptable. The semantic search layer (Vectorize) covers
fuzzy/conceptual matching. FTS5 keyword search provides fast, precise token matching.

## Testing Strategy

### Principle: Existing Tests Must Pass Unchanged

All existing tests in `tests/unit/test_search_query.py`, `tests/integration/test_search.py`,
and `tests/integration/test_search_accuracy.py` must continue to pass. Tests that
assert on SQL content (e.g., `"LIKE" in result.sql`) will be updated to assert on
FTS5 SQL content instead, but the **behavioral assertions** (what results are returned,
ranking order, deduplication) must remain identical.

### Test Plan

#### A. Unit Tests: `tests/unit/test_search_query.py`

**Updated tests** (assert on FTS5 SQL instead of LIKE SQL):

1. `TestSearchQueryBuilderPhraseSearch` → `TestFTS5PhraseSearch`
   - Phrase search builds correct FTS5 MATCH SQL
   - Params contain quoted phrase: `'"error handling"'`
   - Special characters in phrase are double-quote escaped

2. `TestSearchQueryBuilderSingleWord` → `TestFTS5SingleWord`
   - Single word builds correct MATCH SQL
   - Params contain quoted token: `'"python"'`
   - Special characters escaped

3. `TestSearchQueryBuilderMultiWord` → `TestFTS5MultiWord`
   - Multi-word builds MATCH with space-separated quoted tokens
   - Word truncation still applies (max_words)
   - Custom max_words respected

4. `TestSearchQueryBuilderFromRawQuery` → `TestFTS5FromRawQuery`
   - Double-quoted queries detected as phrase search
   - Single-quoted queries detected as phrase search
   - Unquoted queries detected as word search
   - Whitespace stripped
   - max_words passed through

5. `TestSearchQueryBuilderValidation` → `TestFTS5Validation`
   - Empty query raises ValueError
   - Whitespace-only query raises ValueError

**New tests:**

6. `TestFTS5Escaping`
   - Double quotes in token are doubled: `test "quoted"` → `"test ""quoted"""`
   - FTS5 operators in query are quoted (not interpreted): `OR`, `AND`, `NOT`, `NEAR`
   - Asterisk in query is quoted (not treated as prefix): `test*` → `"test*"`
   - Parentheses in query are quoted: `(test)` → `"(test)"`
   - Plus/caret in query are quoted

7. `TestFTS5SecurityDeep`
   - SQL injection via MATCH expression prevented (all input quoted)
   - FTS5 command injection (`{rank}`, `{snippet}`) prevented
   - Null bytes handled
   - Newlines handled

8. `TestFTS5Unicode`
   - Emoji in query builds successfully
   - CJK characters build successfully
   - Arabic text builds successfully
   - Mixed scripts handled

9. `TestFTS5Determinism`
   - Same input → same output
   - Build called twice → same result
   - Placeholder count matches params count
   - Params are tuple (immutable)

10. `TestFTS5SQLStructure`
    - All search modes produce SQL with `MATCH`
    - All search modes produce SQL with `entries_fts`
    - SQL contains proper JOIN: `JOIN entries_fts fts ON e.id = fts.rowid`
    - SQL does NOT contain `LIKE`
    - SQL has exactly 2 placeholders (MATCH expression + LIMIT)

11. `TestSearchQueryBuilderBackwardCompat`
    - Old `SearchQueryBuilder` class still importable
    - Old class still produces LIKE queries
    - Old class is not broken by new code

#### B. Integration Tests: `tests/integration/test_search.py`

All existing integration tests must pass without modification. These test the full
search pipeline including:

- `test_search_returns_results_for_indexed_entries` — finds indexed entries
- `test_hybrid_search_finds_entries_via_keyword_when_vectorize_empty` — keyword fallback
- `test_search_ai_returns_none_still_works` — AI failure graceful degradation
- `test_search_ai_throws_exception_still_works` — exception handling
- `test_search_vectorize_throws_exception_still_works` — Vectorize failure
- `test_search_keyword_entries_rank_before_semantic` — ranking order
- `test_search_deduplication_entry_appears_once` — dedup
- `test_search_empty_results_returns_200` — no results
- `test_search_event_metrics_populated` — metrics
- `test_search_long_query_returns_error` — validation
- `test_search_with_url_encoded_chars` — URL encoding
- `test_search_phrase_search_in_handler` — phrase search

**Required mock changes:** The `MockD1Statement` in `conftest.py` and the
`MockD1WithFixtures` in `test_search_accuracy.py` currently detect keyword search
queries by checking for `"LIKE"` in the SQL. These must be updated to also detect
`"MATCH"` / `"entries_fts"` in the SQL and return the same results. The mock must
simulate FTS5 MATCH behavior (tokenized matching) to ensure test fidelity.

#### C. Search Accuracy Tests: `tests/integration/test_search_accuracy.py`

All existing accuracy tests must pass:

- `TestTitleMatching.test_exact_title_match`
- `TestTitleMatching.test_title_in_query_match`
- `TestTitleMatching.test_query_in_title_match`
- `TestKeywordMatching.test_keyword_in_content`
- `TestKeywordMatching.test_author_search`
- `TestSearchRanking.test_exact_title_ranks_above_partial`
- `TestSearchRanking.test_title_match_ranks_above_content_match`
- `TestEdgeCases.test_case_insensitive_matching`
- `TestEdgeCases.test_multi_word_query`
- `TestEdgeCases.test_quoted_query_strips_quotes`
- `TestEdgeCases.test_no_results_returns_empty`
- `TestAllFixtureQueries.test_all_expected_results`

**Note on `test_partial_word_matching`:** This test searches for `"Cloudflare"` and
expects matches. FTS5 tokenizes on word boundaries, so searching for `"Cloudflare"`
will match entries containing the token `cloudflare`. This test should continue to pass.
If a test searches for a substring that doesn't align with token boundaries (e.g.,
`"cloud"` expecting to match `"Cloudflare"`), it would need to be adapted — but
review of the current fixtures shows no such test exists.

#### D. Performance Benchmark: `tests/benchmark/test_search_performance.py`

**New file.** Compares LIKE vs FTS5 query performance using real SQLite (not mocks).

```python
"""
Performance benchmark: LIKE vs FTS5 search.

Demonstrates that FTS5 is at least as fast as LIKE-based search
across a range of dataset sizes and query types.

Run with: pytest tests/benchmark/test_search_performance.py -v -s
"""

import sqlite3
import statistics
import time

import pytest

# Dataset sizes to benchmark
DATASET_SIZES = [100, 1_000, 10_000]
# Number of iterations per benchmark for statistical significance
ITERATIONS = 50
# Queries to benchmark
BENCHMARK_QUERIES = [
    ("single_word", "python", False),
    ("multi_word", "python error handling", False),
    ("phrase", "error handling", True),
    ("common_word", "the", False),
    ("rare_word", "xyzzyquux", False),
]
```

The benchmark will:

1. **Setup:** Create a SQLite database with `N` entries containing realistic text
   (lorem ipsum mixed with technical terms). Create both the regular `entries` table
   and the `entries_fts` FTS5 virtual table.

2. **LIKE benchmark:** For each query type, run the current LIKE-based SQL 50 times,
   measure wall-clock time, compute median and p95.

3. **FTS5 benchmark:** For each query type, run the FTS5 MATCH SQL 50 times,
   measure wall-clock time, compute median and p95.

4. **Assertions:**
   - FTS5 median latency <= LIKE median latency for all dataset sizes (i.e., FTS5
     is at least as fast).
   - At 10,000 entries, FTS5 should be measurably faster (assert FTS5 < LIKE * 0.9
     to demonstrate the indexing advantage, with a generous tolerance for CI variance).

5. **Output:** Print a comparison table showing median/p95 latencies for both
   approaches at each dataset size.

Example output:
```
Dataset: 10,000 entries
┌──────────────┬────────────────┬────────────────┬──────────┐
│ Query Type   │ LIKE median    │ FTS5 median    │ Speedup  │
├──────────────┼────────────────┼────────────────┼──────────┤
│ single_word  │ 12.4ms         │ 0.3ms          │ 41x      │
│ multi_word   │ 35.1ms         │ 0.4ms          │ 88x      │
│ phrase       │ 11.8ms         │ 0.2ms          │ 59x      │
│ common_word  │ 8.2ms          │ 0.5ms          │ 16x      │
│ rare_word    │ 10.1ms         │ 0.1ms          │ 101x     │
└──────────────┴────────────────┴────────────────┴──────────┘
```

**Important:** The benchmark uses real `sqlite3` (Python's built-in module), not D1
mocks. This tests the actual query execution characteristics. D1 performance in
production may differ, but the relative comparison (LIKE vs FTS5) holds because D1
uses SQLite under the hood.

#### E. Migration Test: `tests/unit/test_fts5_migration.py`

**New file.** Verifies the migration SQL executes correctly against a real SQLite database.

Tests:
1. **Migration creates FTS5 table:** Run migration SQL, verify `entries_fts` exists
   via `PRAGMA table_list`.
2. **Backfill populates FTS5:** Insert entries before migration, run migration,
   verify FTS5 contains all entries via `SELECT count(*) FROM entries_fts`.
3. **Insert trigger:** Insert a new entry into `entries`, verify it appears in
   `entries_fts` via MATCH query.
4. **Delete trigger:** Delete an entry from `entries`, verify it's removed from
   `entries_fts`.
5. **Update trigger:** Update an entry's title, verify the old title no longer
   matches and the new title does match in FTS5.
6. **Migration is idempotent:** Running migration twice doesn't error (due to
   `IF NOT EXISTS`).
7. **FTS5 MATCH works end-to-end:** Insert entries with known content, run
   MATCH queries, verify correct results returned.

### Test Execution

```bash
# Run all tests (must all pass)
pytest tests/ -v

# Run only search-related tests
pytest tests/unit/test_search_query.py tests/integration/test_search.py tests/integration/test_search_accuracy.py -v

# Run performance benchmark
pytest tests/benchmark/test_search_performance.py -v -s

# Run migration tests
pytest tests/unit/test_fts5_migration.py -v
```

## Implementation Plan

### Step 1: Add Migration
- Create `migrations/006_create_fts5_index.sql`
- Add FTS5 virtual table, triggers, and backfill

### Step 2: Add `FTS5SearchQueryBuilder`
- Add new class to `src/search_query.py` alongside existing `SearchQueryBuilder`
- Implement `escape_fts5_token()`, `build()`, `from_raw_query()`
- Keep `SearchQueryBuilder` intact

### Step 3: Swap Builder in `main.py`
- Change import from `SearchQueryBuilder` to `FTS5SearchQueryBuilder` in `_search_entries()`
- Single-line change: swap the class name in the constructor call

### Step 4: Update Test Mocks
- Update `MockD1Statement._filter_results()` in `conftest.py` to handle FTS5 SQL
- Update `MockD1WithFixtures` in `test_search_accuracy.py` to detect MATCH queries
- Ensure mock FTS5 matching simulates tokenized (word-boundary) matching

### Step 5: Update Unit Tests
- Add `TestFTS5*` test classes
- Update existing tests that assert on LIKE SQL to assert on MATCH SQL
- Keep old LIKE tests in a separate `TestSearchQueryBuilderLegacy` class

### Step 6: Add Performance Benchmark
- Create `tests/benchmark/test_search_performance.py`
- Verify FTS5 is at least as fast as LIKE across all dataset sizes

### Step 7: Add Migration Tests
- Create `tests/unit/test_fts5_migration.py`
- Verify migration correctness with real SQLite

### Step 8: Verify All Tests Pass
- Run full test suite
- Verify no regressions in search accuracy tests
- Verify performance benchmark assertions pass

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| D1 FTS5 case sensitivity (`fts5` must be lowercase) | Use lowercase in migration SQL. Add a test that verifies the migration runs. |
| FTS5 export limitation (can't export DB with virtual tables) | Document in ARCHITECTURE.md. Workaround: drop FTS5 table before export, recreate after. |
| Token boundary matching differs from LIKE substring matching | Semantic search (Vectorize) covers fuzzy matching. Monitor search quality post-deploy. |
| External content mode requires manual sync | Triggers handle sync automatically. Test trigger correctness. |
| Migration backfill on large tables | Backfill runs once. D1 handles this within migration execution. |

## Files Changed

| File | Change |
|---|---|
| `migrations/006_create_fts5_index.sql` | **New.** FTS5 table, triggers, backfill. |
| `src/search_query.py` | **Modified.** Add `FTS5SearchQueryBuilder` class. Keep `SearchQueryBuilder`. |
| `src/main.py` | **Modified.** Swap `SearchQueryBuilder` → `FTS5SearchQueryBuilder` (1 line). |
| `tests/conftest.py` | **Modified.** Update mock to handle MATCH SQL. |
| `tests/unit/test_search_query.py` | **Modified.** Add FTS5 test classes, keep LIKE tests. |
| `tests/integration/test_search_accuracy.py` | **Modified.** Update mock to handle MATCH SQL. |
| `tests/benchmark/test_search_performance.py` | **New.** Performance comparison. |
| `tests/unit/test_fts5_migration.py` | **New.** Migration correctness tests. |
| `docs/ARCHITECTURE.md` | **Modified.** Document FTS5 usage and export limitation. |
