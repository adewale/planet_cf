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

#### Trigger Interaction with UPSERT (`ON CONFLICT DO UPDATE`)

The `_upsert_entry()` method (`main.py:1030`) uses:

```sql
INSERT INTO entries (...) VALUES (...)
ON CONFLICT(feed_id, guid) DO UPDATE SET
    title = excluded.title,
    content = excluded.content,
    updated_at = CURRENT_TIMESTAMP
RETURNING id
```

SQLite's trigger behavior for UPSERT depends on whether a conflict occurs:

| Scenario | Triggers Fired on `entries` |
|---|---|
| **New entry** (no conflict) | BEFORE INSERT → AFTER INSERT |
| **Existing entry** (conflict, DO UPDATE) | BEFORE INSERT → BEFORE UPDATE → AFTER UPDATE |

This means:
- **New entries:** The `entries_fts_insert` AFTER INSERT trigger fires → FTS entry added.
- **Updated entries:** The `entries_fts_update` AFTER UPDATE trigger fires → FTS entry
  deleted with old values, re-added with new values. The AFTER INSERT trigger does
  **not** fire on the conflict path (the insert is omitted), so no double-insert.

The `AFTER UPDATE OF title, content` clause matches because the `DO UPDATE SET` always
includes `title` and `content` in its SET clause, even if values haven't changed.
SQLite fires `AFTER UPDATE OF col` based on columns mentioned in SET, not whether
values actually differ.

**Test requirement:** Add a migration test that verifies UPSERT fires the correct
trigger (see Section E.8).

#### Cascade DELETE and FTS Trigger Behavior

When a feed is deleted (`DELETE FROM feeds WHERE id = ?`), entries cascade via the
foreign key constraint (`ON DELETE CASCADE`). **SQLite does not fire triggers on child
tables for cascade deletes** unless `PRAGMA recursive_triggers = ON` is set (off by
default, and not controllable in D1).

This means: cascade-deleting a feed's entries does **not** fire `entries_fts_delete`,
leaving stale tokens in the FTS index.

**Impact: Low.** The search query uses a JOIN:
```sql
FROM entries e
JOIN feeds f ON e.feed_id = f.id
JOIN entries_fts fts ON e.id = fts.rowid
WHERE entries_fts MATCH ?
```
Stale FTS rowids pointing to deleted entries produce no JOIN match, so they never
appear in results. The stale tokens only waste FTS index storage.

**Mitigation:** The FTS5 `rebuild` command (see Section 2b) periodically reconciles
the FTS index with the entries table. Feed deletion is rare (admin action), so the
stale data accumulates slowly.

**Alternative considered:** Add a BEFORE DELETE trigger on `feeds` that explicitly
`DELETE FROM entries WHERE feed_id = old.id` before the cascade. This would fire
`entries_fts_delete` for each entry. However, this adds complexity for marginal
benefit since the JOIN already filters stale results. Not recommended for v1.

#### Retention Policy Deletes

The `_apply_retention_policy()` method (`main.py:1958`) uses:
```sql
DELETE FROM entries WHERE id IN (?, ?, ...)
```
These are direct DELETEs on `entries`, **not** cascade deletes. The `entries_fts_delete`
AFTER DELETE trigger fires normally for each deleted row. No gap here.

### 2b. FTS Index Rebuild and Integrity

FTS5 external content tables can drift out of sync if:
- Cascade deletes skip the trigger (see above)
- Triggers are accidentally dropped
- The entries table is modified directly (e.g., D1 console)
- A trigger fails mid-execution

FTS5 provides two maintenance commands:

```sql
-- Check FTS index integrity against the content table
INSERT INTO entries_fts(entries_fts) VALUES('integrity-check');

-- Rebuild FTS index from scratch using the content table
INSERT INTO entries_fts(entries_fts) VALUES('rebuild');
```

**Integration with existing reindex endpoint:** The current `_reindex_all_entries()`
(`main.py:3375`) only re-indexes Vectorize embeddings. Extend it to also rebuild
the FTS5 index:

```python
# In _reindex_all_entries(), add before the Vectorize loop:
await self.env.DB.prepare(
    "INSERT INTO entries_fts(entries_fts) VALUES('rebuild')"
).run()
```

This is a single SQL statement that rebuilds the entire FTS index from the `entries`
table. It replaces all FTS content, so it's both the fix for stale data and a full
re-index. It does not require iterating over entries individually.

**Test requirement:** Add tests for rebuild and integrity-check (see Section E.9).

### 2c. NULL Handling in FTS Triggers

