# tests/unit/test_safe_wrappers.py
"""Unit tests for Safe wrapper classes that handle JS/Python boundary."""

import pytest

from src.wrappers import (
    SafeAI,
    SafeD1,
    SafeD1Statement,
    SafeEnv,
    SafeFeedInfo,
    SafeFormData,
    SafeHeaders,
    SafeQueue,
    SafeVectorize,
    _to_d1_value,
    admin_row_from_js,
    audit_row_from_js,
    audit_rows_from_d1,
    entry_bind_values,
    entry_row_from_js,
    entry_rows_from_d1,
    feed_bind_values,
    feed_row_from_js,
    feed_rows_from_d1,
)

# =============================================================================
# Mock Classes for Testing
# =============================================================================


class MockD1Statement:
    """Mock D1 prepared statement."""

    def __init__(self, results=None):
        self._results = results or []
        self._bound_args = None

    def bind(self, *args):
        self._bound_args = args
        return self

    async def first(self):
        return self._results[0] if self._results else None

    async def all(self):
        class Result:
            def __init__(self, results):
                self.results = results
                self.success = True

        return Result(self._results)

    async def run(self):
        return {"success": True}


class MockD1:
    """Mock D1 database."""

    def __init__(self, statement=None):
        self._statement = statement or MockD1Statement()

    def prepare(self, sql):
        return self._statement


class MockAI:
    """Mock Workers AI binding."""

    def __init__(self, result=None):
        self._result = result
        self._has_result = result is not None

    async def run(self, model, inputs):
        if not self._has_result:
            return None
        return self._result


class MockVectorize:
    """Mock Vectorize index."""

    def __init__(self, query_result=None):
        self._query_result = query_result or {"matches": []}

    async def query(self, vector, options):
        return self._query_result

    async def upsert(self, vectors):
        return {"count": len(vectors) if vectors else 0}

    async def delete_by_ids(self, ids):
        return {"count": len(ids) if ids else 0}


class MockQueue:
    """Mock Cloudflare Queue."""

    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)
        return {"success": True}


class MockEnv:
    """Mock Worker environment."""

    def __init__(self):
        self.DB = MockD1()
        self.AI = MockAI()
        self.SEARCH_INDEX = MockVectorize()
        self.FEED_QUEUE = MockQueue()
        self.DEAD_LETTER_QUEUE = MockQueue()
        # String env vars
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret"


# =============================================================================
# SafeD1Statement Tests
# =============================================================================


class TestSafeD1Statement:
    """Tests for SafeD1Statement wrapper."""

    def test_bind_returns_self_for_chaining(self):
        """bind() returns self for method chaining."""
        stmt = SafeD1Statement(MockD1Statement())
        result = stmt.bind("value1", "value2")
        assert result is stmt

    def test_bind_converts_values(self):
        """bind() converts values through _to_d1_value."""
        mock_stmt = MockD1Statement()
        stmt = SafeD1Statement(mock_stmt)
        stmt.bind("test", 42, None)
        # Values should be converted (None handling is platform-specific)
        assert mock_stmt._bound_args is not None

    @pytest.mark.asyncio
    async def test_first_returns_dict_or_none(self):
        """first() returns Python dict or None."""
        # With result
        stmt = SafeD1Statement(MockD1Statement([{"id": 1, "name": "test"}]))
        result = await stmt.first()
        assert result == {"id": 1, "name": "test"}

        # Without result
        stmt = SafeD1Statement(MockD1Statement([]))
        result = await stmt.first()
        assert result is None

    @pytest.mark.asyncio
    async def test_all_returns_d1_result_object(self):
        """all() returns object with results list and success bool."""
        stmt = SafeD1Statement(MockD1Statement([{"id": 1}, {"id": 2}]))
        result = await stmt.all()
        assert hasattr(result, "results")
        assert hasattr(result, "success")
        assert result.success is True
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_run_executes_statement(self):
        """run() executes the statement."""
        stmt = SafeD1Statement(MockD1Statement())
        result = await stmt.run()
        assert result == {"success": True}


