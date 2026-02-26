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
        builder = SearchQueryBuilder(
            query="one two three four five", is_phrase_search=False, max_words=3
        )
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


class TestSearchQueryBoundaries:
    """Tests for boundary conditions in search queries."""

    def test_query_exactly_2_chars_builds(self):
        """2-char query builds successfully."""
        builder = SearchQueryBuilder(query="ab", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.sql
        assert "%ab%" in result.params

    def test_query_single_char_builds(self):
        """Even 1-char builds (handler rejects, not builder)."""
        builder = SearchQueryBuilder(query="a", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.sql
        assert "%a%" in result.params

    def test_query_1000_chars_builds(self):
        """Very long query builds successfully."""
        long_query = "x" * 1000
        builder = SearchQueryBuilder(query=long_query, is_phrase_search=True)
        result = builder.build(limit=50)

        assert result.sql
        assert f"%{long_query}%" in result.params

    def test_exactly_max_words_no_truncation(self):
        """10 words -> words_truncated=False."""
        query = " ".join(f"word{i}" for i in range(10))
        builder = SearchQueryBuilder(query=query, is_phrase_search=False, max_words=10)
        result = builder.build(limit=50)

        assert result.words_truncated is False

    def test_exactly_max_plus_one_truncation(self):
        """11 words -> words_truncated=True."""
        query = " ".join(f"word{i}" for i in range(11))
        builder = SearchQueryBuilder(query=query, is_phrase_search=False, max_words=10)
        result = builder.build(limit=50)

        assert result.words_truncated is True

    def test_consecutive_spaces_handled(self):
        """'word  word' doesn't produce empty words."""
        builder = SearchQueryBuilder(query="word  word", is_phrase_search=False)
        result = builder.build(limit=50)

        # 2 words x 2 (title + content) = 4 patterns + 1 limit
        assert len(result.params) == 5
        assert "%word%" in result.params

    def test_tabs_and_newlines_as_whitespace(self):
        """'\\tword\\nword' splits correctly."""
        builder = SearchQueryBuilder(query="\tword1\nword2", is_phrase_search=False)
        result = builder.build(limit=50)

        # 2 words x 2 (title + content) = 4 patterns + 1 limit
        assert len(result.params) == 5
        assert "%word1%" in result.params
        assert "%word2%" in result.params

    def test_all_whitespace_words_after_split(self):
        """Query with only spaces raises ValueError."""
        builder = SearchQueryBuilder(query="   ", is_phrase_search=False)

        with pytest.raises(ValueError, match="cannot be empty"):
            builder.build()


class TestSearchQuerySecurityDeep:
    """Deep tests for SQL injection prevention."""

    def test_sql_comment_double_dash_in_params(self):
        """'--' stays in params, not in SQL."""
        builder = SearchQueryBuilder(query="test -- drop", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "%--%" in result.params
        assert "test" not in result.sql
        assert "--" not in result.sql

    def test_sql_comment_block_in_params(self):
        """'/* */' stays in params."""
        builder = SearchQueryBuilder(query="test /* comment */ end", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "%/*%" in result.params
        assert "%*/%" in result.params
        assert "/*" not in result.sql

    def test_union_select_in_params(self):
        """'UNION SELECT' stays in params."""
        builder = SearchQueryBuilder(query="UNION SELECT password", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "%UNION%" in result.params
        assert "%SELECT%" in result.params
        # The only SELECT in SQL should be the base query, not injected
        assert "UNION" not in result.sql

    def test_semicolon_stacked_query_in_params(self):
        """';' stays in params."""
        builder = SearchQueryBuilder(query="test; DROP TABLE entries", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "%test;%" in result.params
        assert ";" not in result.sql

    def test_backtick_identifier_in_params(self):
        """Backticks stay in params."""
        builder = SearchQueryBuilder(query="`entries`", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "%`entries`%" in result.params
        assert "`entries`" not in result.sql

    def test_null_byte_handled(self):
        """'\\x00' in query doesn't crash."""
        builder = SearchQueryBuilder(query="test\x00value", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.sql
        assert result.params

    def test_newline_in_query_handled(self):
        """'\\n' in query handled."""
        builder = SearchQueryBuilder(query="test\nvalue", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.sql
        assert result.params

    def test_sql_or_1_equals_1_in_params(self):
        """\"' OR '1'='1\" stays in params."""
        builder = SearchQueryBuilder(query="' OR '1'='1", is_phrase_search=True)
        result = builder.build(limit=50)

        assert "%' OR '1'='1%" in result.params
        assert "'1'='1" not in result.sql


class TestSearchQueryUnicode:
    """Tests for Unicode handling in search queries."""

    def test_emoji_in_query(self):
        """Emoji in query builds successfully."""
        builder = SearchQueryBuilder(query="\U0001f50d search", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.sql
        assert "%\U0001f50d%" in result.params
        assert "%search%" in result.params

    def test_cjk_characters(self):
        """CJK characters build successfully."""
        builder = SearchQueryBuilder(
            query="\u65e5\u672c\u8a9e\u30c6\u30b9\u30c8", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert result.sql
        assert "%\u65e5\u672c\u8a9e\u30c6\u30b9\u30c8%" in result.params

    def test_arabic_text(self):
        """Arabic text builds successfully."""
        builder = SearchQueryBuilder(query="\u0628\u062d\u062b", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.sql
        assert "%\u0628\u062d\u062b%" in result.params

    def test_mixed_scripts(self):
        """Mixed scripts split into 3 words."""
        builder = SearchQueryBuilder(
            query="test \u0442\u0435\u0441\u0442 \u6d4b\u8bd5",
            is_phrase_search=False,
        )
        result = builder.build(limit=50)

        # 3 words x 2 (title + content) = 6 patterns + 1 limit
        assert len(result.params) == 7
        assert "%test%" in result.params
        assert "%\u0442\u0435\u0441\u0442%" in result.params
        assert "%\u6d4b\u8bd5%" in result.params


class TestSearchQueryDeterminism:
    """Tests that search query building is deterministic."""

    def test_same_input_same_output(self):
        """Same query+params produce identical SQL+params."""
        builder1 = SearchQueryBuilder(query="test query", is_phrase_search=False)
        builder2 = SearchQueryBuilder(query="test query", is_phrase_search=False)

        result1 = builder1.build(limit=50)
        result2 = builder2.build(limit=50)

        assert result1.sql == result2.sql
        assert result1.params == result2.params

    def test_build_called_twice_same_result(self):
        """Calling build() twice returns same result."""
        builder = SearchQueryBuilder(query="test query", is_phrase_search=False)

        result1 = builder.build(limit=50)
        result2 = builder.build(limit=50)

        assert result1.sql == result2.sql
        assert result1.params == result2.params

    def test_params_are_tuple(self):
        """Params is always a tuple (immutable)."""
        builder = SearchQueryBuilder(query="test", is_phrase_search=False)
        result = builder.build(limit=50)

        assert isinstance(result.params, tuple)

    def test_placeholder_count_matches_params(self):
        """Count of '?' in SQL == len(params)."""
        # Single word
        builder1 = SearchQueryBuilder(query="test", is_phrase_search=False)
        result1 = builder1.build(limit=50)
        assert result1.sql.count("?") == len(result1.params)

        # Multi word
        builder2 = SearchQueryBuilder(query="one two three", is_phrase_search=False)
        result2 = builder2.build(limit=50)
        assert result2.sql.count("?") == len(result2.params)

        # Phrase
        builder3 = SearchQueryBuilder(query="exact phrase", is_phrase_search=True)
        result3 = builder3.build(limit=50)
        assert result3.sql.count("?") == len(result3.params)


class TestSearchQueryMutations:
    """Tests that different inputs produce meaningfully different outputs."""

    def test_phrase_vs_word_different_sql(self):
        """'test' phrase vs word produces different SQL structure."""
        phrase_builder = SearchQueryBuilder(query="test word", is_phrase_search=True)
        word_builder = SearchQueryBuilder(query="test word", is_phrase_search=False)

        phrase_result = phrase_builder.build(limit=50)
        word_result = word_builder.build(limit=50)

        # Phrase search uses the full phrase as one LIKE; word search uses AND
        assert phrase_result.sql != word_result.sql or phrase_result.params != word_result.params

    def test_adding_word_changes_param_count(self):
        """2-word query has more params than 1-word."""
        builder1 = SearchQueryBuilder(query="python", is_phrase_search=False)
        builder2 = SearchQueryBuilder(query="python error", is_phrase_search=False)

        result1 = builder1.build(limit=50)
        result2 = builder2.build(limit=50)

        assert len(result2.params) > len(result1.params)

    def test_different_limit_changes_last_param(self):
        """limit=10 vs limit=50 changes last param."""
        builder = SearchQueryBuilder(query="test", is_phrase_search=False)

        result10 = builder.build(limit=10)
        result50 = builder.build(limit=50)

        assert result10.params[-1] == 10
        assert result50.params[-1] == 50

    def test_escaping_changes_output(self):
        """'test_func' has different params than 'test func'."""
        builder_underscore = SearchQueryBuilder(query="test_func", is_phrase_search=False)
        builder_space = SearchQueryBuilder(query="test func", is_phrase_search=False)

        result_underscore = builder_underscore.build(limit=50)
        result_space = builder_space.build(limit=50)

        # "test_func" is a single word with escaped underscore
        # "test func" is two separate words
        assert result_underscore.params != result_space.params