The `entries.title` and `entries.content` columns are nullable (`TEXT` without
`NOT NULL`). When a NULL value is inserted into an FTS5 column, FTS5 treats it as
an empty string — it won't match any search terms, which is correct behavior.

The DELETE trigger uses `old.title` and `old.content`. The FTS5 `'delete'` command
requires the exact values that were originally indexed. Since NULL was indexed as
empty string, passing NULL to the delete command is consistent. SQLite handles this
transparently.

**Test requirement:** Add migration tests for NULL title/content (see Section E.10).

### 2d. Indexed Columns: title and content Only

The FTS5 index covers `title` and `content` only. This matches the current LIKE
search behavior, which uses `WHERE e.title LIKE ? OR e.content LIKE ?`.

Fields **not** indexed:
- `author` — Not searched by the current LIKE SQL (despite the `MockD1WithFixtures`
  mock in `test_search_accuracy.py` checking `pattern in author` on line 107). The
  mock diverges from production behavior here. This is a pre-existing gap unrelated
  to FTS5.
- `summary` — Typically a subset of `content`, so indexing it separately would add
  FTS storage without meaningful search improvement.

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

FTS5 tokenized matching differs from LIKE substring matching in several areas:

### General Token vs Substring Differences

| Scenario | LIKE (current) | FTS5 (new) | Impact |
|---|---|---|---|
| **Substring in word** (`"cloud"` matching `"Cloudflare"`) | Matches | Does not match (token boundary) | Minor — full words still match. Prefix search (`cloud*`) can be added later. |
| **HTML tags in content** | Matches tags (`<div>`) | Tokenizer strips markup context | Neutral — users don't search for HTML tags. |
| **Special chars** (`test_func`) | Matches as substring | Tokenized as `test` and `func` | Matches more broadly (both words anywhere). |
| **Relevance ranking** | None (ORDER BY published_at) | BM25 available (not used in v1) | Future improvement possible. |
| **Case sensitivity** | D1 LIKE is case-insensitive | FTS5 unicode61 is case-insensitive | No change. |

### Phrase Search Tokenization Details

Phrase search is the mode most affected by FTS5 tokenization. The current LIKE
phrase search (`LIKE '%error handling%'`) matches the **exact byte sequence** in the
text. FTS5 phrase search (`MATCH '"error handling"'`) matches **adjacent tokens** in
order, which is subtly different.

| Phrase Query | LIKE (current) | FTS5 (new) | Notes |
|---|---|---|---|
| `"error handling"` | Matches exact substring | Matches adjacent tokens `error` + `handling` | Equivalent for normal text. |
| `"day-to-day"` | Matches exact substring `day-to-day` | `unicode61` tokenizes on hyphens → tokens `day`, `to`, `day`. Phrase match looks for 3 adjacent tokens. | **Both match**, but FTS5 treats hyphens as token separators. A phrase `"day-to-day"` in FTS5 is equivalent to `"day to day"`. |
| `"error.handling"` | Matches exact substring `error.handling` | Tokens `error` + `handling` (period is separator). Matches `error handling` or `error. handling`. | FTS5 is more permissive — matches regardless of punctuation. |
| `"what the day-to-day looks like"` | Matches exact substring | Tokenizes to `what the day to day looks like` (7 tokens). Title tokenizes identically. | **Matches.** Verified against fixture test data. |

**Validation against fixture test queries:**

The `blog_posts.json` fixtures include two phrase searches:
1. `"what the day-to-day looks like"` → expects entry 1 ("What the day-to-day looks like").
   FTS5 tokenizes both query and title identically (including hyphen splitting), so
   the phrase match succeeds.
2. `'context is the work'` → expects entry 2 ("Context is the work"). Straightforward
   token sequence match, no special characters.

Both pass with FTS5.

### Impact Assessment

These differences are acceptable. The semantic search layer (Vectorize) covers
fuzzy/conceptual matching. FTS5 keyword search provides fast, precise token matching.
The primary risk (substring-within-word matching loss) can be addressed later with
prefix search (`*` operator) if user feedback warrants it.

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

**New file.** Verifies the migration SQL executes correctly against a real SQLite
database (Python's built-in `sqlite3` module).

Tests:

**Basic Migration:**

1. **Migration creates FTS5 table:** Run migration SQL, verify `entries_fts` exists
   via `PRAGMA table_list`.
2. **Backfill populates FTS5:** Insert entries before migration, run migration,
   verify FTS5 contains all entries via `SELECT count(*) FROM entries_fts`.
3. **Migration is idempotent:** Running migration twice doesn't error (due to
   `IF NOT EXISTS`).