# =============================================================================
# SafeD1 Tests
# =============================================================================


class TestSafeD1:
    """Tests for SafeD1 wrapper."""

    def test_prepare_returns_safe_statement(self):
        """prepare() returns SafeD1Statement."""
        db = SafeD1(MockD1())
        stmt = db.prepare("SELECT * FROM test")
        assert isinstance(stmt, SafeD1Statement)


# =============================================================================
# SafeAI Tests
# =============================================================================


class TestSafeAI:
    """Tests for SafeAI wrapper."""

    @pytest.mark.asyncio
    async def test_run_returns_python_dict(self):
        """run() returns Python dict result."""
        ai = SafeAI(MockAI({"data": [{"values": [0.1, 0.2]}]}))
        result = await ai.run("@cf/model", {"text": "test"})
        assert isinstance(result, dict)
        assert "data" in result

    @pytest.mark.asyncio
    async def test_run_handles_empty_result(self):
        """run() handles empty/None result."""
        ai = SafeAI(MockAI(None))
        result = await ai.run("@cf/model", {"text": "test"})
        assert result is None


# =============================================================================
# SafeVectorize Tests
# =============================================================================


class TestSafeVectorize:
    """Tests for SafeVectorize wrapper."""

    @pytest.mark.asyncio
    async def test_query_returns_python_dict(self):
        """query() returns Python dict with matches."""
        index = SafeVectorize(MockVectorize({"matches": [{"id": "1", "score": 0.9}]}))
        result = await index.query([0.1, 0.2], {"topK": 10})
        assert isinstance(result, dict)
        assert "matches" in result


# =============================================================================
# SafeQueue Tests
# =============================================================================


class TestSafeQueue:
    """Tests for SafeQueue wrapper."""

    @pytest.mark.asyncio
    async def test_send_sends_message(self):
        """send() sends message to queue."""
        mock_queue = MockQueue()
        queue = SafeQueue(mock_queue)
        await queue.send({"feed_id": 1, "url": "https://example.com"})
        assert len(mock_queue.messages) == 1
        assert mock_queue.messages[0]["feed_id"] == 1


# =============================================================================
# SafeEnv Tests
# =============================================================================


class TestSafeEnv:
    """Tests for SafeEnv wrapper."""

    def test_wraps_d1_binding(self):
        """D1 binding is wrapped with SafeD1."""
        env = SafeEnv(MockEnv())
        assert isinstance(env.DB, SafeD1)

    def test_wraps_ai_binding(self):
        """AI binding is wrapped with SafeAI."""
        env = SafeEnv(MockEnv())
        assert isinstance(env.AI, SafeAI)

    def test_wraps_vectorize_binding(self):
        """Vectorize binding is wrapped with SafeVectorize."""
        env = SafeEnv(MockEnv())
        assert isinstance(env.SEARCH_INDEX, SafeVectorize)

    def test_wraps_queue_bindings(self):
        """Queue bindings are wrapped with SafeQueue."""
        env = SafeEnv(MockEnv())
        assert isinstance(env.FEED_QUEUE, SafeQueue)
        assert isinstance(env.DEAD_LETTER_QUEUE, SafeQueue)

    def test_passes_through_string_vars(self):
        """String env vars are passed through."""
        env = SafeEnv(MockEnv())
        assert env.PLANET_NAME == "Test Planet"
        assert env.SESSION_SECRET == "test-secret"

    def test_getattr_fallback(self):
        """Unknown attributes fall back to underlying env."""
        mock_env = MockEnv()
        mock_env.CUSTOM_VAR = "custom_value"
        env = SafeEnv(mock_env)
        assert env.CUSTOM_VAR == "custom_value"


# =============================================================================
# D1 Value Conversion Tests
# =============================================================================


