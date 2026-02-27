# tests/conftest.py
"""Shared fixtures for Planet CF tests."""

import base64
import hashlib
import hmac
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

# =============================================================================
# Shared Test Constants
# =============================================================================

TEST_SESSION_SECRET = "test-secret-key-for-testing-only-32chars"  # pragma: allowlist secret

# Add src directory to path so imports work like in Workers environment
_src_path = str(Path(__file__).parent.parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# =============================================================================
# Mock Workers Module (must be set up before importing src.main)
# =============================================================================


class MockResponse:
    """Mock Cloudflare Workers Response object."""

    def __init__(
        self,
        body: str = "",
        status: int = 200,
        headers: dict | None = None,
    ):
        self.body = body
        self.status = status
        self._headers = headers or {}

    @property
    def headers(self) -> dict:
        return self._headers


class MockWorkerEntrypoint:
    """Mock Cloudflare Workers WorkerEntrypoint base class."""

    env: Any = None
    ctx: Any = None

    def __init__(self):
        pass


class MockRequest:
    """Mock Cloudflare Workers Request object.

    Supports two modes:
    - Simple mode: headers as a plain dict (for tests using direct header access)
    - Full mode: cookies/form_data/json_data with MagicMock headers (for admin/auth tests)

    Full mode is activated automatically when cookies, form_data, or json_data are provided.
    """

    def __init__(
        self,
        url: str = "https://example.com/",
        method: str = "GET",
        headers: dict | None = None,
        body: str | bytes | None = None,
        cookies: str = "",
        form_data: dict | None = None,
        json_data: dict | None = None,
    ):
        from unittest.mock import MagicMock

        self.url = url
        self.method = method
        self._body = body
        self._cookies = cookies
        self._form_data = form_data or {}
        self._json_data = json_data or {}

        # Use MagicMock headers with side_effect for cookie/header lookups
        # (compatible with SafeHeaders which calls headers.get())
        self.headers = MagicMock()
        # Merge explicit headers with cookie header
        self._raw_headers = headers or {}
        self.headers.get = MagicMock(side_effect=self._get_header)

    def _get_header(self, name, default=None):
        # Check explicit headers first (case-insensitive)
        for key, val in self._raw_headers.items():
            if key.lower() == name.lower():
                return val
        # Then check cookie
        if name.lower() == "cookie":
            return self._cookies
        return default

    async def text(self) -> str:
        if isinstance(self._body, bytes):
            return self._body.decode("utf-8")
        return self._body or ""

    async def json(self) -> Any:
        import json

        return self._json_data or json.loads(await self.text())

    async def form_data(self):
        """Workers Python SDK uses snake_case form_data(), not formData()."""

        class _FormData:
            def __init__(self, data):
                self._data = data

            def get(self, key, default=None):
                return self._data.get(key, default)

        return _FormData(self._form_data)


# Create mock workers module
_mock_workers = ModuleType("workers")
_mock_workers.Request = MockRequest
_mock_workers.Response = MockResponse
_mock_workers.WorkerEntrypoint = MockWorkerEntrypoint

# Install the mock before any imports of src.main
sys.modules["workers"] = _mock_workers


# =============================================================================
# Mock Cloudflare Bindings
# =============================================================================


@dataclass
class MockD1Result:
    """Mock D1 query result."""

    results: list[dict]
    success: bool = True


class MockD1Statement:
    """Mock D1 prepared statement."""

    def __init__(self, results: list[dict], sql: str = ""):
        self._results = results
        self._sql = sql
        self._bound_args = []

    def bind(self, *args) -> "MockD1Statement":
        self._bound_args = args
        return self

    def _filter_results(self) -> list[dict]:
        """Apply basic filtering based on SQL WHERE clause.

        Note: This only filters on is_active when querying tables that actually
        have that field (feeds, admins). Entry queries that JOIN with feeds
        should NOT be filtered here - entries don't have is_active.
        """
        import re

        results = self._results
        sql_lower = self._sql.lower()

        # Only filter on is_active for tables that have it (feeds, admins)
        # Skip filtering for entry queries (they JOIN with feeds but entries
        # themselves don't have is_active)
        is_entry_query = "from entries" in sql_lower
        if not is_entry_query and "where" in sql_lower and "is_active" in sql_lower:
            match = re.search(r"is_active\s*=\s*(\d+)", sql_lower)
            if match:
                is_active_val = int(match.group(1))
                results = [r for r in results if r.get("is_active") == is_active_val]

        return results

    async def all(self) -> MockD1Result:
        return MockD1Result(results=self._filter_results())

    async def first(self) -> dict | None:
        filtered = self._filter_results()
        return filtered[0] if filtered else None

    async def run(self) -> MockD1Result:
        return MockD1Result(results=[])


class MockD1:
    """Mock D1 database.

    Args:
        data: Pre-loaded table data for query results.
        schema: Optional dict mapping table names to sets of column names.
            When provided, INSERT/UPDATE SQL is validated against the schema
            and errors are raised for unknown columns (strict mode).
    """

    def __init__(
        self,
        data: dict[str, list[dict]] | None = None,
        schema: dict[str, set[str]] | None = None,
    ):
        self._data = data or {}
        self._schema = schema

    def prepare(self, sql: str) -> MockD1Statement:
        """
        Parse SQL to determine which table to return data for.

        Priority order:
        1. DELETE FROM table_name
        2. INSERT INTO table_name
        3. UPDATE table_name
        4. FROM table_name (the primary table in SELECT)
        5. Simple table name match as fallback

        When schema is provided (strict mode), validates that INSERT/UPDATE
        columns exist in the schema.
        """
        import re

        sql_lower = sql.lower()

        # Strict mode: validate column names in INSERT/UPDATE
        if self._schema:
            self._validate_sql_columns(sql)

        # Try to find the primary table from SQL patterns
        patterns = [
            r"delete\s+from\s+(\w+)",
            r"insert\s+into\s+(\w+)",
            r"update\s+(\w+)",
            r"from\s+(\w+)",  # Primary table in SELECT
        ]

        for pattern in patterns:
            match = re.search(pattern, sql_lower)
            if match:
                table_name = match.group(1)
                if table_name in self._data:
                    return MockD1Statement(self._data[table_name], sql)

        # Fallback: simple table name match
        for table, rows in self._data.items():
            if table in sql_lower:
                return MockD1Statement(rows, sql)

        return MockD1Statement([], sql)

    def _validate_sql_columns(self, sql: str) -> None:
        """Validate that SQL column references exist in the schema."""
        import re

        sql_lower = sql.lower()

        # Skip PRAGMA and CREATE TABLE statements
        if sql_lower.strip().startswith(("pragma", "create table")):
            return

        # Validate INSERT INTO table (col1, col2, ...) columns
        insert_match = re.search(r"insert\s+into\s+(\w+)\s*\(([^)]+)\)", sql_lower)
        if insert_match:
            table = insert_match.group(1)
            if table in self._schema:
                cols = [c.strip() for c in insert_match.group(2).split(",")]
                for col in cols:
                    if col and col not in self._schema[table]:
                        raise ValueError(
                            f"MockD1 strict mode: INSERT INTO {table} "
                            f"references unknown column '{col}'. "
                            f"Schema columns: {sorted(self._schema[table])}"
                        )

        # Validate UPDATE table SET col = ... columns
        update_match = re.search(r"update\s+(\w+)\s+set\s+(.*?)(?:where|$)", sql_lower, re.DOTALL)
        if update_match:
            table = update_match.group(1)
            if table in self._schema:
                set_clause = update_match.group(2)
                for assignment in set_clause.split(","):
                    col_match = re.match(r"\s*(\w+)\s*=", assignment)
                    if col_match:
                        col = col_match.group(1)
                        if col not in ("current_timestamp",) and col not in self._schema[table]:
                            raise ValueError(
                                f"MockD1 strict mode: UPDATE {table} "
                                f"references unknown column '{col}'. "
                                f"Schema columns: {sorted(self._schema[table])}"
                            )


class TrackingD1Statement(MockD1Statement):
    """Extends MockD1Statement with SQL and bound_args tracking.

    Used in tests that need to assert on the SQL queries and parameters
    that were passed to D1 (e.g., verifying INSERT/UPDATE statements).
    """

    def __init__(self, results: list[dict] | None = None, sql: str = ""):
        super().__init__(results or [], sql)
        self.bound_args: list = []

    def bind(self, *args) -> "TrackingD1Statement":
        self.bound_args = list(args)
        self._bound_args = args
        return self


class TrackingD1:
    """Mock D1 database that tracks all prepared statements.

    Uses TrackingD1Statement so tests can assert on SQL and bound parameters.
    """

    def __init__(self, statement_results: list[dict] | None = None):
        self._statement_results = statement_results or []
        self.last_statement: TrackingD1Statement | None = None
        self.statements: list[TrackingD1Statement] = []

    def prepare(self, sql: str) -> TrackingD1Statement:
        stmt = TrackingD1Statement(self._statement_results, sql)
        stmt.sql = sql
        self.last_statement = stmt
        self.statements.append(stmt)
        return stmt


class MockQueue:
    """Mock Cloudflare Queue."""

    def __init__(self):
        self.messages: list[dict] = []

    async def send(self, message: dict) -> None:
        self.messages.append(message)

    async def sendBatch(self, messages: list[dict]) -> None:
        for msg in messages:
            self.messages.append(msg.get("body", msg))


class MockVectorize:
    """Mock Vectorize index."""

    def __init__(self):
        self.vectors: dict[str, list[float]] = {}
        self.metadata: dict[str, dict] = {}

    async def upsert(self, vectors: list[dict]) -> None:
        for v in vectors:
            self.vectors[v["id"]] = v["values"]
            if "metadata" in v:
                self.metadata[v["id"]] = v["metadata"]

    async def query(self, vector: list[float], options: dict) -> Any:
        # Return a dict structure matching what SafeVectorize.query() returns
        matches = [{"id": id, "score": 0.9} for id in self.vectors]
        return {"matches": matches}

    async def deleteByIds(self, ids: list[str]) -> None:
        for id in ids:
            self.vectors.pop(id, None)
            self.metadata.pop(id, None)


class MockAI:
    """Mock Workers AI."""

    async def run(self, model: str, inputs: dict) -> dict:
        # Return fake 768-dim embedding (inputs ignored for mock)
        _ = model, inputs  # Acknowledge unused params
        return {"data": [[0.1] * 768]}


class MockAssets:
    """Mock Cloudflare ASSETS binding for static file serving."""

    def __init__(self, files: dict[str, tuple[str, str]] | None = None):
        """Initialize with optional file mappings.

        Args:
            files: Dict mapping paths to (content, content_type) tuples.
        """
        self._files = files or {
            "/static/style.css": ("/* mock css */", "text/css"),
            "/feeds.opml": ('<?xml version="1.0"?><opml/>', "application/xml"),
        }

    async def fetch(self, request) -> MockResponse:
        """Serve a static file based on request path."""
        url = str(request.url)
        # Extract path from URL
        path = "/" + url.split("://", 1)[1].split("/", 1)[-1] if "://" in url else url

        # Remove query string if present
        if "?" in path:
            path = path.split("?")[0]

        if path in self._files:
            content, content_type = self._files[path]
            return MockResponse(
                body=content,
                status=200,
                headers={"Content-Type": content_type},
            )
        return MockResponse(body="Not Found", status=404)


@dataclass
class MockEnv:
    """Mock Cloudflare Worker environment bindings."""

    DB: MockD1
    FEED_QUEUE: MockQueue
    DEAD_LETTER_QUEUE: MockQueue
    SEARCH_INDEX: MockVectorize
    AI: MockAI
    ASSETS: MockAssets | None = None
    PLANET_NAME: str = "Test Planet"
    PLANET_URL: str = "https://test.example.com"
    PLANET_DESCRIPTION: str = "Test description"
    PLANET_OWNER_NAME: str = "Test Owner"
    PLANET_OWNER_EMAIL: str = "test@example.com"
    SESSION_SECRET: str = "test-secret-key-for-testing-only-32chars"
    GITHUB_CLIENT_ID: str = "test-client-id"
    GITHUB_CLIENT_SECRET: str = "test-client-secret"

    def __post_init__(self):
        """Initialize ASSETS if not provided."""
        if self.ASSETS is None:
            self.ASSETS = MockAssets()


# =============================================================================
# Shared Test Helper Functions
# =============================================================================


def create_signed_session(
    secret: str = TEST_SESSION_SECRET,
    username: str = "testadmin",
    github_id: int = 12345,
) -> str:
    """Create a valid HMAC-signed session cookie for testing."""
    payload = {
        "github_username": username,
        "github_id": github_id,
        "avatar_url": None,
        "exp": int(time.time()) + 3600,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"session={payload_b64}.{signature}"


def admin_row() -> dict:
    """Return a standard admin DB row dict for testing."""
    return {
        "id": 1,
        "github_username": "testadmin",
        "github_id": 12345,
        "display_name": "Test Admin",
        "is_active": 1,
        "last_login_at": None,
        "created_at": "2026-01-01T00:00:00Z",
    }


def make_authenticated_worker(feeds=None, admins=None, env_class=None):
    """Build a Default worker with auth, returning (worker, env, session_cookie).

    Args:
        feeds: List of feed dicts for the mock DB.
        admins: List of admin dicts. Defaults to [admin_row()].
        env_class: Custom MockEnv class. Defaults to conftest MockEnv.
    """
    from src.main import Default

    admin_list = admins or [admin_row()]
    feed_list = feeds or []

    if env_class is not None:
        env = env_class(admins=admin_list, feeds=feed_list)
    else:
        data = {}
        if admin_list is not None:
            data["admins"] = admin_list
        if feed_list is not None:
            data["feeds"] = feed_list
        env = MockEnv(
            DB=MockD1(data),
            FEED_QUEUE=MockQueue(),
            DEAD_LETTER_QUEUE=MockQueue(),
            SEARCH_INDEX=MockVectorize(),
            AI=MockAI(),
        )

    session_cookie = create_signed_session(env.SESSION_SECRET)
    worker = Default()
    worker.env = env
    return worker, env, session_cookie


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture
def mock_env() -> MockEnv:
    """Create a mock environment with empty data."""
    return MockEnv(
        DB=MockD1(),
        FEED_QUEUE=MockQueue(),
        DEAD_LETTER_QUEUE=MockQueue(),
        SEARCH_INDEX=MockVectorize(),
        AI=MockAI(),
    )


@pytest.fixture
def mock_env_with_feeds(mock_env: MockEnv) -> MockEnv:
    """Create a mock environment with sample feeds."""
    mock_env.DB = MockD1(
        {
            "feeds": [
                {
                    "id": 1,
                    "url": "https://example.com/feed.xml",
                    "title": "Example",
                    "is_active": 1,
                    "site_url": "https://example.com",
                    "etag": None,
                    "last_modified": None,
                },
                {
                    "id": 2,
                    "url": "https://test.com/rss",
                    "title": "Test Blog",
                    "is_active": 1,
                    "site_url": "https://test.com",
                    "etag": None,
                    "last_modified": None,
                },
            ]
        }
    )
    return mock_env


@pytest.fixture
def mock_env_with_entries(mock_env: MockEnv) -> MockEnv:
    """Create a mock environment with sample entries."""
    mock_env.DB = MockD1(
        {
            "feeds": [
                {
                    "id": 1,
                    "url": "https://example.com/feed.xml",
                    "title": "Example",
                    "is_active": 1,
                    "site_url": "https://example.com",
                    "consecutive_failures": 0,
                    "last_success_at": "2026-01-01T00:00:00Z",
                },
            ],
            "entries": [
                {
                    "id": 1,
                    "feed_id": 1,
                    "guid": "entry-1",
                    "url": "https://example.com/post/1",
                    "title": "Test Entry 1",
                    "content": "<p>Content 1</p>",
                    "published_at": "2026-01-01T12:00:00Z",
                    "feed_title": "Example",
                    "feed_site_url": "https://example.com",
                },
                {
                    "id": 2,
                    "feed_id": 1,
                    "guid": "entry-2",
                    "url": "https://example.com/post/2",
                    "title": "Test Entry 2",
                    "content": "<p>Content 2</p>",
                    "published_at": "2026-01-01T14:00:00Z",
                    "feed_title": "Example",
                    "feed_site_url": "https://example.com",
                },
            ],
        }
    )
    return mock_env


@pytest.fixture
def mock_env_with_admins(mock_env: MockEnv) -> MockEnv:
    """Create a mock environment with sample admins."""
    mock_env.DB = MockD1(
        {
            "admins": [
                {
                    "id": 1,
                    "github_username": "testadmin",
                    "github_id": 12345,
                    "display_name": "Test Admin",
                    "is_active": 1,
                    "last_login_at": None,
                    "created_at": "2026-01-01T00:00:00Z",
                },
            ]
        }
    )
    return mock_env


# =============================================================================
# Test Data Factories (imported from canonical source)
# =============================================================================

from tests.fixtures.factories import EntryFactory, FeedFactory, FeedJobFactory


# Reset factories before each test module
@pytest.fixture(autouse=True)
def reset_factories():
    """Reset factory counters before each test."""
    FeedFactory.reset()
    EntryFactory.reset()
    FeedJobFactory.reset()
    yield
