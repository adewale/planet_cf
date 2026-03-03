# tests/unit/test_search_query.py
"""Tests for the search query builder."""

import pytest

from src.search_query import FTS5SearchQueryBuilder, SearchQueryBuilder, SearchQueryResult


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


# =============================================================================
# FTS5SearchQueryBuilder Tests
# =============================================================================


class TestFTS5Escaping:
    """Tests for FTS5 token escaping."""

    def test_simple_word(self):
        """Simple word is wrapped in double quotes."""
        result = FTS5SearchQueryBuilder.escape_fts5_token("python")
        assert result == '"python"'

    def test_double_quotes_are_doubled(self):
        """Internal double quotes are doubled."""
        result = FTS5SearchQueryBuilder.escape_fts5_token('test "quoted" word')
        assert result == '"test ""quoted"" word"'

    def test_single_quotes_pass_through(self):
        """Single quotes are not special in FTS5."""
        result = FTS5SearchQueryBuilder.escape_fts5_token("it's working")
        assert result == "\"it's working\""

    def test_fts5_operators_are_quoted(self):
        """FTS5 operators (OR, AND, NOT, NEAR) are neutralized by quoting."""
        for op in ["OR", "AND", "NOT", "NEAR"]:
            result = FTS5SearchQueryBuilder.escape_fts5_token(op)
            assert result == f'"{op}"'

    def test_asterisk_is_quoted(self):
        """Asterisk (prefix operator) is neutralized by quoting."""
        result = FTS5SearchQueryBuilder.escape_fts5_token("test*")
        assert result == '"test*"'

    def test_parentheses_are_quoted(self):
        """Parentheses are neutralized by quoting."""
        result = FTS5SearchQueryBuilder.escape_fts5_token("(test)")
        assert result == '"(test)"'

    def test_plus_caret_are_quoted(self):
        """Plus and caret are neutralized by quoting."""
        result = FTS5SearchQueryBuilder.escape_fts5_token("^test+")
        assert result == '"^test+"'

    def test_empty_string(self):
        """Empty string produces empty quoted string."""
        result = FTS5SearchQueryBuilder.escape_fts5_token("")
        assert result == '""'

    def test_only_double_quotes(self):
        """String of only double quotes is properly escaped."""
        result = FTS5SearchQueryBuilder.escape_fts5_token('""')
        # Input: "" (2 chars) → each " doubled → """" (4 chars) → wrapped → """""" (6 chars)
        assert result == '""""""'


class TestFTS5PhraseSearch:
    """Tests for FTS5 phrase search query building."""

    def test_phrase_search_query(self):
        """Phrase search builds correct FTS5 MATCH SQL."""
        builder = FTS5SearchQueryBuilder(query="error handling", is_phrase_search=True)
        result = builder.build(limit=50)

        assert "entries_fts MATCH ?" in result.sql
        assert "JOIN entries_fts fts ON e.id = fts.rowid" in result.sql
        assert "LIMIT ?" in result.sql
        assert result.params[0] == '"error handling"'
        assert result.params[1] == 50
        assert result.words_truncated is False

    def test_phrase_search_escapes_double_quotes(self):
        """Phrase search escapes double quotes in phrase."""
        builder = FTS5SearchQueryBuilder(query='say "hello"', is_phrase_search=True)
        result = builder.build(limit=10)

        assert result.params[0] == '"say ""hello"""'

    def test_phrase_has_exactly_two_placeholders(self):
        """Phrase search always has exactly 2 params (match + limit)."""
        builder = FTS5SearchQueryBuilder(query="error handling", is_phrase_search=True)
        result = builder.build(limit=50)

        assert result.sql.count("?") == 2
        assert len(result.params) == 2


