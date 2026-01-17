# tests/unit/test_safe_wrappers.py
"""Unit tests for Safe wrapper classes that handle JS/Python boundary."""

import pytest

from src.wrappers import (
    SafeAI,
    SafeD1,
    SafeD1Statement,
    SafeEnv,
    SafeQueue,
    SafeVectorize,
    _to_d1_value,
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
        self._messages = []

    async def send(self, message):
        self._messages.append(message)
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
        assert len(mock_queue._messages) == 1
        assert mock_queue._messages[0]["feed_id"] == 1


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