class TestToD1Value:
    """Tests for _to_d1_value conversion function."""

    def test_converts_primitives(self):
        """Primitives pass through."""
        assert _to_d1_value(42) == 42
        assert _to_d1_value("text") == "text"
        assert _to_d1_value(3.14) == 3.14
        assert _to_d1_value(True) is True

    def test_handles_none(self):
        """None is converted appropriately."""
        result = _to_d1_value(None)
        # In Python-only tests, None stays None
        # In Pyodide, it would convert to JS null
        assert result is None

    def test_converts_nested_dict(self):
        """Nested dicts are converted."""
        value = {"outer": {"inner": "value"}}
        result = _to_d1_value(value)
        assert result == {"outer": {"inner": "value"}}


# =============================================================================
# Row Factory Tests - Feed
# =============================================================================


class TestFeedRowFromJs:
    """Tests for feed_row_from_js conversion function."""

    def test_converts_complete_row(self):
        """Converts a complete feed row with all fields."""
        row = {
            "id": 42,
            "url": "https://example.com/feed.xml",
            "title": "Example Feed",
            "site_url": "https://example.com",
            "is_active": 1,
            "consecutive_failures": 0,
            "etag": '"abc123"',
            "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT",
            "last_success_at": "2025-01-17T12:00:00Z",
            "last_error_at": None,
            "last_error_message": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-17T12:00:00Z",
            "author_name": "John Doe",
            "author_email": "john@example.com",
        }
        result = feed_row_from_js(row)
        assert result["id"] == 42
        assert result["url"] == "https://example.com/feed.xml"
        assert result["title"] == "Example Feed"
        assert result["site_url"] == "https://example.com"
        assert result["is_active"] == 1
        assert result["consecutive_failures"] == 0
        assert result["etag"] == '"abc123"'
        assert result["author_name"] == "John Doe"
        assert result["author_email"] == "john@example.com"

    def test_returns_empty_dict_for_none(self):
        """Returns empty dict for None input."""
        assert feed_row_from_js(None) == {}

    def test_returns_empty_dict_for_empty_row(self):
        """Returns empty dict for empty input."""
        assert feed_row_from_js({}) == {}

    def test_handles_missing_optional_fields(self):
        """Handles rows with missing optional fields."""
        row = {"id": 1, "url": "https://example.com/feed.xml"}
        result = feed_row_from_js(row)
        assert result["id"] == 1
        assert result["url"] == "https://example.com/feed.xml"
        assert result["title"] is None
        assert result["author_name"] is None

    def test_converts_id_to_int(self):
        """Converts id to int even if stored as string."""
        row = {"id": "123", "url": "https://example.com/feed.xml"}
        result = feed_row_from_js(row)
        assert result["id"] == 123
        assert isinstance(result["id"], int)

    def test_handles_none_values_in_row(self):
        """Handles None values within the row dict."""
        row = {
            "id": 1,
            "url": "https://example.com/feed.xml",
            "title": None,
            "etag": None,
        }
        result = feed_row_from_js(row)
        assert result["title"] is None
        assert result["etag"] is None


class TestFeedRowsFromD1:
    """Tests for feed_rows_from_d1 conversion function."""

    def test_converts_list_of_rows(self):
        """Converts a list of feed rows."""
        results = [
            {"id": 1, "url": "https://a.com/feed.xml", "title": "Feed A"},
            {"id": 2, "url": "https://b.com/feed.xml", "title": "Feed B"},
        ]
        rows = feed_rows_from_d1(results)
        assert len(rows) == 2
        assert rows[0]["id"] == 1
        assert rows[0]["title"] == "Feed A"
        assert rows[1]["id"] == 2
        assert rows[1]["title"] == "Feed B"

    def test_returns_empty_list_for_none(self):
        """Returns empty list for None input."""
        assert feed_rows_from_d1(None) == []

    def test_returns_empty_list_for_empty_list(self):
        """Returns empty list for empty input."""
        assert feed_rows_from_d1([]) == []


