# tests/conftest.py
"""Shared fixtures for Planet CF tests."""

import time
from dataclasses import dataclass
from typing import Any

import pytest

from src.types import EntryRow, FeedId, FeedRow, Session


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

    def __init__(self, results: list[dict]):
        self._results = results

    def bind(self, *args) -> "MockD1Statement":
        return self

    async def all(self) -> MockD1Result:
        return MockD1Result(results=self._results)

    async def first(self) -> dict | None:
        return self._results[0] if self._results else None

    async def run(self) -> MockD1Result:
        return MockD1Result(results=[])


class MockD1:
    """Mock D1 database."""

    def __init__(self, data: dict[str, list[dict]] | None = None):
        self._data = data or {}

    def prepare(self, sql: str) -> MockD1Statement:
        # Simple mock - return data based on table mentioned in SQL
        sql_lower = sql.lower()
        for table, rows in self._data.items():
            if table in sql_lower:
                return MockD1Statement(rows)
        return MockD1Statement([])


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
        # Simple mock - return all stored IDs
        @dataclass
        class Match:
            id: str
            score: float = 0.9

        matches = [Match(id=id, score=0.9) for id in self.vectors.keys()]
        return type("QueryResult", (), {"matches": matches})()

    async def deleteByIds(self, ids: list[str]) -> None:
        for id in ids:
            self.vectors.pop(id, None)
            self.metadata.pop(id, None)


class MockAI:
    """Mock Workers AI."""

    async def run(self, model: str, inputs: dict) -> dict:
        # Return fake 768-dim embedding
        text = inputs.get("text", [""])[0]
        return {"data": [[0.1] * 768]}


@dataclass
class MockEnv:
    """Mock Cloudflare Worker environment bindings."""
    DB: MockD1
    FEED_QUEUE: MockQueue
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
        SEARCH_INDEX=MockVectorize(),
        AI=MockAI(),
    )


@pytest.fixture
def mock_env_with_feeds(mock_env: MockEnv) -> MockEnv:
    """Create a mock environment with sample feeds."""
    mock_env.DB = MockD1({
        "feeds": [
            {"id": 1, "url": "https://example.com/feed.xml", "title": "Example", "is_active": 1, "etag": None, "last_modified": None},
            {"id": 2, "url": "https://test.com/rss", "title": "Test Blog", "is_active": 1, "etag": None, "last_modified": None},
        ]
    })
    return mock_env


@pytest.fixture
def mock_env_with_entries(mock_env: MockEnv) -> MockEnv:
    """Create a mock environment with sample entries."""
    mock_env.DB = MockD1({
        "feeds": [
            {"id": 1, "url": "https://example.com/feed.xml", "title": "Example", "is_active": 1, "site_url": "https://example.com", "consecutive_failures": 0, "last_success_at": "2026-01-01T00:00:00Z"},
        ],
        "entries": [
            {"id": 1, "feed_id": 1, "guid": "entry-1", "url": "https://example.com/post/1", "title": "Test Entry 1", "content": "<p>Content 1</p>", "published_at": "2026-01-01T12:00:00Z", "feed_title": "Example", "feed_site_url": "https://example.com"},
            {"id": 2, "feed_id": 1, "guid": "entry-2", "url": "https://example.com/post/2", "title": "Test Entry 2", "content": "<p>Content 2</p>", "published_at": "2026-01-01T14:00:00Z", "feed_title": "Example", "feed_site_url": "https://example.com"},
        ]
    })
    return mock_env


@pytest.fixture
def mock_env_with_admins(mock_env: MockEnv) -> MockEnv:
    """Create a mock environment with sample admins."""
    mock_env.DB = MockD1({
        "admins": [
            {"id": 1, "github_username": "testadmin", "github_id": 12345, "display_name": "Test Admin", "is_active": 1, "last_login_at": None, "created_at": "2026-01-01T00:00:00Z"},
        ]
    })
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