4. **FTS5 MATCH works end-to-end:** Insert entries with known content, run
   MATCH queries, verify correct results returned.

**Trigger Tests:**

5. **Insert trigger:** Insert a new entry into `entries`, verify it appears in
   `entries_fts` via MATCH query.
6. **Delete trigger:** Delete an entry from `entries`, verify it's removed from
   `entries_fts` (MATCH no longer returns it).
7. **Update trigger — title change:** Update an entry's title, verify the old title
   no longer matches and the new title does match in FTS5.
8. **UPSERT trigger interaction:** Execute `INSERT ... ON CONFLICT DO UPDATE` against
   an existing entry with a new title. Verify:
   - The old title no longer matches in FTS5
   - The new title matches in FTS5
   - The FTS index has exactly one entry for this rowid (not duplicated)
9. **Batch delete trigger:** Delete multiple entries in one statement
   (`DELETE FROM entries WHERE id IN (?, ?)`), verify all are removed from FTS.

**Rebuild and Integrity:**

10. **Rebuild command:** Delete entries directly from `entries` without triggers
    (using a raw DELETE that bypasses triggers, e.g., by disabling triggers
    temporarily), then run `INSERT INTO entries_fts(entries_fts) VALUES('rebuild')`.
    Verify FTS index matches the entries table.
11. **Integrity-check command:** After normal operations, verify
    `INSERT INTO entries_fts(entries_fts) VALUES('integrity-check')` does not raise.

**NULL Handling:**

12. **NULL title:** Insert entry with `title = NULL, content = 'some text'`. Verify
    MATCH on 'some text' returns the entry. Verify MATCH on random word does not
    return the entry.
13. **NULL content:** Insert entry with `title = 'some title', content = NULL`.
    Verify MATCH on 'some title' returns the entry.
14. **Update NULL to non-NULL:** Insert entry with NULL title, then UPDATE to a real
    title. Verify the new title matches in FTS5.

**Cascade DELETE (documenting known behavior):**

15. **Cascade delete does not clean FTS:** Set up feeds + entries with triggers.
    Delete a feed (CASCADE). Verify entries are gone from `entries` table. Verify
    stale tokens remain in `entries_fts`. Verify a MATCH query with JOIN to `entries`
    does NOT return the stale entries (JOIN filters them out). Then run `rebuild` and
    verify FTS is clean.

**Phrase Search:**

16. **Hyphenated phrase:** Insert entry with title `"day-to-day"`. Verify phrase
    MATCH `'"day-to-day"'` finds it (tokenizes to `day to day`).
17. **Punctuated phrase:** Insert entry with content `"error.handling patterns"`.
    Verify phrase MATCH `'"error handling"'` finds it (period is token separator).

#### F. Property-Based Tests: `tests/unit/test_search_query_properties.py`