# =============================================================================
# Row Factory Tests - Entry
# =============================================================================


class TestEntryRowFromJs:
    """Tests for entry_row_from_js conversion function."""

    def test_converts_complete_row(self):
        """Converts a complete entry row with all fields."""
        row = {
            "id": 100,
            "feed_id": 42,
            "guid": "unique-guid-123",
            "url": "https://example.com/post/1",
            "title": "Example Post",
            "author": "Jane Doe",
            "content": "<p>Post content here</p>",
            "summary": "A brief summary",
            "published_at": "2025-01-17T10:00:00Z",
            "created_at": "2025-01-17T10:05:00Z",
            "first_seen": "2025-01-17T10:05:00Z",
            "feed_title": "Example Feed",
            "feed_site_url": "https://example.com",
        }
        result = entry_row_from_js(row)
        assert result["id"] == 100
        assert result["feed_id"] == 42
        assert result["guid"] == "unique-guid-123"
        assert result["url"] == "https://example.com/post/1"
        assert result["title"] == "Example Post"
        assert result["author"] == "Jane Doe"
        assert result["content"] == "<p>Post content here</p>"
        assert result["summary"] == "A brief summary"
        assert result["feed_title"] == "Example Feed"

    def test_returns_empty_dict_for_none(self):
        """Returns empty dict for None input."""
        assert entry_row_from_js(None) == {}

    def test_handles_missing_optional_fields(self):
        """Handles rows with missing optional fields."""
        row = {"id": 1, "feed_id": 1, "guid": "guid", "url": "https://x.com", "title": "Title"}
        result = entry_row_from_js(row)
        assert result["author"] is None
        assert result["summary"] is None
        assert result["feed_title"] is None


class TestEntryRowsFromD1:
    """Tests for entry_rows_from_d1 conversion function."""

    def test_converts_list_of_rows(self):
        """Converts a list of entry rows."""
        results = [
            {"id": 1, "feed_id": 1, "guid": "a", "url": "https://a.com", "title": "A"},
            {"id": 2, "feed_id": 1, "guid": "b", "url": "https://b.com", "title": "B"},
        ]
        rows = entry_rows_from_d1(results)
        assert len(rows) == 2
        assert rows[0]["guid"] == "a"
        assert rows[1]["guid"] == "b"

    def test_returns_empty_list_for_none(self):
        """Returns empty list for None input."""
        assert entry_rows_from_d1(None) == []


# =============================================================================
# Row Factory Tests - Admin
# =============================================================================


class TestAdminRowFromJs:
    """Tests for admin_row_from_js conversion function."""

    def test_converts_complete_row(self):
        """Converts a complete admin row."""
        row = {
            "id": 1,
            "github_username": "testuser",
            "github_id": 12345,
            "display_name": "Test User",
            "is_active": 1,
            "last_login_at": "2025-01-17T12:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
        }
        result = admin_row_from_js(row)
        assert result["id"] == 1
        assert result["github_username"] == "testuser"
        assert result["github_id"] == 12345
        assert result["display_name"] == "Test User"
        assert result["is_active"] == 1

    def test_returns_none_for_none_input(self):
        """Returns None for None input (unlike other row factories)."""
        assert admin_row_from_js(None) is None

    def test_returns_none_for_empty_row(self):
        """Returns None for empty row."""
        assert admin_row_from_js({}) is None


# =============================================================================
# Row Factory Tests - Audit
# =============================================================================


class TestAuditRowFromJs:
    """Tests for audit_row_from_js conversion function."""

    def test_converts_complete_row(self):
        """Converts a complete audit log row."""
        row = {
            "id": 500,
            "admin_id": 1,
            "action": "add_feed",
            "target_type": "feed",
            "target_id": 42,
            "details": '{"url": "https://example.com"}',
            "created_at": "2025-01-17T12:00:00Z",
            "admin_username": "testuser",
        }
        result = audit_row_from_js(row)
        assert result["id"] == 500
        assert result["admin_id"] == 1
        assert result["action"] == "add_feed"
        assert result["target_type"] == "feed"
        assert result["target_id"] == 42
        assert result["admin_username"] == "testuser"

    def test_returns_empty_dict_for_none(self):
        """Returns empty dict for None input."""
        assert audit_row_from_js(None) == {}


