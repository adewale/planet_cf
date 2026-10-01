# tests/unit/test_admin_operations.py
"""Unit tests for admin operations in main.py."""

import json

import pytest

from src.main import Default
from tests.conftest import MockEnv, MockQueue
from tests.mocks.sqlite_d1 import SQLiteD1

# =============================================================================
# Mock Classes for Testing (MockRequest/MockFormData are specialized for this
# file: json_body param, plain-dict headers. _make_env wraps conftest MockEnv.)
# =============================================================================


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


def _make_env(db):
    """Create a MockEnv for admin operations tests."""
    return MockEnv(
        DB=db,
        FEED_QUEUE=MockQueue(),
        DEAD_LETTER_QUEUE=MockQueue(),
        SEARCH_INDEX=None,
        AI=None,
    )


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def db():
    """SQLite with the migrated schema; UPDATEs and audit rows really persist."""
    return SQLiteD1.from_migrations()


@pytest.fixture
def mock_admin(db):
    """An admin row that exists, so the audit_log foreign key is satisfied (as in D1)."""
    admin_id = db.insert(
        "admins", github_username="testadmin", display_name="Test Admin", is_active=1
    )
    return {
        "id": admin_id,
        "github_username": "testadmin",
        "display_name": "Test Admin",
        "is_active": 1,
    }


@pytest.fixture
def worker(db):
    """Worker with feed 42 (the target) and feed 43 (a bystander that must not change)."""
    db.insert("feeds", id=42, url="https://example.com/feed.xml", title="Original Title")
    db.insert("feeds", id=43, url="https://other.example/feed.xml", title="Bystander")
    w = Default()
    w.env = _make_env(db)
    return w


def _feeds(db) -> dict[int, dict]:
    return {r["id"]: r for r in db.rows("SELECT id, title, is_active FROM feeds")}


BYSTANDER = {"id": 43, "title": "Bystander", "is_active": 1}


# =============================================================================
# Feed Update Tests
# =============================================================================


class TestUpdateFeed:
    """Tests for _update_feed method."""

    @pytest.mark.asyncio
    async def test_update_feed_title(self, db, worker, mock_admin):
        """Updates the title of the target feed only."""
        request = MockRequest(
            method="PUT",
            url="https://example.com/admin/feeds/42",
            headers={"Content-Type": "application/json"},
            json_body={"title": "New Title"},
        )

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 200
        assert json.loads(response.body)["success"] is True
        feeds = _feeds(db)
        assert feeds[42] == {"id": 42, "title": "New Title", "is_active": 1}
        assert feeds[43] == BYSTANDER

    @pytest.mark.asyncio
    async def test_update_feed_is_active(self, db, worker, mock_admin):
        """Disables the target feed without touching its title."""
        request = MockRequest(method="PUT", json_body={"is_active": False})

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 200
        feeds = _feeds(db)
        assert feeds[42] == {"id": 42, "title": "Original Title", "is_active": 0}
        assert feeds[43] == BYSTANDER

    @pytest.mark.asyncio
    async def test_update_feed_both_fields(self, db, worker, mock_admin):
        """Re-enables a disabled feed and renames it in one request."""
        db.conn.execute("UPDATE feeds SET is_active = 0 WHERE id = 42")
        request = MockRequest(method="PUT", json_body={"title": "New Title", "is_active": True})

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 200
        assert _feeds(db)[42] == {"id": 42, "title": "New Title", "is_active": 1}

    @pytest.mark.asyncio
    async def test_update_feed_no_fields_returns_error(self, db, worker, mock_admin):
        """Returns 400 error when no valid fields provided."""
        request = MockRequest(method="PUT", json_body={})

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 400
        body = json.loads(response.body)
        assert "No valid fields" in body["error"]
        assert _feeds(db)[42]["title"] == "Original Title"

    @pytest.mark.asyncio
    async def test_update_feed_empty_title_is_stored_as_empty_string(self, db, worker, mock_admin):
        """An empty title is stored as "" (``_safe_str`` maps only None/undefined to None)."""
        request = MockRequest(method="PUT", json_body={"title": ""})

        response = await worker._update_feed(request, "42", mock_admin)

        assert response.status == 200
        assert _feeds(db)[42]["title"] == ""

    @pytest.mark.asyncio
    async def test_update_feed_invalid_id_returns_error(self, db, worker, mock_admin):
        """Returns 500 for a non-numeric feed ID, and no feed changes."""
        request = MockRequest(method="PUT", json_body={"title": "New Title"})

        response = await worker._update_feed(request, "not-a-number", mock_admin)

        assert response.status == 500
        assert {f["title"] for f in _feeds(db).values()} == {"Original Title", "Bystander"}

    @pytest.mark.asyncio
    async def test_update_feed_logs_audit(self, db, worker, mock_admin):
        """Writes an audit_log row naming the admin, the feed and the new values."""
        request = MockRequest(method="PUT", json_body={"title": "New Title"})

        await worker._update_feed(request, "42", mock_admin)

        (audit,) = db.rows(
            "SELECT admin_id, action, target_type, target_id, details FROM audit_log"
        )
        assert audit["admin_id"] == mock_admin["id"]
        assert (audit["action"], audit["target_type"], audit["target_id"]) == (
            "update_feed",
            "feed",
            42,
        )
        assert json.loads(audit["details"]) == {"title": "New Title"}