**New file.** Uses [Hypothesis](https://hypothesis.readthedocs.io/) to verify
invariants that must hold for **any** input, not just hand-picked examples.

Property-based testing is especially valuable here because:
- The escaping logic must be correct for arbitrary user input (including adversarial)
- The SQL structure must be valid for any query shape
- FTS5 MATCH expressions must parse without syntax errors for any input

**Properties to test:**

1. **Placeholder-param count invariant:** For any non-empty query string `q` and any
   `is_phrase_search` value, `result.sql.count('?') == len(result.params)`.

   ```python
   @given(q=text(min_size=1, max_size=200), phrase=booleans())
   def test_placeholder_count_matches_params(q, phrase):
       q = q.strip()
       assume(len(q) >= 1)
       builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=phrase)
       result = builder.build(limit=50)
       assert result.sql.count("?") == len(result.params)
   ```

2. **Params are always tuple:** For any input, `isinstance(result.params, tuple)`.

3. **Idempotency:** For any input, calling `build()` twice returns identical
   `(sql, params)`.

4. **No raw user input in SQL:** For any query string `q` containing at least one
   alphanumeric character, `q` must NOT appear literally in `result.sql` — it must
   only appear inside `result.params` (i.e., behind bind placeholders).

   ```python
   @given(q=from_regex(r'[a-zA-Z]{2,20}', fullmatch=True))
   def test_user_input_never_in_sql(q):
       builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=False)
       result = builder.build(limit=50)
       assert q not in result.sql
   ```

5. **FTS5 MATCH expression is valid SQLite:** For any query string, the generated
   MATCH expression (first element of `result.params`) must be parseable by SQLite's
   FTS5 engine. Verify by executing against a real SQLite FTS5 table in the test.

   ```python
   @given(q=text(min_size=1, max_size=100))
   def test_fts5_expression_is_valid_sqlite(q, fts5_db):
       q = q.strip()
       assume(len(q) >= 1)
       builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=False)
       result = builder.build(limit=50)
       match_expr = result.params[0]
       # Must not raise "fts5: syntax error"
       fts5_db.execute(
           "SELECT rowid FROM test_fts WHERE test_fts MATCH ?", (match_expr,)
       )
   ```

   This is the most important property test. It catches escaping bugs that
   hand-written tests miss — e.g., a query like `"` (just a double quote), `""`,
   `"" ""`, `*`, `NEAR`, etc.

6. **Escaping round-trip preserves token content:** For any string `s`,
   `escape_fts5_token(s)` must produce output that starts and ends with `"` and
   contains the original text (with internal `"` doubled).

   ```python
   @given(s=text(min_size=1, max_size=50))
   def test_escape_roundtrip(s):
       escaped = FTS5SearchQueryBuilder.escape_fts5_token(s)
       assert escaped.startswith('"')
       assert escaped.endswith('"')
       inner = escaped[1:-1]
       assert inner.replace('""', '"') == s
   ```

7. **Multi-word commutativity:** For any two non-empty words `a` and `b`, searching
   for `"a b"` and `"b a"` (non-phrase) should produce MATCH expressions with the
   same tokens (FTS5 implicit AND is unordered). Both should have exactly 2 quoted
   tokens in the MATCH expression.

8. **Phrase vs non-phrase are distinct:** For any query with 2+ words, the phrase
   MATCH expression should differ from the non-phrase MATCH expression (phrase wraps
   the entire sequence in one quoted string; non-phrase wraps each word separately).

   ```python
   @given(w1=from_regex(r'[a-z]{3,10}', fullmatch=True),
          w2=from_regex(r'[a-z]{3,10}', fullmatch=True))
   def test_phrase_vs_nonphrase_differ(w1, w2):
       assume(w1 != w2)
       q = f"{w1} {w2}"
       phrase = FTS5SearchQueryBuilder(query=q, is_phrase_search=True).build()
       nonphrase = FTS5SearchQueryBuilder(query=q, is_phrase_search=False).build()
       assert phrase.params[0] != nonphrase.params[0]
   ```

9. **SQL structure invariant:** For any non-empty query, the SQL must contain
   `entries_fts MATCH`, `JOIN entries_fts`, and must NOT contain `LIKE`.

10. **words_truncated consistency:** For any query with `N` whitespace-separated
    tokens and `max_words = M`, `words_truncated == (N > M)`.

**Fixture: `fts5_db`**

Property tests 5 requires a real SQLite database with an FTS5 table. Create a
session-scoped pytest fixture:

```python
@pytest.fixture(scope="session")
def fts5_db():
    """Real SQLite DB with an FTS5 table for validating MATCH expressions."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE test_fts USING fts5(title, content)")
    conn.execute("INSERT INTO test_fts(title, content) VALUES ('test', 'test content')")
    yield conn
    conn.close()
```

#### G. Property-Based Tests for Trigger Consistency: `tests/unit/test_fts5_trigger_properties.py`

**New file.** Uses Hypothesis to verify the FTS index stays consistent with the
entries table across arbitrary sequences of mutations.

1. **Insert/delete consistency:** For any sequence of N inserts followed by M deletes
   (M <= N), the FTS index row count equals the entries table row count.

   ```python
   @given(
       titles=lists(text(min_size=1, max_size=50), min_size=1, max_size=20),
       delete_indices=lists(integers(min_value=0), max_size=10),
   )
   def test_fts_count_matches_entries_count(fts5_full_db, titles, delete_indices):
       # Insert entries
       for i, title in enumerate(titles):
           fts5_full_db.execute(
               "INSERT INTO entries(feed_id, guid, title, content) VALUES (1, ?, ?, '')",
               (f"guid-{i}", title),
           )
       # Delete some
       ids = [row[0] for row in fts5_full_db.execute("SELECT id FROM entries").fetchall()]
       for idx in delete_indices:
           if ids:
               target = ids.pop(idx % len(ids))
               fts5_full_db.execute("DELETE FROM entries WHERE id = ?", (target,))
       # Verify counts match
       entry_count = fts5_full_db.execute("SELECT count(*) FROM entries").fetchone()[0]
       fts_count = fts5_full_db.execute("SELECT count(*) FROM entries_fts").fetchone()[0]
       assert entry_count == fts_count
   ```

2. **Update consistency:** For any entry, after updating its title, the old title
   should not match and the new title should match.

3. **Rebuild idempotency:** After any sequence of mutations, running `rebuild`
   should not change the set of matchable tokens (the index is already consistent
   via triggers, so rebuild is a no-op).

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

### Step 4: Extend Reindex Endpoint
- Add FTS5 `rebuild` command to `_reindex_all_entries()` in `main.py`
- Run `INSERT INTO entries_fts(entries_fts) VALUES('rebuild')` before the
  Vectorize re-indexing loop

### Step 5: Update Test Mocks
- Update `MockD1Statement._filter_results()` in `conftest.py` to handle FTS5 SQL
- Update `MockD1WithFixtures` in `test_search_accuracy.py` to detect MATCH queries
- Ensure mock FTS5 matching simulates tokenized (word-boundary) matching

### Step 6: Update Unit Tests
- Add `TestFTS5*` test classes
- Update existing tests that assert on LIKE SQL to assert on MATCH SQL
- Keep old LIKE tests in a separate `TestSearchQueryBuilderLegacy` class

### Step 7: Add Migration Tests (Section E)
- Create `tests/unit/test_fts5_migration.py`
- Verify migration, triggers, UPSERT interaction, rebuild, NULL handling,
  cascade DELETE behavior, and phrase search tokenization

### Step 8: Add Property-Based Tests (Section F, G)
- Add `hypothesis` to dev dependencies
- Create `tests/unit/test_search_query_properties.py` (query builder properties)
- Create `tests/unit/test_fts5_trigger_properties.py` (trigger consistency)

### Step 9: Add Performance Benchmark (Section D)
- Create `tests/benchmark/test_search_performance.py`
- Verify FTS5 is at least as fast as LIKE across all dataset sizes

### Step 10: Verify All Tests Pass
- Run full test suite
- Verify no regressions in search accuracy tests
- Verify performance benchmark assertions pass
- Verify property-based tests pass with default Hypothesis settings

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| D1 FTS5 case sensitivity (`fts5` must be lowercase) | Use lowercase in migration SQL. Add a test that verifies the migration runs. |
| FTS5 export limitation (can't export DB with virtual tables) | Document in ARCHITECTURE.md. Workaround: drop FTS5 table before export, recreate after. |
| Token boundary matching differs from LIKE substring matching | Semantic search (Vectorize) covers fuzzy matching. Monitor search quality post-deploy. |
| External content mode requires manual sync | Triggers handle sync automatically. Test trigger correctness with property-based tests (Section G). |
| Migration backfill on large tables | Backfill runs once. D1 handles this within migration execution. |
| Cascade DELETE leaves stale FTS tokens | JOIN in search query filters stale rowids. Periodic `rebuild` via admin endpoint cleans up. Stale data is storage-only, not correctness. (See Section 2, "Cascade DELETE".) |
| UPSERT fires UPDATE trigger, not INSERT | Verified behavior is correct: AFTER UPDATE trigger handles the delete-old + insert-new cycle. Tested explicitly (Section E.8). |
| FTS index corruption (dropped triggers, direct SQL) | `rebuild` command available via admin reindex endpoint. `integrity-check` available for diagnostics. (See Section 2b.) |
| NULL title/content in entries | FTS5 treats NULL as empty string. Triggers pass NULL transparently. Tested explicitly (Section E.12-14). |
| Hypothesis dependency for property-based tests | `hypothesis` is a dev-only test dependency. No production impact. |

## Files Changed

| File | Change |
|---|---|
| `migrations/006_create_fts5_index.sql` | **New.** FTS5 table, triggers, backfill. |
| `src/search_query.py` | **Modified.** Add `FTS5SearchQueryBuilder` class. Keep `SearchQueryBuilder`. |
| `src/main.py` | **Modified.** Swap builder class (1 line). Add FTS5 rebuild to `_reindex_all_entries()`. |
| `tests/conftest.py` | **Modified.** Update mock to handle MATCH SQL. |
| `tests/unit/test_search_query.py` | **Modified.** Add FTS5 test classes, keep LIKE tests. |
| `tests/unit/test_search_query_properties.py` | **New.** Hypothesis property-based tests for query builder. |
| `tests/unit/test_fts5_migration.py` | **New.** Migration, trigger, rebuild, NULL, cascade, phrase tests. |
| `tests/unit/test_fts5_trigger_properties.py` | **New.** Hypothesis property-based tests for trigger consistency. |
| `tests/integration/test_search_accuracy.py` | **Modified.** Update mock to handle MATCH SQL. |
| `tests/benchmark/test_search_performance.py` | **New.** Performance comparison. |
| `docs/ARCHITECTURE.md` | **Modified.** Document FTS5 usage and export limitation. |
