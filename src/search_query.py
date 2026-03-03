# src/search_query.py
"""Search query builder for constructing SQL search queries.

This module provides two builder classes:

- FTS5SearchQueryBuilder: Uses FTS5 MATCH for fast tokenized search (primary)
- SearchQueryBuilder: Uses LIKE patterns for substring search (legacy)

Both return SearchQueryResult with SQL and bind parameters.

Usage:
    builder = FTS5SearchQueryBuilder(query, is_phrase_search=True)
    result = builder.build(limit=50)
    rows = await db.prepare(result.sql).bind(*result.params).all()
"""

from dataclasses import dataclass, field

# Maximum number of words to search for (prevents DoS)
DEFAULT_MAX_SEARCH_WORDS = 10


@dataclass
class SearchQueryResult:
    """Result of building a search query.

    Attributes:
        sql: The SQL query string with placeholders
        params: Tuple of bind parameters
        words_truncated: True if words were truncated to max limit
    """

    sql: str
    params: tuple
    words_truncated: bool = False


@dataclass
class SearchQueryBuilder:
    """Builder for SQL search queries.

    Constructs SQL queries for keyword search with proper escaping
    and parameterization to prevent SQL injection.

    Attributes:
        query: The search query string
        is_phrase_search: Whether this is a phrase search (exact sequence)
        max_words: Maximum number of words to search for
    """

    query: str
    is_phrase_search: bool = False
    max_words: int = DEFAULT_MAX_SEARCH_WORDS
    _words: list[str] = field(default_factory=list, init=False)
    _words_truncated: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Parse query into words if needed."""
        if not self.is_phrase_search and self.query:
            self._words = [w.strip() for w in self.query.split() if w.strip()]
            if len(self._words) > self.max_words:
                self._words = self._words[: self.max_words]
                self._words_truncated = True

    @staticmethod
    def escape_like_pattern(value: str) -> str:
        """Escape special characters for LIKE pattern.

        Args:
            value: The value to escape

        Returns:
            Escaped value safe for use in LIKE clause
        """
        return value.replace("%", "\\%").replace("_", "\\_")

    @property
    def words_truncated(self) -> bool:
        """Return whether words were truncated to max limit."""
        return self._words_truncated

    def _build_base_select(self) -> str:
        """Build the base SELECT clause with all needed columns."""
        return """
            SELECT e.id, e.feed_id, e.guid, e.url, e.title, e.author,
                   e.content, e.summary, e.published_at, e.first_seen,
                   f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
        """

    def _build_phrase_query(self, limit: int) -> SearchQueryResult:
        """Build query for phrase search (exact sequence).

        Args:
            limit: Maximum number of results

        Returns:
            SearchQueryResult with SQL and params
        """
        escaped_query = self.escape_like_pattern(self.query)
        like_pattern = f"%{escaped_query}%"

        sql = f"""
            {self._build_base_select()}
            WHERE e.title LIKE ? ESCAPE '\\'
               OR e.content LIKE ? ESCAPE '\\'
            ORDER BY e.published_at DESC
            LIMIT ?
        """

        return SearchQueryResult(
            sql=sql,
            params=(like_pattern, like_pattern, limit),
            words_truncated=False,
        )

    def _build_single_word_query(self, limit: int) -> SearchQueryResult:
        """Build query for single-word search.

        Args:
            limit: Maximum number of results

        Returns:
            SearchQueryResult with SQL and params
        """
        escaped_query = self.escape_like_pattern(self.query)
        like_pattern = f"%{escaped_query}%"

        sql = f"""
            {self._build_base_select()}
            WHERE e.title LIKE ? ESCAPE '\\'
               OR e.content LIKE ? ESCAPE '\\'
            ORDER BY e.published_at DESC
            LIMIT ?
        """

        return SearchQueryResult(
            sql=sql,
            params=(like_pattern, like_pattern, limit),
            words_truncated=self._words_truncated,
        )

    def _build_multi_word_query(self, limit: int) -> SearchQueryResult:
        """Build query for multi-word search (all words must appear).

        All words must appear in either the title OR the content.

        Args:
            limit: Maximum number of results

        Returns:
            SearchQueryResult with SQL and params
        """
        # Build bind values for each word
        bind_values: list[str] = []
        for word in self._words:
            escaped_word = self.escape_like_pattern(word)
            bind_values.append(f"%{escaped_word}%")

        # Build WHERE conditions
        title_conditions = " AND ".join(["e.title LIKE ? ESCAPE '\\'" for _ in self._words])
        content_conditions = " AND ".join(["e.content LIKE ? ESCAPE '\\'" for _ in self._words])

        sql = f"""
            {self._build_base_select()}
            WHERE ({title_conditions})
               OR ({content_conditions})
            ORDER BY e.published_at DESC
            LIMIT ?
        """

        # Params: title patterns + content patterns + limit
        params = tuple(bind_values + bind_values + [limit])

        return SearchQueryResult(
            sql=sql,
            params=params,
            words_truncated=self._words_truncated,
        )

    def build(self, limit: int = 50) -> SearchQueryResult:
        """Build the SQL query based on search type.

        Args:
            limit: Maximum number of results to return

        Returns:
            SearchQueryResult with SQL, params, and metadata

        Raises:
            ValueError: If query is empty
        """
        if not self.query or not self.query.strip():
            raise ValueError("Search query cannot be empty")

        if self.is_phrase_search:
            return self._build_phrase_query(limit)

        # Word-based search
        if len(self._words) <= 1:
            return self._build_single_word_query(limit)

        return self._build_multi_word_query(limit)

    @classmethod
    def from_raw_query(
        cls, raw_query: str, max_words: int = DEFAULT_MAX_SEARCH_WORDS
    ) -> "SearchQueryBuilder":
        """Create a builder from a raw query string.

        Automatically detects phrase searches (quoted queries).

        Args:
            raw_query: The raw query string (may include quotes)
            max_words: Maximum number of words for multi-word search

        Returns:
            SearchQueryBuilder configured for the query type
        """
        query = raw_query.strip()

        # Detect phrase search (quoted)
        is_phrase_search = (query.startswith('"') and query.endswith('"')) or (
            query.startswith("'") and query.endswith("'")
        )

        # Strip quotes for actual search
        if is_phrase_search:
            query = query[1:-1].strip()

        return cls(query=query, is_phrase_search=is_phrase_search, max_words=max_words)


@dataclass
class FTS5SearchQueryBuilder:
    """Builder for FTS5 full-text search queries.

    Constructs SQL queries using FTS5 MATCH for fast tokenized search.
    All user input is quoted to prevent FTS5 operator injection.

    Drop-in replacement for SearchQueryBuilder — same constructor
    signature, same build() return type, same from_raw_query() factory.

    Attributes:
        query: The search query string
        is_phrase_search: Whether this is a phrase search (exact token sequence)
        max_words: Maximum number of words to search for
    """

    query: str
    is_phrase_search: bool = False
    max_words: int = DEFAULT_MAX_SEARCH_WORDS
    _words: list[str] = field(default_factory=list, init=False)
    _words_truncated: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Parse query into words if needed."""
        if not self.is_phrase_search and self.query:
            self._words = [w.strip() for w in self.query.split() if w.strip()]
            if len(self._words) > self.max_words:
                self._words = self._words[: self.max_words]
                self._words_truncated = True

    @staticmethod
    def escape_fts5_token(value: str) -> str:
        """Escape a token for safe use in FTS5 MATCH expression.

        Wraps in double quotes and escapes internal double quotes by
        doubling them. This treats the value as a literal string,
        preventing FTS5 operator injection (OR, AND, NOT, NEAR, *, etc.).

        Args:
            value: The value to escape

        Returns:
            Quoted string safe for use in FTS5 MATCH clause
        """
        # Strip null bytes — they cause FTS5 "unterminated string" errors
        value = value.replace("\x00", "")
        return '"' + value.replace('"', '""') + '"'

    @property
    def words_truncated(self) -> bool:
        """Return whether words were truncated to max limit."""
        return self._words_truncated

    def _build_base_select(self) -> str:
        """Build the base SELECT clause with FTS5 JOIN."""
        return """
            SELECT e.id, e.feed_id, e.guid, e.url, e.title, e.author,
                   e.content, e.summary, e.published_at, e.first_seen,
                   f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            JOIN entries_fts fts ON e.id = fts.rowid
        """

    def _build_match_expression(self) -> str:
        """Build the FTS5 MATCH expression from the query.

        Returns:
            Escaped MATCH expression string
        """
        if self.is_phrase_search:
            # Phrase search: wrap entire phrase in quotes for adjacent token match
            return self.escape_fts5_token(self.query)

        # Word-based search: quote each word separately (implicit AND)
        words = self._words if self._words else [self.query]
        return " ".join(self.escape_fts5_token(w) for w in words)

    def build(self, limit: int = 50) -> SearchQueryResult:
        """Build the FTS5 SQL query.

        Args:
            limit: Maximum number of results to return

        Returns:
            SearchQueryResult with SQL, params, and metadata

        Raises:
            ValueError: If query is empty
        """
        if not self.query or not self.query.strip():
            raise ValueError("Search query cannot be empty")

        match_expr = self._build_match_expression()

        sql = f"""
            {self._build_base_select()}
            WHERE entries_fts MATCH ?
            ORDER BY e.published_at DESC
            LIMIT ?
        """

        return SearchQueryResult(
            sql=sql,
            params=(match_expr, limit),
            words_truncated=self._words_truncated,
        )

    @classmethod
    def from_raw_query(
        cls, raw_query: str, max_words: int = DEFAULT_MAX_SEARCH_WORDS
    ) -> "FTS5SearchQueryBuilder":
        """Create a builder from a raw query string.

        Automatically detects phrase searches (quoted queries).

        Args:
            raw_query: The raw query string (may include quotes)
            max_words: Maximum number of words for multi-word search

        Returns:
            FTS5SearchQueryBuilder configured for the query type
        """
        query = raw_query.strip()

        # Detect phrase search (quoted)
        is_phrase_search = (query.startswith('"') and query.endswith('"')) or (
            query.startswith("'") and query.endswith("'")
        )

        # Strip quotes for actual search
        if is_phrase_search:
            query = query[1:-1].strip()

        return cls(query=query, is_phrase_search=is_phrase_search, max_words=max_words)
