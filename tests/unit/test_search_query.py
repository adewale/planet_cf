# tests/unit/test_search_query.py
"""Tests for the search query builder."""

import pytest

from src.search_query import SearchQueryBuilder, SearchQueryResult


class TestSearchQueryBuilderEscaping:
    """Tests for SQL escaping in search queries."""

    def test_escapes_percent(self):
        """Percent sign is escaped for LIKE pattern."""
        result = SearchQueryBuilder.escape_like_pattern("100% complete")
        assert result == "100\\% complete"

    def test_escapes_underscore(self):
        """Underscore is escaped for LIKE pattern."""
        result = SearchQueryBuilder.escape_like_pattern("test_case")
        assert result == "test\\_case"

    def test_escapes_both_special_chars(self):
        """Both special chars are escaped."""
        result = SearchQueryBuilder.escape_like_pattern("50%_off")
        assert result == "50\\%\\_off"

    def test_no_escaping_needed(self):
        """Normal text passes through unchanged."""
        result = SearchQueryBuilder.escape_like_pattern("hello world")
        assert result == "hello world"


class TestSearchQueryBuilderPhraseSearch:
    """Tests for phrase search query building."""

    def test_phrase_search_query(self):
        """Phrase search builds correct SQL."""
        builder = SearchQueryBuilder(query="error handling", is_phrase_search=True)
        result = builder.build(limit=50)

        assert "e.title LIKE ? ESCAPE" in result.sql
        assert "e.content LIKE ? ESCAPE" in result.sql
        assert "LIMIT ?" in result.sql
        assert result.params[0] == "%error handling%"
        assert result.params[1] == "%error handling%"
        assert result.params[2] == 50
        assert result.words_truncated is False

    def test_phrase_search_escapes_special_chars(self):
        """Phrase search escapes special SQL chars."""
        builder = SearchQueryBuilder(query="100% coverage", is_phrase_search=True)
        result = builder.build(limit=10)

        assert result.params[0] == "%100\\% coverage%"