class TestFTS5SingleWord:
    """Tests for FTS5 single-word search query building."""

    def test_single_word_query(self):
        """Single word search builds correct MATCH SQL."""
        builder = FTS5SearchQueryBuilder(query="python", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "entries_fts MATCH ?" in result.sql
        assert result.params[0] == '"python"'
        assert result.params[1] == 50

    def test_single_word_with_special_chars(self):
        """Single word with special chars is quoted."""
        builder = FTS5SearchQueryBuilder(query="test*func", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.params[0] == '"test*func"'


class TestFTS5MultiWord:
    """Tests for FTS5 multi-word search query building."""

    def test_multi_word_query(self):
        """Multi-word search builds MATCH with space-separated quoted tokens."""
        builder = FTS5SearchQueryBuilder(
            query="python error handling", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert "entries_fts MATCH ?" in result.sql
        # Each word is individually quoted (implicit AND)
        assert result.params[0] == '"python" "error" "handling"'
        assert result.params[1] == 50
        # Always 2 params for FTS5: match expression + limit
        assert len(result.params) == 2

    def test_multi_word_truncation(self):
        """Words beyond max limit are truncated."""
        long_query = " ".join(f"word{i}" for i in range(15))
        builder = FTS5SearchQueryBuilder(
            query=long_query, is_phrase_search=False, max_words=10
        )
        result = builder.build(limit=50)

        assert result.words_truncated is True
        # Still only 2 params for FTS5
        assert len(result.params) == 2
        # Should have exactly 10 quoted tokens
        assert result.params[0].count('"') == 20  # 10 words x 2 quotes each

    def test_multi_word_respects_custom_max(self):
        """Custom max_words limit is respected."""
        builder = FTS5SearchQueryBuilder(
            query="one two three four five", is_phrase_search=False, max_words=3
        )
        result = builder.build(limit=50)

        assert result.words_truncated is True
        assert result.params[0] == '"one" "two" "three"'

    def test_multi_word_escapes_special_chars(self):
        """Special chars in individual words are quoted."""
        builder = FTS5SearchQueryBuilder(
            query="test*func OR value", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert result.params[0] == '"test*func" "OR" "value"'


class TestFTS5FromRawQuery:
    """Tests for creating FTS5 builder from raw query."""

    def test_detects_double_quoted_phrase(self):
        """Double-quoted query creates phrase search."""
        builder = FTS5SearchQueryBuilder.from_raw_query('"exact phrase"')

        assert builder.is_phrase_search is True
        assert builder.query == "exact phrase"

    def test_detects_single_quoted_phrase(self):
        """Single-quoted query creates phrase search."""
        builder = FTS5SearchQueryBuilder.from_raw_query("'exact phrase'")

        assert builder.is_phrase_search is True
        assert builder.query == "exact phrase"

    def test_unquoted_is_word_search(self):
        """Unquoted query creates word search."""
        builder = FTS5SearchQueryBuilder.from_raw_query("multiple words here")

        assert builder.is_phrase_search is False
        assert builder.query == "multiple words here"

    def test_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        builder = FTS5SearchQueryBuilder.from_raw_query("  test query  ")

        assert builder.query == "test query"

    def test_passes_max_words(self):
        """Custom max_words is passed through."""
        builder = FTS5SearchQueryBuilder.from_raw_query(
            "one two three four", max_words=2
        )

        assert builder.max_words == 2


class TestFTS5Validation:
    """Tests for FTS5 query validation."""

    def test_empty_query_raises_error(self):
        """Empty query raises ValueError."""
        builder = FTS5SearchQueryBuilder(query="")

        with pytest.raises(ValueError, match="cannot be empty"):
            builder.build()

    def test_whitespace_only_raises_error(self):
        """Whitespace-only query raises ValueError."""
        builder = FTS5SearchQueryBuilder(query="   ")

        with pytest.raises(ValueError, match="cannot be empty"):
            builder.build()


class TestFTS5SecurityDeep:
    """Tests for FTS5 injection prevention."""

    def test_fts5_operators_in_query(self):
        """FTS5 operators (OR, AND, NOT) are quoted, not interpreted."""
        builder = FTS5SearchQueryBuilder(
            query="python OR javascript", is_phrase_search=False
        )
        result = builder.build(limit=50)

        # OR should be a quoted token, not an FTS5 operator
        assert result.params[0] == '"python" "OR" "javascript"'
        assert "?" in result.sql

    def test_near_operator_in_query(self):
        """NEAR operator is quoted."""
        builder = FTS5SearchQueryBuilder(
            query="test NEAR/3 value", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert '"NEAR/3"' in result.params[0]

    def test_column_filter_syntax(self):
        """Column filter syntax (title:test) is quoted."""
        builder = FTS5SearchQueryBuilder(
            query="title:injected", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert result.params[0] == '"title:injected"'

    def test_sql_injection_via_match(self):
        """SQL keywords in query are safely parameterized."""
        builder = FTS5SearchQueryBuilder(
            query="DROP TABLE users", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert "DROP" not in result.sql
        assert '"DROP"' in result.params[0]

    def test_null_byte_handled(self):
        """Null byte in query doesn't crash."""
        builder = FTS5SearchQueryBuilder(
            query="test\x00value", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert result.sql
        assert result.params

    def test_newline_in_query_handled(self):
        """Newline in query handled."""
        builder = FTS5SearchQueryBuilder(
            query="test\nvalue", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert result.sql
        assert result.params


class TestFTS5Unicode:
    """Tests for Unicode handling in FTS5 search queries."""

    def test_emoji_in_query(self):
        """Emoji in query builds successfully."""
        builder = FTS5SearchQueryBuilder(
            query="\U0001f50d search", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert result.sql
        assert '"\U0001f50d"' in result.params[0]
        assert '"search"' in result.params[0]

    def test_cjk_characters(self):
        """CJK characters build successfully."""
        builder = FTS5SearchQueryBuilder(
            query="\u65e5\u672c\u8a9e\u30c6\u30b9\u30c8", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert result.sql
        assert '"\u65e5\u672c\u8a9e\u30c6\u30b9\u30c8"' in result.params[0]

    def test_arabic_text(self):
        """Arabic text builds successfully."""
        builder = FTS5SearchQueryBuilder(
            query="\u0628\u062d\u062b", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert result.sql
        assert '"\u0628\u062d\u062b"' in result.params[0]

    def test_mixed_scripts(self):
        """Mixed scripts split into 3 quoted words."""
        builder = FTS5SearchQueryBuilder(
            query="test \u0442\u0435\u0441\u0442 \u6d4b\u8bd5",
            is_phrase_search=False,
        )
        result = builder.build(limit=50)

        # Always 2 params for FTS5
        assert len(result.params) == 2
        assert '"test"' in result.params[0]
        assert '"\u0442\u0435\u0441\u0442"' in result.params[0]
        assert '"\u6d4b\u8bd5"' in result.params[0]


class TestFTS5Determinism:
    """Tests that FTS5 search query building is deterministic."""

    def test_same_input_same_output(self):
        """Same query+params produce identical SQL+params."""
        builder1 = FTS5SearchQueryBuilder(query="test query", is_phrase_search=False)
        builder2 = FTS5SearchQueryBuilder(query="test query", is_phrase_search=False)

        result1 = builder1.build(limit=50)
        result2 = builder2.build(limit=50)

        assert result1.sql == result2.sql
        assert result1.params == result2.params

    def test_build_called_twice_same_result(self):
        """Calling build() twice returns same result."""
        builder = FTS5SearchQueryBuilder(query="test query", is_phrase_search=False)

        result1 = builder.build(limit=50)
        result2 = builder.build(limit=50)

        assert result1.sql == result2.sql
        assert result1.params == result2.params

    def test_params_are_tuple(self):
        """Params is always a tuple (immutable)."""
        builder = FTS5SearchQueryBuilder(query="test", is_phrase_search=False)
        result = builder.build(limit=50)

        assert isinstance(result.params, tuple)

    def test_placeholder_count_matches_params(self):
        """Count of '?' in SQL == len(params) for all query types."""
        for query, phrase in [
            ("test", False),
            ("one two three", False),
            ("exact phrase", True),
        ]:
            builder = FTS5SearchQueryBuilder(query=query, is_phrase_search=phrase)
            result = builder.build(limit=50)
            assert result.sql.count("?") == len(result.params)


class TestFTS5SQLStructure:
    """Tests for FTS5 SQL structure invariants."""

    def test_all_modes_use_match(self):
        """All search modes produce SQL with MATCH."""
        for query, phrase in [
            ("test", False),
            ("one two three", False),
            ("exact phrase", True),
        ]:
            builder = FTS5SearchQueryBuilder(query=query, is_phrase_search=phrase)
            result = builder.build(limit=50)
            assert "MATCH" in result.sql

    def test_all_modes_join_fts(self):
        """All search modes JOIN entries_fts."""
        for query, phrase in [
            ("test", False),
            ("one two three", False),
            ("exact phrase", True),
        ]:
            builder = FTS5SearchQueryBuilder(query=query, is_phrase_search=phrase)
            result = builder.build(limit=50)
            assert "entries_fts" in result.sql
            assert "JOIN entries_fts fts ON e.id = fts.rowid" in result.sql

    def test_no_like_in_sql(self):
        """FTS5 SQL does NOT contain LIKE."""
        for query, phrase in [
            ("test", False),
            ("one two three", False),
            ("exact phrase", True),
        ]:
            builder = FTS5SearchQueryBuilder(query=query, is_phrase_search=phrase)
            result = builder.build(limit=50)
            assert "LIKE" not in result.sql

    def test_exactly_two_placeholders(self):
        """FTS5 SQL always has exactly 2 placeholders (MATCH + LIMIT)."""
        for query, phrase in [
            ("test", False),
            ("one two three", False),
            ("exact phrase", True),
            (" ".join(f"w{i}" for i in range(15)), False),
        ]:
            builder = FTS5SearchQueryBuilder(query=query, is_phrase_search=phrase)
            result = builder.build(limit=50)
            assert result.sql.count("?") == 2


class TestFTS5Mutations:
    """Tests that different FTS5 inputs produce meaningfully different outputs."""

    def test_phrase_vs_word_different_params(self):
        """Phrase vs word search produce different MATCH expressions."""
        phrase = FTS5SearchQueryBuilder(
            query="test word", is_phrase_search=True
        ).build(limit=50)
        word = FTS5SearchQueryBuilder(
            query="test word", is_phrase_search=False
        ).build(limit=50)

        # Phrase: '"test word"' (one quoted string)
        # Non-phrase: '"test" "word"' (two quoted strings)
        assert phrase.params[0] != word.params[0]
        assert phrase.params[0] == '"test word"'
        assert word.params[0] == '"test" "word"'

    def test_different_limit_changes_last_param(self):
        """limit=10 vs limit=50 changes last param."""
        builder = FTS5SearchQueryBuilder(query="test", is_phrase_search=False)

        result10 = builder.build(limit=10)
        result50 = builder.build(limit=50)

        assert result10.params[-1] == 10
        assert result50.params[-1] == 50


class TestFTS5Boundaries:
    """Tests for FTS5 boundary conditions."""

    def test_query_single_char_builds(self):
        """1-char query builds (handler rejects, not builder)."""
        builder = FTS5SearchQueryBuilder(query="a", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.sql
        assert result.params[0] == '"a"'

    def test_query_1000_chars_builds(self):
        """Very long query builds successfully."""
        long_query = "x" * 1000
        builder = FTS5SearchQueryBuilder(query=long_query, is_phrase_search=True)
        result = builder.build(limit=50)

        assert result.sql
        assert result.params[0] == f'"{long_query}"'

    def test_exactly_max_words_no_truncation(self):
        """10 words -> words_truncated=False."""
        query = " ".join(f"word{i}" for i in range(10))
        builder = FTS5SearchQueryBuilder(
            query=query, is_phrase_search=False, max_words=10
        )
        result = builder.build(limit=50)

        assert result.words_truncated is False

    def test_exactly_max_plus_one_truncation(self):
        """11 words -> words_truncated=True."""
        query = " ".join(f"word{i}" for i in range(11))
        builder = FTS5SearchQueryBuilder(
            query=query, is_phrase_search=False, max_words=10
        )
        result = builder.build(limit=50)

        assert result.words_truncated is True

    def test_consecutive_spaces_handled(self):
        """'word  word' doesn't produce empty words."""
        builder = FTS5SearchQueryBuilder(query="word  word", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.params[0] == '"word" "word"'

    def test_tabs_and_newlines_as_whitespace(self):
        """Tabs and newlines split correctly."""
        builder = FTS5SearchQueryBuilder(
            query="\tword1\nword2", is_phrase_search=False
        )
        result = builder.build(limit=50)

        assert '"word1"' in result.params[0]
        assert '"word2"' in result.params[0]


class TestSearchQueryBuilderBackwardCompat:
    """Tests that old SearchQueryBuilder still works."""

    def test_old_class_still_importable(self):
        """SearchQueryBuilder is still importable."""
        assert SearchQueryBuilder is not None

    def test_old_class_produces_like_queries(self):
        """Old class still produces LIKE queries."""
        builder = SearchQueryBuilder(query="test", is_phrase_search=False)
        result = builder.build(limit=50)

        assert "LIKE" in result.sql
        assert "MATCH" not in result.sql

    def test_old_class_not_broken(self):
        """Old class basic functionality unchanged."""
        builder = SearchQueryBuilder(query="test query", is_phrase_search=False)
        result = builder.build(limit=50)

        assert result.sql.count("?") == len(result.params)
        assert isinstance(result.params, tuple)
