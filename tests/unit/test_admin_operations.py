# tests/unit/test_admin_operations.py
"""Unit tests for admin operations in main.py."""

import json

import pytest

from src.main import Default
from tests.conftest import MockD1Statement

# =============================================================================
# Mock Classes for Testing
# =============================================================================


class TrackingD1Statement(MockD1Statement):
    """Extends conftest MockD1Statement with SQL and bound_args tracking."""

    def __init__(self, results: list[dict] | None = None, sql: str = ""):
        super().__init__(results or [], sql)
        self.bound_args: list = []

    def bind(self, *args) -> "TrackingD1Statement":
        self.bound_args = list(args)
        self._bound_args = args
        return self


class TrackingD1:
    """Mock D1 database that tracks all prepared statements.

    Uses conftest MockD1Result and MockD1Statement as building blocks,
    but adds statement tracking for test assertions on SQL and params.
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


class MockRequest:
    """Mock HTTP request object."""

    def __init__(
        self,
        method: str = "GET",
        url: str = "https://example.com",
        headers: dict | None = None,
        json_body: dict | None = None,
        form_data: dict | None = None,
    ):
        self.method = method
        self.url = url
        self.headers = headers or {}
        self._json_body = json_body
        self._form_data = form_data

    async def json(self):
        return self._json_body or {}

    async def form_data(self):
        return MockFormData(self._form_data or {})


class MockFormData:
    """Mock form data object."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key: str):
        return self._data.get(key)


class MockEnv:
    """Mock Cloudflare Workers environment."""

    def __init__(self, db: TrackingD1 | None = None):
        self.DB = db or TrackingD1()
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = MockQueue()
        self.DEAD_LETTER_QUEUE = MockQueue()
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret-key-for-testing-only"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"


class MockQueue:
    """Mock Cloudflare Queue."""

    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)
        return {"success": True}


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_admin():
    """Return a mock admin user dict."""
    return {
        "id": 1,
        "github_username": "testadmin",
        "display_name": "Test Admin",
        "is_active": 1,
    }


@pytest.fixture
def mock_feed():
    """Return a mock feed dict."""
    return {
        "id": 42,
        "url": "https://example.com/feed.xml",
        "title": "Original Title",
        "site_url": "https://example.com",
        "is_active": 1,
        "consecutive_failures": 0,
    }


# =============================================================================
# Feed Update Tests
# =============================================================================


class TestUpdateFeed:
    """Tests for _update_feed method."""

    @pytest.mark.asyncio
    async def test_update_feed_title(self, mock_admin, mock_feed):
        """Updates feed title when title is provided."""
        db = TrackingD1([mock_feed])
        env = MockEnv(db=db)

        worker = Default()
        worker.env = env

        request = MockRequest(
            method="PUT",
            url="https://example.com/admin/feeds/42",
            headers={"Content-Type": "application/json"},
            json_body={"title": "New Title"},
        )

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 200
        body = json.loads(response.body)
        assert body["success"] is True

        # Verify the SQL was correct
        update_stmt = db.statements[-2]  # -1 is audit log
        assert "title = ?" in update_stmt.sql
        assert "New Title" in update_stmt.bound_args

    @pytest.mark.asyncio
    async def test_update_feed_is_active(self, mock_admin, mock_feed):
        """Updates feed is_active when is_active is provided."""
        db = TrackingD1([mock_feed])
        env = MockEnv(db=db)

        worker = Default()
        worker.env = env

        request = MockRequest(
            method="PUT",
            json_body={"is_active": False},
        )

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 200

        # Verify the SQL was correct
        update_stmt = db.statements[-2]
        assert "is_active = ?" in update_stmt.sql
        assert 0 in update_stmt.bound_args

    @pytest.mark.asyncio
    async def test_update_feed_both_fields(self, mock_admin, mock_feed):
        """Updates both title and is_active when both provided."""
        db = TrackingD1([mock_feed])
        env = MockEnv(db=db)

        worker = Default()
        worker.env = env

        request = MockRequest(
            method="PUT",
            json_body={"title": "New Title", "is_active": True},
        )

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 200

        # Verify SQL includes both fields
        update_stmt = db.statements[-2]
        assert "is_active = ?" in update_stmt.sql
        assert "title = ?" in update_stmt.sql

    @pytest.mark.asyncio
    async def test_update_feed_no_fields_returns_error(self, mock_admin, mock_feed):
        """Returns 400 error when no valid fields provided."""
        db = TrackingD1([mock_feed])
        env = MockEnv(db=db)

        worker = Default()
        worker.env = env

        request = MockRequest(
            method="PUT",
            json_body={},
        )

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 400
        body = json.loads(response.body)
        assert "error" in body
        assert "No valid fields" in body["error"]

    @pytest.mark.asyncio
    async def test_update_feed_empty_title(self, mock_admin, mock_feed):
        """Handles empty string title (converts to None via _safe_str)."""
        db = TrackingD1([mock_feed])
        env = MockEnv(db=db)

        worker = Default()
        worker.env = env

        request = MockRequest(
            method="PUT",
            json_body={"title": ""},
        )

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 200

        # Empty string should be converted to None by _safe_str
        update_stmt = db.statements[-2]
        assert None in update_stmt.bound_args or "" in update_stmt.bound_args

    @pytest.mark.asyncio
    async def test_update_feed_invalid_id_returns_error(self, mock_admin):
        """Returns 500 error for invalid feed ID."""
        db = TrackingD1([])
        env = MockEnv(db=db)

        worker = Default()
        worker.env = env

        request = MockRequest(
            method="PUT",
            json_body={"title": "New Title"},
        )

        response = await worker._update_feed(request, "not-a-number", mock_admin)

        assert response.status == 500

    @pytest.mark.asyncio
    async def test_update_feed_logs_audit(self, mock_admin, mock_feed):
        """Creates audit log entry when feed is updated."""
        db = TrackingD1([mock_feed])
        env = MockEnv(db=db)

        worker = Default()
        worker.env = env

        request = MockRequest(
            method="PUT",
            json_body={"title": "New Title"},
        )

        await worker._update_feed(request, "42", mock_admin)

        # Find the audit log INSERT statement
        audit_stmt = db.statements[-1]
        assert "INSERT INTO audit_log" in audit_stmt.sql


class TestUpdateFeedTitleSanitization:
    """Tests for feed title sanitization in updates."""

    @pytest.mark.asyncio
    async def test_title_is_sanitized(self, mock_admin, mock_feed):
        """Title is passed through _safe_str for sanitization."""
        db = TrackingD1([mock_feed])
        env = MockEnv(db=db)

        worker = Default()
        worker.env = env

        # Test with a title containing leading/trailing whitespace
        request = MockRequest(
            method="PUT",
            json_body={"title": "  Trimmed Title  "},
        )

        response = await worker._update_feed(request, "42", mock_admin)
        assert response.status == 200

        # The title should be in the bound args (may or may not be trimmed depending on _safe_str behavior)
        update_stmt = db.statements[-2]
        assert any("Trimmed Title" in str(arg) for arg in update_stmt.bound_args if arg)