class TestSearchQueryBuilderSingleWord:
    """Tests for single word search query building."""

    def test_single_word_query(self):
        """Single word search builds correct SQL."""
        builder = SearchQueryBuilder(query="python", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "e.title LIKE ? ESCAPE" in result.sql
        assert "e.content LIKE ? ESCAPE" in result.sql
        assert result.params[0] == "%python%"
        assert result.params[1] == "%python%"
        assert result.params[2] == 50

    def test_single_word_with_special_chars(self):
        """Single word with special chars is escaped."""
        builder = SearchQueryBuilder(query="test_function", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.params[0] == "%test\\_function%"


class TestSearchQueryBuilderMultiWord:
    """Tests for multi-word search query building."""

    def test_multi_word_query(self):
        """Multi-word search builds correct SQL with AND conditions."""
        builder = SearchQueryBuilder(query="python error handling", is_phrase_search=False)
        result = builder.build(limit=50)

        # Should have title conditions AND content conditions
        assert "e.title LIKE ? ESCAPE" in result.sql
        assert "e.content LIKE ? ESCAPE" in result.sql
        # Should have 3 words x 2 (title + content) = 6 like patterns + 1 limit
        assert len(result.params) == 7
        assert result.params[0] == "%python%"
        assert result.params[1] == "%error%"
        assert result.params[2] == "%handling%"
        assert result.params[6] == 50

    def test_multi_word_truncation(self):
        """Words beyond max limit are truncated."""
        long_query = " ".join(f"word{i}" for i in range(15))
        builder = SearchQueryBuilder(query=long_query, is_phrase_search=False, max_words=10)
        result = builder.build(limit=50)

        assert result.words_truncated is True
        # 10 words x 2 (title + content) = 20 patterns + 1 limit
        assert len(result.params) == 21

    def test_multi_word_respects_custom_max(self):
        """Custom max_words limit is respected."""
        builder = SearchQueryBuilder(query="one two three four five", is_phrase_search=False, max_words=3)
        result = builder.build(limit=50)

        assert result.words_truncated is True
        # 3 words x 2 = 6 patterns + 1 limit
        assert len(result.params) == 7

    def test_multi_word_escapes_special_chars(self):
        """Special chars in individual words are escaped."""
        builder = SearchQueryBuilder(query="test_func 100%", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "%test\\_func%" in result.params
        assert "%100\\%%" in result.params


class TestSearchQueryBuilderFromRawQuery:
    """Tests for creating builder from raw query."""

    def test_detects_double_quoted_phrase(self):
        """Double-quoted query creates phrase search."""
        builder = SearchQueryBuilder.from_raw_query('"exact phrase"')

        assert builder.is_phrase_search is True
        assert builder.query == "exact phrase"

    def test_detects_single_quoted_phrase(self):
        """Single-quoted query creates phrase search."""
        builder = SearchQueryBuilder.from_raw_query("'exact phrase'")

        assert builder.is_phrase_search is True
        assert builder.query == "exact phrase"

    def test_unquoted_is_word_search(self):
        """Unquoted query creates word search."""
        builder = SearchQueryBuilder.from_raw_query("multiple words here")

        assert builder.is_phrase_search is False
        assert builder.query == "multiple words here"

    def test_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        builder = SearchQueryBuilder.from_raw_query("  test query  ")

        assert builder.query == "test query"

    def test_passes_max_words(self):
        """Custom max_words is passed through."""
        builder = SearchQueryBuilder.from_raw_query("one two three four", max_words=2)

        assert builder.max_words == 2


class TestSearchQueryBuilderValidation:
    """Tests for query validation."""

    def test_empty_query_raises_error(self):
        """Empty query raises ValueError."""
        builder = SearchQueryBuilder(query="")

        with pytest.raises(ValueError, match="cannot be empty"):
            builder.build()

    def test_whitespace_only_raises_error(self):
        """Whitespace-only query raises ValueError."""
        builder = SearchQueryBuilder(query="   ")

        with pytest.raises(ValueError, match="cannot be empty"):
            builder.build()


class TestSearchQueryBuilderSQLInjection:
    """Tests for SQL injection prevention."""

    def test_single_quote_in_query(self):
        """Single quotes in query don't break SQL."""
        # Use phrase search to keep as single pattern
        builder = SearchQueryBuilder(query="it's working", is_phrase_search=True)
        result = builder.build(limit=50)

        # Single quote is in the bind parameter, not SQL
        assert result.params[0] == "%it's working%"
        # SQL should use placeholders, not interpolated values
        assert "?" in result.sql
        assert "it's" not in result.sql

    def test_double_quote_in_query(self):
        """Double quotes in query don't break SQL."""
        builder = SearchQueryBuilder(query='test "quoted" word', is_phrase_search=False)
        result = builder.build(limit=50)

        # Quotes are in bind parameters
        assert "?" in result.sql

    def test_sql_keywords_in_query(self):
        """SQL keywords in query are safely parameterized."""
        builder = SearchQueryBuilder(query="DROP TABLE users", is_phrase_search=False)
        result = builder.build(limit=50)

        # Should be in parameters, not SQL
        assert "DROP" not in result.sql
        assert "%DROP%" in result.params[0]

    def test_escape_characters_in_query(self):
        """Backslashes in query are handled correctly."""
        builder = SearchQueryBuilder(query="test\\path", is_phrase_search=False)
        result = builder.build(limit=50)

        # Backslash is in the parameter
        assert "%test\\path%" in result.params


class TestSearchQueryResult:
    """Tests for SearchQueryResult dataclass."""

    def test_result_properties(self):
        """SearchQueryResult has correct properties."""
        result = SearchQueryResult(
            sql="SELECT * FROM entries",
            params=("%test%", 50),
            words_truncated=True,
        )

        assert result.sql == "SELECT * FROM entries"
        assert result.params == ("%test%", 50)
        assert result.words_truncated is True

    def test_default_words_truncated(self):
        """words_truncated defaults to False."""
        result = SearchQueryResult(sql="SELECT 1", params=())

        assert result.words_truncated is False
