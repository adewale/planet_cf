# tests/unit/test_import_opml.py
"""Unit tests for _import_opml orchestration in src/main.py."""

import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest

from src.main import Default
from tests.conftest import MockD1Statement

# =============================================================================
# Compatibility: ET.XMLParser(forbid_dtd=True) was added in Python 3.13.1.
# The production Cloudflare Workers runtime (Pyodide / Python 3.12) supports it
# via a patch, but the local test runner may not. We patch ET.XMLParser to
# accept and silently ignore the keyword when unsupported.
# =============================================================================

_original_xml_parser = ET.XMLParser


def _patched_xml_parser(**kwargs):
    kwargs.pop("forbid_dtd", None)
    return _original_xml_parser(**kwargs)


# =============================================================================
# Mock Infrastructure
# =============================================================================

VALID_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>My Feeds</title></head>
  <body>
    <outline text="Tech" title="Tech">
      <outline type="rss" text="Example Blog" title="Example Blog"
               xmlUrl="https://example.com/feed.xml"
               htmlUrl="https://example.com" />
      <outline type="rss" text="Test Feed" title="Test Feed"
               xmlUrl="https://test.com/rss"
               htmlUrl="https://test.com" />
    </outline>
  </body>
</opml>"""

EMPTY_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Empty</title></head>
  <body></body>
</opml>"""


class TrackingD1Statement(MockD1Statement):
    """Extends MockD1Statement with SQL and bound_args tracking."""

    def __init__(self, results: list[dict] | None = None, sql: str = ""):
        super().__init__(results or [], sql)
        self.bound_args: list = []

    def bind(self, *args) -> "TrackingD1Statement":
        self.bound_args = list(args)
        self._bound_args = args
        return self


class TrackingD1:
    """Mock D1 database that tracks all prepared statements."""

    def __init__(self):
        self.statements: list[TrackingD1Statement] = []

    def prepare(self, sql: str) -> TrackingD1Statement:
        stmt = TrackingD1Statement([], sql)
        stmt.sql = sql
        self.statements.append(stmt)
        return stmt


class MockQueue:
    """Mock Cloudflare Queue."""

    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class MockFormData:
    """Mock form data for OPML import tests."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockFile:
    """Mock uploaded file object."""

    def __init__(self, content: str):
        self._content = content

    def text(self):
        return self._content


class MockRequest:
    """Mock HTTP request for OPML import tests."""

    def __init__(self, opml_content: str | None = None, form_data: dict | None = None):
        self.method = "POST"
        self.url = "https://example.com/admin/import-opml"
        self.headers = {}
        self._form_data = form_data or {}
        if opml_content is not None:
            self._form_data["opml"] = MockFile(opml_content)

    async def form_data(self):
        return MockFormData(self._form_data)


class MockEnv:
    """Mock Cloudflare Workers environment for OPML import tests."""

    def __init__(self, db: TrackingD1 | None = None):
        self.DB = db or TrackingD1()
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = MockQueue()
        self.DEAD_LETTER_QUEUE = MockQueue()
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"


def _mock_admin() -> dict:
    """Return a mock admin user dict."""
    return {
        "id": 1,
        "github_username": "testadmin",
        "display_name": "Test Admin",
        "is_active": 1,
    }


# =============================================================================
# Tests: _import_opml orchestration
# =============================================================================


class TestImportOpml:
    """Tests for Default._import_opml orchestration."""

    @pytest.mark.asyncio
    async def test_successful_import_with_valid_opml(self):
        """Valid OPML file imports feeds and redirects."""
        db = TrackingD1()
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env
        admin = _mock_admin()

        request = MockRequest(opml_content=VALID_OPML)

        with patch("src.main.ET.XMLParser", _patched_xml_parser):
            response = await worker._import_opml(request, admin)

        # Should redirect on success
        assert response.status == 302
        assert response.headers.get("Location") == "/admin"

        # Should have INSERT statements for feeds
        insert_stmts = [s for s in db.statements if "INSERT INTO feeds" in s.sql]
        assert len(insert_stmts) >= 2  # Two feeds in OPML

        # Verify the feed URLs were inserted
        inserted_urls = [s.bound_args[0] for s in insert_stmts if s.bound_args]
        assert "https://example.com/feed.xml" in inserted_urls
        assert "https://test.com/rss" in inserted_urls

    @pytest.mark.asyncio
    async def test_import_with_no_file_returns_error(self):
        """Import with no file uploaded returns error."""
        env = MockEnv()
        worker = Default()
        worker.env = env
        admin = _mock_admin()

        request = MockRequest(form_data={})  # No opml file

        response = await worker._import_opml(request, admin)

        assert response.status in (200, 400)
        assert "No File" in response.body or "OPML" in response.body

    @pytest.mark.asyncio
    async def test_import_with_empty_opml(self):
        """Empty OPML (no feeds) completes without inserting feeds."""
        db = TrackingD1()
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env
        admin = _mock_admin()

        request = MockRequest(opml_content=EMPTY_OPML)

        with patch("src.main.ET.XMLParser", _patched_xml_parser):
            response = await worker._import_opml(request, admin)

        # Should redirect (successful even if no feeds imported)
        assert response.status == 302

        # No feed INSERT statements (only audit_log INSERT)
        feed_insert_stmts = [s for s in db.statements if "INSERT INTO feeds" in s.sql]
        assert len(feed_insert_stmts) == 0

    @pytest.mark.asyncio
    async def test_import_skips_unsafe_urls(self):
        """OPML feeds with unsafe URLs are skipped."""
        opml_with_unsafe = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
          <body>
            <outline type="rss" text="Safe Feed" title="Safe Feed"
                     xmlUrl="https://safe.example.com/feed.xml" />
            <outline type="rss" text="Unsafe Feed" title="Unsafe Feed"
                     xmlUrl="http://localhost/feed.xml" />
            <outline type="rss" text="Metadata" title="Metadata"
                     xmlUrl="http://169.254.169.254/latest/meta-data/" />
          </body>
        </opml>"""

        db = TrackingD1()
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env
        admin = _mock_admin()

        request = MockRequest(opml_content=opml_with_unsafe)

        with patch("src.main.ET.XMLParser", _patched_xml_parser):
            response = await worker._import_opml(request, admin)

        assert response.status == 302

        # Only the safe URL should have an INSERT
        feed_insert_stmts = [s for s in db.statements if "INSERT INTO feeds" in s.sql]
        assert len(feed_insert_stmts) == 1
        assert "https://safe.example.com/feed.xml" in feed_insert_stmts[0].bound_args

    @pytest.mark.asyncio
    async def test_import_invalid_xml_returns_error(self):
        """Invalid XML content returns parse error."""
        env = MockEnv()
        worker = Default()
        worker.env = env
        admin = _mock_admin()

        request = MockRequest(opml_content="<not valid xml")

        with patch("src.main.ET.XMLParser", _patched_xml_parser):
            response = await worker._import_opml(request, admin)

        assert response.status in (200, 400)
        assert "Invalid OPML" in response.body or "format" in response.body.lower()

    @pytest.mark.asyncio
    async def test_import_creates_audit_log(self):
        """Audit log entry is created for OPML import."""
        db = TrackingD1()
        env = MockEnv(db=db)
        worker = Default()
        worker.env = env
        admin = _mock_admin()

        request = MockRequest(opml_content=VALID_OPML)

        with patch("src.main.ET.XMLParser", _patched_xml_parser):
            await worker._import_opml(request, admin)

        # Should have an audit_log INSERT
        audit_stmts = [s for s in db.statements if "INSERT INTO audit_log" in s.sql]
        assert len(audit_stmts) >= 1
