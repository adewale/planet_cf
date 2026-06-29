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
from hypothesis import HealthCheck, settings

# =============================================================================
# Hypothesis Profile (M-T1)
# =============================================================================
# Under coverage/tracing instrumentation, individual examples can exceed
# Hypothesis's default per-example deadline and trip the `too_slow` health
# check (e.g. regex-strategy draws), making CI flaky. Register and load a
# profile that disables the deadline and suppresses the timing health checks so
# property tests don't flake when run with --cov.

settings.register_profile(
    "ci",
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
    ],
)
settings.load_profile("ci")

# =============================================================================
# Shared Test Constants
# =============================================================================

TEST_SESSION_SECRET = "test-secret-key-for-testing-only-32chars"  # pragma: allowlist secret


def _csrf_token_from_cookie(cookies: str, secret: str = TEST_SESSION_SECRET) -> str:
    """Compute the CSRF token matching a session cookie (mirrors the server).

    Used by MockRequest to auto-supply a valid token for authenticated
    state-changing requests — modelling a real admin browser, which receives
    the token embedded in the rendered admin page. Returns "" if no session.
    """
    from src.auth import generate_csrf_token

    if not cookies:
        return ""
    try:
        val = cookies.split("session=", 1)[1].split(";", 1)[0] if "session=" in cookies else cookies
        payload_b64 = val.rsplit(".", 1)[0]
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return generate_csrf_token(payload, secret)
    except Exception:
        return ""


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
        csrf: bool = True,
        secret: str = TEST_SESSION_SECRET,
    ):
        from unittest.mock import MagicMock

        self.url = url
        self.method = method
        self._body = body
        self._cookies = cookies
        self._form_data = form_data or {}
        self._json_data = json_data or {}

        # H15: model a correct admin browser. When the request carries a session
        # cookie, supply the matching CSRF token (via the X-CSRF-Token header and
        # a csrf_token form field) unless the test opts out with csrf=False or
        # provides its own. This lets the ~20 existing admin-mutation tests keep
        # passing; test_csrf.py covers the missing/invalid/cross-session cases.
        self._csrf_token = _csrf_token_from_cookie(cookies, secret) if csrf else ""
        if (
            self._csrf_token
            and "csrf_token" not in self._form_data
            and not self._has_explicit_header(headers, "x-csrf-token")
        ):
            self._form_data = {**self._form_data, "csrf_token": self._csrf_token}

        # Use MagicMock headers with side_effect for cookie/header lookups
        # (compatible with SafeHeaders which calls headers.get())
        self.headers = MagicMock()
        # Merge explicit headers with cookie header
        self._raw_headers = headers or {}
        self.headers.get = MagicMock(side_effect=self._get_header)

    @staticmethod
    def _has_explicit_header(headers: dict | None, name: str) -> bool:
        return bool(headers) and any(k.lower() == name.lower() for k in headers)

    def _get_header(self, name, default=None):
        # Check explicit headers first (case-insensitive)
        for key, val in self._raw_headers.items():
            if key.lower() == name.lower():
                return val
        # Auto-supply the session-matched CSRF token (explicit header wins above).
        if name.lower() == "x-csrf-token" and self._csrf_token:
            return self._csrf_token
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


def _count_sql_placeholders(sql: str) -> int:
    """Count `?` bind placeholders in SQL, ignoring those inside string literals.

    Mirrors real D1, which raises when the number of bound values doesn't match
    the number of placeholders. Single- and double-quoted string contents are
    skipped so a literal "?" in text isn't miscounted.
    """
    count = 0
    quote: str | None = None
    for ch in sql:
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "?":
            count += 1
    return count


class MockD1Statement:
    """Mock D1 prepared statement."""

    def __init__(self, results: list[dict], sql: str = ""):
        self._results = results
        self._sql = sql
        self._bound_args = []

    def bind(self, *args) -> "MockD1Statement":
        # M-T3: validate bind arity against the number of `?` placeholders, like
        # real D1. A mismatch is a real bug (this is how H3 slipped through — the
        # old mock never checked). Statements with no placeholders that are
        # nonetheless bound (e.g. defensive .bind() calls) are allowed when no
        # args are passed.
        expected = _count_sql_placeholders(self._sql)
        if expected and len(args) != expected:
            raise ValueError(
                f"MockD1: bind() got {len(args)} argument(s) but SQL has "
                f"{expected} placeholder(s). SQL: {self._sql.strip()[:200]}"
            )
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
        # M-T3: enforce bind-arity (see MockD1Statement.bind).
        expected = _count_sql_placeholders(self._sql)
        if expected and len(args) != expected:
            raise ValueError(
                f"MockD1: bind() got {len(args)} argument(s) but SQL has "
                f"{expected} placeholder(s). SQL: {self._sql.strip()[:200]}"
            )
        self.bound_args = list(args)
        self._bound_args = args
        return self


class TrackingD1:
    """Mock D1 database that tracks all prepared statements.

    Uses TrackingD1Statement so tests can assert on SQL and bound parameters.

    Args:
        statement_results: default result rows returned for every statement.
        results_by_sql: optional list of (sql_substring, result_rows) pairs.
            The first substring found in a statement's SQL wins, letting a test
            simulate, e.g., an INSERT ... DO NOTHING that returns no row (a
            conflict) while a following UPDATE returns a row. Falls back to
            statement_results when nothing matches.
    """

    def __init__(
        self,
        statement_results: list[dict] | None = None,
        results_by_sql: list[tuple[str, list[dict]]] | None = None,
    ):
        self._statement_results = statement_results or []
        self._results_by_sql = results_by_sql or []
        self.last_statement: TrackingD1Statement | None = None
        self.statements: list[TrackingD1Statement] = []

    def prepare(self, sql: str) -> TrackingD1Statement:
        results = self._statement_results
        for needle, rows in self._results_by_sql:
            if needle in sql:
                results = rows
                break
        stmt = TrackingD1Statement(results, sql)
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
    CLOUDFLARE_ZONE_ID: str = ""
    CLOUDFLARE_API_TOKEN: str = ""

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


def csrf_token_for(session_cookie: str, secret: str = TEST_SESSION_SECRET) -> str:
    """Return the CSRF token that matches a test session cookie."""
    return _csrf_token_from_cookie(session_cookie, secret)


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


@pytest.fixture(autouse=True)
def reset_auth_rate_limits():
    """Clear the module-level auth rate-limit dict before each test (M-T5).

    src.main._auth_rate_limits is keyed by IP ("unknown" for every MockRequest),
    uses real time.time(), and is never otherwise reset. Without this, once the
    suite accumulates enough /auth/* fetches the next auth test to run starts
    getting 429s — an ordering-dependent time bomb.
    """
    import src.main as _main

    if hasattr(_main, "_auth_rate_limits"):
        _main._auth_rate_limits.clear()
    yield
    if hasattr(_main, "_auth_rate_limits"):
        _main._auth_rate_limits.clear()