class TestAuditRowsFromD1:
    """Tests for audit_rows_from_d1 conversion function."""

    def test_converts_list_of_rows(self):
        """Converts a list of audit rows."""
        results = [
            {"id": 1, "admin_id": 1, "action": "add_feed"},
            {"id": 2, "admin_id": 1, "action": "remove_feed"},
        ]
        rows = audit_rows_from_d1(results)
        assert len(rows) == 2
        assert rows[0]["action"] == "add_feed"
        assert rows[1]["action"] == "remove_feed"

    def test_returns_empty_list_for_none(self):
        """Returns empty list for None input."""
        assert audit_rows_from_d1(None) == []


# =============================================================================
# SafeHeaders Tests
# =============================================================================


class MockRequest:
    """Mock request object for testing SafeHeaders."""

    def __init__(self, headers: dict):
        self.headers = headers


class TestSafeHeaders:
    """Tests for SafeHeaders helper class."""

    def test_gets_user_agent(self):
        """Gets User-Agent header."""
        request = MockRequest({"user-agent": "Mozilla/5.0"})
        headers = SafeHeaders(request)
        assert headers.user_agent == "Mozilla/5.0"

    def test_gets_referer(self):
        """Gets Referer header."""
        request = MockRequest({"referer": "https://example.com"})
        headers = SafeHeaders(request)
        assert headers.referer == "https://example.com"

    def test_gets_cookie(self):
        """Gets Cookie header."""
        request = MockRequest({"Cookie": "session=abc123"})
        headers = SafeHeaders(request)
        assert headers.cookie == "session=abc123"

    def test_gets_content_type(self):
        """Gets Content-Type header."""
        request = MockRequest({"content-type": "application/json"})
        headers = SafeHeaders(request)
        assert headers.content_type == "application/json"

    def test_gets_accept(self):
        """Gets Accept header."""
        request = MockRequest({"accept": "text/html"})
        headers = SafeHeaders(request)
        assert headers.accept == "text/html"

    def test_get_arbitrary_header(self):
        """Gets arbitrary header by name."""
        request = MockRequest({"X-Custom-Header": "custom-value"})
        headers = SafeHeaders(request)
        assert headers.get("X-Custom-Header") == "custom-value"

    def test_returns_empty_string_for_missing_header(self):
        """Returns empty string for missing headers."""
        request = MockRequest({})
        headers = SafeHeaders(request)
        assert headers.user_agent == ""
        assert headers.cookie == ""
        assert headers.get("X-Missing") == ""

    def test_get_with_default(self):
        """Get method uses default for missing headers."""
        request = MockRequest({})
        headers = SafeHeaders(request)
        assert headers.get("X-Missing", "fallback") == "fallback"


# =============================================================================
# SafeFormData Tests
# =============================================================================


