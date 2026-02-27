# tests/mocks/d1.py
"""
Mock D1 database that simulates Cloudflare Workers D1 behavior.

In production, D1 returns JsProxy-wrapped results. This mock
replicates that behavior so tests catch JsProxy-related bugs.
"""

from typing import Any

from tests.conftest import TEST_SESSION_SECRET

from .jsproxy import JsProxyArray, JsProxyDict


class MockD1Result:
    """
    Mock D1 query result.

    In production:
    - result.results is a JsProxy array of JsProxy dicts
    - result.success is a boolean
    - result.meta contains query metadata
    """

    def __init__(
        self,
        results: list | None = None,
        success: bool = True,
        simulate_jsproxy: bool = True,
    ):
        self.success = success
        self.meta = {"changed": 0, "changes": 0, "duration": 0}

        if results is None:
            results = []

        # Simulate JsProxy wrapping (production behavior)
        if simulate_jsproxy:
            self._results = JsProxyArray(results)
        else:
            self._results = results

    @property
    def results(self):
        return self._results


class MockD1PreparedStatement:
    """Mock D1 prepared statement."""

    def __init__(self, db: "MockD1Database", sql: str):
        self._db = db
        self._sql = sql
        self._bindings: list = []

    def bind(self, *args) -> "MockD1PreparedStatement":
        """Bind parameters to the statement."""
        self._bindings = list(args)
        return self

    async def all(self) -> MockD1Result:
        """Execute and return all results."""
        handler = self._db._find_handler(self._sql, "all")
        if handler:
            results = await handler(self._sql, self._bindings)
            return MockD1Result(results=results, simulate_jsproxy=self._db._simulate_jsproxy)
        return MockD1Result(results=[], simulate_jsproxy=self._db._simulate_jsproxy)

    async def first(self) -> Any | None:
        """Execute and return first result."""
        handler = self._db._find_handler(self._sql, "first")
        if handler:
            result = await handler(self._sql, self._bindings)
            if result is None:
                return None
            # Wrap single result as JsProxy
            if self._db._simulate_jsproxy:
                return JsProxyDict(result)
            return result
        return None

    async def run(self) -> MockD1Result:
        """Execute without returning results (INSERT, UPDATE, DELETE)."""
        handler = self._db._find_handler(self._sql, "run")
        if handler:
            await handler(self._sql, self._bindings)
        return MockD1Result(results=[], simulate_jsproxy=self._db._simulate_jsproxy)


class MockD1Database:
    """
    Mock D1 database with JsProxy simulation.

    Usage:
        db = MockD1Database()

        # Register handlers for specific queries
        @db.on_query("SELECT * FROM feeds", method="all")
        async def handle_feeds_query(sql, bindings):
            return [{"id": 1, "url": "https://example.com"}]

        # Or use with predefined data
        db.set_table_data("feeds", [
            {"id": 1, "url": "https://example.com/feed.xml"},
            {"id": 2, "url": "https://other.com/rss.xml"},
        ])
    """

    def __init__(self, simulate_jsproxy: bool = True):
        self._handlers: dict = {}
        self._tables: dict = {}
        self._simulate_jsproxy = simulate_jsproxy

    def prepare(self, sql: str) -> MockD1PreparedStatement:
        """Prepare a SQL statement."""
        return MockD1PreparedStatement(self, sql)

    def on_query(self, pattern: str, method: str = "all"):
        """Decorator to register a query handler."""

        def decorator(func):
            key = (pattern.lower().strip(), method)
            self._handlers[key] = func
            return func

        return decorator

    def _find_handler(self, sql: str, method: str):
        """Find a handler for the given SQL and method."""
        sql_lower = sql.lower().strip()
        # Try exact match first
        key = (sql_lower, method)
        if key in self._handlers:
            return self._handlers[key]

        # Try pattern matching (contains)
        for (pattern, handler_method), handler in self._handlers.items():
            if handler_method == method and pattern in sql_lower:
                return handler

        return None

    def set_table_data(self, table: str, rows: list[dict]):
        """Set data for a table (for simple mocking)."""
        self._tables[table] = rows

    def get_table_data(self, table: str) -> list[dict]:
        """Get data for a table."""
        return self._tables.get(table, [])


# =============================================================================
# Fixture factory
# =============================================================================


def create_mock_env(
    feeds: list[dict] | None = None,
    entries: list[dict] | None = None,
    admins: list[dict] | None = None,
    simulate_jsproxy: bool = True,
) -> Any:
    """
    Create a mock environment with D1 database.

    This is the recommended way to create test fixtures that properly
    simulate production JsProxy behavior.
    """
    from unittest.mock import MagicMock

    env = MagicMock()
    db = MockD1Database(simulate_jsproxy=simulate_jsproxy)

    if feeds:
        db.set_table_data("feeds", feeds)

    if entries:
        db.set_table_data("entries", entries)

    if admins:
        db.set_table_data("admins", admins)

    env.DB = db
    env.PLANET_NAME = "Planet CF"
    env.PLANET_DESCRIPTION = "Test Planet"
    env.PLANET_URL = "https://planetcf.com"
    env.SESSION_SECRET = TEST_SESSION_SECRET
    env.GITHUB_CLIENT_ID = "test-client-id"
    env.GITHUB_CLIENT_SECRET = "test-client-secret"

    return env
