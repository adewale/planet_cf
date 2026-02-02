# tests/conftest.py
"""Shared fixtures for Planet CF tests."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

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
    """Mock Cloudflare Workers Request object."""

    def __init__(
        self,
        url: str = "https://example.com/",
        method: str = "GET",
        headers: dict | None = None,
        body: str | bytes | None = None,
    ):
        self.url = url
        self.method = method
        self._headers = headers or {}
        self._body = body

    @property
    def headers(self) -> dict:
        return self._headers

    async def text(self) -> str:
        if isinstance(self._body, bytes):
            return self._body.decode("utf-8")
        return self._body or ""

    async def json(self) -> Any:
        import json

        return json.loads(await self.text())


# Create mock workers module
_mock_workers = ModuleType("workers")
_mock_workers.Request = MockRequest
_mock_workers.Response = MockResponse
_mock_workers.WorkerEntrypoint = MockWorkerEntrypoint

# Install the mock before any imports of src.main
sys.modules["workers"] = _mock_workers


from src.models import EntryRow, FeedRow, Session

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
    """Mock D1 database."""

    def __init__(self, data: dict[str, list[dict]] | None = None):
        self._data = data or {}

    def prepare(self, sql: str) -> MockD1Statement:
        """
        Parse SQL to determine which table to return data for.

        Priority order:
        1. DELETE FROM table_name
        2. INSERT INTO table_name
        3. UPDATE table_name
        4. FROM table_name (the primary table in SELECT)
        5. Simple table name match as fallback
        """
        import re

        sql_lower = sql.lower()

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


@dataclass
class MockEnv:
    """Mock Cloudflare Worker environment bindings."""

    DB: MockD1
    FEED_QUEUE: MockQueue
    DEAD_LETTER_QUEUE: MockQueue
    SEARCH_INDEX: MockVectorize
    AI: MockAI
    PLANET_NAME: str = "Test Planet"
    PLANET_URL: str = "https://test.example.com"
    PLANET_DESCRIPTION: str = "Test description"
    PLANET_OWNER_NAME: str = "Test Owner"
    PLANET_OWNER_EMAIL: str = "test@example.com"
    SESSION_SECRET: str = "test-secret-key-for-testing-only-32chars"
    GITHUB_CLIENT_ID: str = "test-client-id"
    GITHUB_CLIENT_SECRET: str = "test-client-secret"


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
# Test Data Factories
# =============================================================================


class FeedFactory:
    """Factory for creating test feed data."""

    _counter = 0

    @classmethod
    def create(cls, **overrides) -> FeedRow:
        cls._counter += 1
        defaults: FeedRow = {
            "id": cls._counter,
            "url": f"https://feed{cls._counter}.example.com/rss",
            "title": f"Test Feed {cls._counter}",
            "site_url": f"https://feed{cls._counter}.example.com",
            "is_active": 1,
            "consecutive_failures": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        return {**defaults, **overrides}

    @classmethod
    def reset(cls):
        cls._counter = 0


class EntryFactory:
    """Factory for creating test entry data."""

    _counter = 0

    @classmethod
    def create(cls, feed_id: int = 1, **overrides) -> EntryRow:
        cls._counter += 1
        defaults: EntryRow = {
            "id": cls._counter,
            "feed_id": feed_id,
            "guid": f"entry-{cls._counter}",
            "url": f"https://example.com/post/{cls._counter}",
            "title": f"Test Entry {cls._counter}",
            "content": "<p>Test content</p>",
            "published_at": "2026-01-01T12:00:00Z",
            "created_at": "2026-01-01T12:00:00Z",
        }
        return {**defaults, **overrides}

    @classmethod
    def reset(cls):
        cls._counter = 0


class SessionFactory:
    """Factory for creating test session data."""

    @classmethod
    def create(cls, **overrides) -> Session:
        defaults = {
            "github_username": "testuser",
            "github_id": 12345,
            "avatar_url": "https://github.com/testuser.png",
            "exp": int(time.time()) + 3600,  # 1 hour from now
        }
        return Session(**{**defaults, **overrides})


# Reset factories before each test module
@pytest.fixture(autouse=True)
def reset_factories():
    """Reset factory counters before each test."""
    FeedFactory.reset()
    EntryFactory.reset()
    yield