class MockFormDataDict:
    """Mock form data that behaves like a dict."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key):
        return self._data.get(key)


class TestSafeFormData:
    """Tests for SafeFormData helper class."""

    def test_get_returns_value(self):
        """get() returns form value."""
        form = SafeFormData(MockFormDataDict({"name": "test"}))
        assert form.get("name") == "test"

    def test_get_returns_none_for_missing(self):
        """get() returns None for missing key."""
        form = SafeFormData(MockFormDataDict({}))
        assert form.get("missing") is None

    def test_get_str_returns_value(self):
        """get_str() returns form value."""
        form = SafeFormData(MockFormDataDict({"name": "test"}))
        assert form.get_str("name") == "test"

    def test_get_str_returns_default_for_missing(self):
        """get_str() returns default for missing key."""
        form = SafeFormData(MockFormDataDict({}))
        assert form.get_str("missing", "default") == "default"

    def test_get_str_returns_default_for_empty(self):
        """get_str() returns default for empty value."""
        form = SafeFormData(MockFormDataDict({"empty": ""}))
        assert form.get_str("empty", "default") == "default"

    def test_get_int_returns_integer(self):
        """get_int() returns integer value."""
        form = SafeFormData(MockFormDataDict({"count": "42"}))
        assert form.get_int("count") == 42

    def test_get_int_returns_default_for_missing(self):
        """get_int() returns default for missing key."""
        form = SafeFormData(MockFormDataDict({}))
        assert form.get_int("missing", 10) == 10

    def test_get_int_returns_default_for_invalid(self):
        """get_int() returns default for non-numeric value."""
        form = SafeFormData(MockFormDataDict({"bad": "not-a-number"}))
        assert form.get_int("bad", 0) == 0


# =============================================================================
# SafeFeedInfo Tests
# =============================================================================


class TestSafeFeedInfo:
    """Tests for SafeFeedInfo helper class."""

    def test_gets_title(self):
        """Gets feed title."""
        info = SafeFeedInfo({"title": "My Blog"})
        assert info.title == "My Blog"

    def test_gets_link(self):
        """Gets feed link."""
        info = SafeFeedInfo({"link": "https://example.com"})
        assert info.link == "https://example.com"

    def test_gets_author_from_author_detail(self):
        """Gets author from author_detail.name."""
        info = SafeFeedInfo(
            {
                "author_detail": {"name": "John Doe", "email": "john@example.com"},
                "author": "Fallback Author",
            }
        )
        assert info.author == "John Doe"

    def test_gets_author_fallback(self):
        """Falls back to author field if author_detail missing."""
        info = SafeFeedInfo({"author": "Simple Author"})
        assert info.author == "Simple Author"

    def test_gets_author_email(self):
        """Gets author email from author_detail."""
        info = SafeFeedInfo({"author_detail": {"name": "John", "email": "john@example.com"}})
        assert info.author_email == "john@example.com"

    def test_returns_none_for_missing_author_email(self):
        """Returns None when author_detail has no email."""
        info = SafeFeedInfo({"author_detail": {"name": "John"}})
        assert info.author_email is None

    def test_returns_none_for_no_author_detail(self):
        """Returns None when no author_detail exists."""
        info = SafeFeedInfo({})
        assert info.author_email is None

    def test_handles_none_input(self):
        """Handles None input gracefully."""
        info = SafeFeedInfo(None)
        assert info.title is None
        assert info.link is None
        assert info.author is None

    def test_get_arbitrary_field(self):
        """get() retrieves arbitrary fields."""
        info = SafeFeedInfo({"subtitle": "A blog about things"})
        assert info.get("subtitle") == "A blog about things"

    def test_get_missing_field_returns_none(self):
        """get() returns None for missing fields."""
        info = SafeFeedInfo({})
        assert info.get("nonexistent") is None


# =============================================================================
# Bind Helper Tests
# =============================================================================


class TestEntryBindValues:
    """Tests for entry_bind_values helper function."""

    def test_returns_tuple_of_correct_length(self):
        """Returns tuple with 8 elements."""
        result = entry_bind_values(
            feed_id=1,
            guid="guid-123",
            url="https://example.com/post",
            title="Post Title",
            author="Author Name",
            content="<p>Content</p>",
            summary="Summary text",
            published_at="2025-01-17T12:00:00Z",
        )
        assert isinstance(result, tuple)
        assert len(result) == 8

    def test_preserves_feed_id_as_int(self):
        """feed_id is preserved as integer."""
        result = entry_bind_values(42, "g", "u", "t", "a", "c", "s", "p")
        assert result[0] == 42
        assert isinstance(result[0], int)

    def test_converts_strings(self):
        """String values are converted through _safe_str."""
        result = entry_bind_values(1, "guid", "url", "title", "author", "content", "summary", "pub")
        assert result[1] == "guid"
        assert result[2] == "url"
        assert result[3] == "title"
        assert result[4] == "author"
        assert result[5] == "content"
        assert result[6] == "summary"
        assert result[7] == "pub"

    def test_handles_none_values(self):
        """None values are passed through."""
        result = entry_bind_values(1, None, None, None, None, None, None, None)
        assert result[1] is None
        assert result[2] is None

    def test_converts_empty_string_to_none(self):
        """Empty strings are converted to None by _safe_str."""
        result = entry_bind_values(1, "", "", "", "", "", "", "")
        assert result[1] is None  # _safe_str returns None for empty string


class TestFeedBindValues:
    """Tests for feed_bind_values helper function."""

    def test_returns_tuple_of_correct_length(self):
        """Returns tuple with 7 elements."""
        result = feed_bind_values(
            title="Feed Title",
            site_url="https://example.com",
            author_name="Author",
            author_email="author@example.com",
            etag='"abc123"',
            last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
            feed_id=42,
        )
        assert isinstance(result, tuple)
        assert len(result) == 7

    def test_feed_id_is_last_element(self):
        """feed_id is the last element (for WHERE clause)."""
        result = feed_bind_values("t", "s", "a", "e", "et", "lm", 99)
        assert result[-1] == 99
        assert isinstance(result[-1], int)

    def test_converts_all_string_fields(self):
        """All string fields are converted through _safe_str."""
        result = feed_bind_values(
            "Title", "https://site.com", "Author", "email@x.com", "etag", "lastmod", 1
        )
        assert result[0] == "Title"
        assert result[1] == "https://site.com"
        assert result[2] == "Author"
        assert result[3] == "email@x.com"
        assert result[4] == "etag"
        assert result[5] == "lastmod"

    def test_handles_none_values(self):
        """None values are passed through."""
        result = feed_bind_values(None, None, None, None, None, None, 1)
        assert result[0] is None
        assert result[1] is None


# =============================================================================
# JsNullMock Tests
# =============================================================================


class TestJsNullMock:
    """Tests for JsNullMock - simulates Pyodide's JsNull type."""

    def test_type_name_is_jsnull(self):
        """type(x).__name__ must be 'JsNull' to match Pyodide behavior."""
        from tests.mocks.jsproxy import JsNullMock

        js_null = JsNullMock()
        assert type(js_null).__name__ == "JsNull"

    def test_is_falsy(self):
        """JsNull is falsy, like JavaScript null."""
        from tests.mocks.jsproxy import JsNullMock

        assert not JsNullMock()
        assert bool(JsNullMock()) is False

    def test_is_not_none(self):
        """JsNull is NOT Python None - this is the key gotcha."""
        from tests.mocks.jsproxy import JsNullMock

        js_null = JsNullMock()
        assert js_null is not None
        # isinstance check that would miss it in production
        assert not isinstance(js_null, type(None))

    def test_wrap_as_jsproxy_converts_none_to_jsnull(self):
        """wrap_as_jsproxy(None) returns JsNullMock, simulating the FFI boundary."""
        from tests.mocks.jsproxy import JsNullMock, wrap_as_jsproxy

        result = wrap_as_jsproxy(None)
        assert isinstance(result, JsNullMock)
        assert type(result).__name__ == "JsNull"

    def test_feed_row_handles_jsnull_field(self, monkeypatch):
        """Row factories handle JsNull values in fields gracefully."""
        import src.wrappers as wrappers_mod
        from tests.mocks.jsproxy import JsNullMock

        monkeypatch.setattr(wrappers_mod, "HAS_PYODIDE", True)
        row = {"id": 1, "url": "https://example.com/feed.xml", "title": JsNullMock()}
        result = feed_row_from_js(row)
        assert result["title"] is None


