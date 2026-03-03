# tests/unit/test_search_query_properties.py
"""Property-based tests for FTS5SearchQueryBuilder using Hypothesis.

Verifies invariants that must hold for ANY input, not just hand-picked examples.
The most critical property: every generated FTS5 MATCH expression must be valid
SQLite syntax (tested against a real in-memory FTS5 table).
"""

import sqlite3

import pytest
from hypothesis import assume, given, settings
from hypothesis.strategies import booleans, from_regex, integers, text

from src.search_query import FTS5SearchQueryBuilder


@pytest.fixture(scope="module")
def fts5_db():
    """Real SQLite DB with an FTS5 table for validating MATCH expressions."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE test_fts USING fts5(title, content)")
    conn.execute(
        "INSERT INTO test_fts(title, content) VALUES ('test word', 'test content word')"
    )
    conn.commit()
    yield conn
    conn.close()


class TestQueryBuilderProperties:
    """Property-based tests for FTS5SearchQueryBuilder."""

    @given(q=text(min_size=1, max_size=200), phrase=booleans())
    @settings(max_examples=200)
    def test_placeholder_count_matches_params(self, q, phrase):
        """For any input, placeholder count equals param count."""
        q = q.strip()
        assume(len(q) >= 1)
        builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=phrase)
        result = builder.build(limit=50)
        assert result.sql.count("?") == len(result.params)

    @given(q=text(min_size=1, max_size=200), phrase=booleans())
    @settings(max_examples=200)
    def test_params_are_tuple(self, q, phrase):
        """For any input, params is a tuple."""
        q = q.strip()
        assume(len(q) >= 1)
        builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=phrase)
        result = builder.build(limit=50)
        assert isinstance(result.params, tuple)

    @given(q=text(min_size=1, max_size=100), phrase=booleans())
    @settings(max_examples=100)
    def test_idempotency(self, q, phrase):
        """For any input, build() called twice returns identical results."""
        q = q.strip()
        assume(len(q) >= 1)
        builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=phrase)
        r1 = builder.build(limit=50)
        r2 = builder.build(limit=50)
        assert r1.sql == r2.sql
        assert r1.params == r2.params

    @given(q=from_regex(r"[a-zA-Z]{5,20}", fullmatch=True))
    @settings(max_examples=100)
    def test_user_input_never_in_sql(self, q):
        """Alphanumeric user input (5+ chars) never appears literally in SQL.

        Uses 5+ chars to avoid false positives from SQL keywords/column names
        that contain short substrings (e.g., 'id', 'at', 'ed').
        """
        builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=False)
        result = builder.build(limit=50)
        assert q not in result.sql

    @given(q=text(min_size=1, max_size=100), phrase=booleans())
    @settings(max_examples=200)
    def test_sql_structure_invariant(self, q, phrase):
        """SQL always contains MATCH and entries_fts, never LIKE."""
        q = q.strip()
        assume(len(q) >= 1)
        builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=phrase)
        result = builder.build(limit=50)
        assert "MATCH" in result.sql
        assert "entries_fts" in result.sql
        assert "LIKE" not in result.sql

    @given(q=text(min_size=1, max_size=100), phrase=booleans())
    @settings(max_examples=200)
    def test_exactly_two_placeholders(self, q, phrase):
        """FTS5 SQL always has exactly 2 placeholders."""
        q = q.strip()
        assume(len(q) >= 1)
        builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=phrase)
        result = builder.build(limit=50)
        assert result.sql.count("?") == 2
        assert len(result.params) == 2


class TestFTS5ExpressionValidity:
    """The most important property: generated MATCH expressions must be valid."""

    @given(q=text(min_size=1, max_size=100))
    @settings(max_examples=300)
    def test_non_phrase_match_is_valid_sqlite(self, q, fts5_db):
        """Non-phrase MATCH expression parses without error in real SQLite."""
        q = q.strip()
        assume(len(q) >= 1)
        builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=False)
        result = builder.build(limit=50)
        match_expr = result.params[0]
        # Must not raise "fts5: syntax error"
        fts5_db.execute(
            "SELECT rowid FROM test_fts WHERE test_fts MATCH ?", (match_expr,)
        )

    @given(q=text(min_size=1, max_size=100))
    @settings(max_examples=300)
    def test_phrase_match_is_valid_sqlite(self, q, fts5_db):
        """Phrase MATCH expression parses without error in real SQLite."""
        q = q.strip()
        assume(len(q) >= 1)
        builder = FTS5SearchQueryBuilder(query=q, is_phrase_search=True)
        result = builder.build(limit=50)
        match_expr = result.params[0]
        fts5_db.execute(
            "SELECT rowid FROM test_fts WHERE test_fts MATCH ?", (match_expr,)
        )


class TestEscapingProperties:
    """Property-based tests for escape_fts5_token."""

    @given(s=text(min_size=0, max_size=50))
    @settings(max_examples=200)
    def test_escape_roundtrip(self, s):
        """Escaped token starts/ends with quote, inner content round-trips.

        Null bytes are stripped (they cause FTS5 errors), so round-trip
        equality is against the null-stripped input.
        """
        escaped = FTS5SearchQueryBuilder.escape_fts5_token(s)
        assert escaped.startswith('"')
        assert escaped.endswith('"')
        inner = escaped[1:-1]
        assert inner.replace('""', '"') == s.replace("\x00", "")

    @given(s=text(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_escaped_token_is_valid_fts5(self, s, fts5_db):
        """Any escaped token is a valid FTS5 expression."""
        escaped = FTS5SearchQueryBuilder.escape_fts5_token(s)
        # Must not raise
        fts5_db.execute(
            "SELECT rowid FROM test_fts WHERE test_fts MATCH ?", (escaped,)
        )


class TestPhraseVsNonPhrase:
    """Property-based tests for phrase vs non-phrase distinction."""

    @given(
        w1=from_regex(r"[a-z]{3,10}", fullmatch=True),
        w2=from_regex(r"[a-z]{3,10}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_phrase_vs_nonphrase_differ(self, w1, w2):
        """For any 2-word query, phrase and non-phrase produce different MATCH."""
        assume(w1 != w2)
        q = f"{w1} {w2}"
        phrase = FTS5SearchQueryBuilder(query=q, is_phrase_search=True).build()
        nonphrase = FTS5SearchQueryBuilder(query=q, is_phrase_search=False).build()
        assert phrase.params[0] != nonphrase.params[0]
        # Phrase: '"w1 w2"' (one quoted string)
        assert phrase.params[0] == f'"{q}"'
        # Non-phrase: '"w1" "w2"' (two quoted strings)
        assert nonphrase.params[0] == f'"{w1}" "{w2}"'


class TestWordsTruncated:
    """Property-based tests for words_truncated consistency."""

    @given(
        num_words=integers(min_value=1, max_value=30),
        max_words=integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100)
    def test_words_truncated_consistency(self, num_words, max_words):
        """words_truncated == (num_words > max_words) for non-phrase search."""
        query = " ".join(f"w{i}" for i in range(num_words))
        builder = FTS5SearchQueryBuilder(
            query=query, is_phrase_search=False, max_words=max_words
        )
        result = builder.build(limit=50)
        assert result.words_truncated == (num_words > max_words)