# =============================================================================
# Branch Coverage Tests for wrappers.py
# =============================================================================


class TestToPyListFallbackBranches:
    """Tests for _to_py_list fallback paths (lines 217-220)."""

    def test_to_py_list_fallback_iteration_with_items(self):
        """_to_py_list falls back to iteration when input is not list and has no to_py()."""
        from src.wrappers import _to_py_list

        # Create an iterable that is NOT a list and has no to_py()
        # FakeRow must be a proper mapping (keys() + __getitem__) for dict() to work
        class FakeRow:
            def __init__(self):
                self._data = {"id": 1, "name": "test"}

            def items(self):
                return self._data.items()

            def keys(self):
                return self._data.keys()

            def __getitem__(self, key):
                return self._data[key]

        class FakeArray:
            def __iter__(self):
                return iter([FakeRow()])

        result = _to_py_list(FakeArray())
        assert len(result) == 1
        assert result[0] == {"id": 1, "name": "test"}

    def test_to_py_list_exception_falls_back_to_list(self):
        """_to_py_list returns list(js_array) when iteration raises in comprehension."""
        from src.wrappers import _to_py_list

        # Create an iterable where the comprehension body fails
        # (no .items() and no .to_py()), but list() works
        class SimpleItem:
            pass

        class FakeArray:
            def __init__(self):
                self._items = ["a", "b", "c"]

            def __iter__(self):
                return iter(self._items)

        result = _to_py_list(FakeArray())
        # The comprehension will fail because strings have no .items() or .to_py()
        # Falls back to list(js_array)
        assert result == ["a", "b", "c"]


class TestExtractFormValueException:
    """Tests for _extract_form_value exception branch (line 195-196)."""

    def test_extract_form_value_exception_returns_none(self):
        """_extract_form_value returns None when form.get() raises."""
        from src.wrappers import _extract_form_value

        class BrokenForm:
            def get(self, key):
                raise RuntimeError("broken form data")

        result = _extract_form_value(BrokenForm(), "any_key")
        assert result is None


class TestToPySafeEdgeCases:
    """Tests for _to_py_safe edge case branches."""

    def test_numeric_string_object_converted_to_int(self):
        """Object whose str() is all digits gets converted to int (line 153-154)."""
        from src.wrappers import _to_py_safe

        class NumericThing:
            def __str__(self):
                return "42"

        result = _to_py_safe(NumericThing())
        assert result == 42
        assert isinstance(result, int)

    def test_non_numeric_string_object_returned_as_str(self):
        """Object whose str() is not all digits is returned as string (line 155)."""
        from src.wrappers import _to_py_safe

        class StringThing:
            def __str__(self):
                return "hello"

        result = _to_py_safe(StringThing())
        assert result == "hello"

    def test_string_123_passes_through_as_string(self):
        """Python string '123' passes through as string, not converted to int."""
        from src.wrappers import _to_py_safe

        # Strings hit the isinstance(value, str) branch early
        result = _to_py_safe("123")
        assert result == "123"
        assert isinstance(result, str)

    def test_js_undefined_converts_to_none(self, monkeypatch):
        """JsUndefined-like object converts to None."""
        import src.wrappers as wrappers_mod
        from src.wrappers import _to_py_safe

        monkeypatch.setattr(wrappers_mod, "HAS_PYODIDE", True)

        class FakeJsUndefined:
            pass

        FakeJsUndefined.__name__ = "JsUndefined"
        FakeJsUndefined.__qualname__ = "JsUndefined"

        result = _to_py_safe(FakeJsUndefined())
        assert result is None

    def test_max_depth_returns_value_unchanged(self):
        """Exceeding max conversion depth returns value as-is."""
        from src.wrappers import _MAX_CONVERSION_DEPTH, _to_py_safe

        result = _to_py_safe({"key": "val"}, _depth=_MAX_CONVERSION_DEPTH)
        assert result == {"key": "val"}
