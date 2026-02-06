# src/wrappers.py
"""JavaScript/Python Boundary Layer for Cloudflare Workers.

This module provides a clean boundary between JavaScript (Pyodide/JsProxy)
and Python. All JavaScript bindings (D1, AI, Vectorize, Queue) are wrapped to
automatically convert JsProxy objects to native Python types.

This ensures that application code NEVER sees JsProxy objects - they are
converted at the boundary layer before reaching business logic.
"""

from typing import Any
from urllib.parse import urlencode

import httpx

# =============================================================================
# Module-level constants
# =============================================================================

# Maximum recursion depth for _to_py_safe() JsProxy-to-Python conversion.
# Feeds rarely nest beyond a few levels; 50 is generous headroom.
_MAX_CONVERSION_DEPTH = 50

# Default timeout in seconds for HTTP fetch requests.
_DEFAULT_HTTP_TIMEOUT_SECONDS = 30

# =============================================================================
# Pyodide-specific imports (only available in Cloudflare Workers environment)
# =============================================================================

try:
    import js
    from js import fetch as js_fetch
    from pyodide.ffi import to_js

    HAS_PYODIDE = True
    # Create a proper JavaScript null value for D1 bindings
    # Python None -> JS undefined, but D1 needs JS null for SQL NULL
    # Note: js.eval() is disallowed in Workers, so use JSON.parse instead
    JS_NULL = js.JSON.parse("null")
except ImportError:
    # Test environment - these will not be used
    js = None
    js_fetch = None
    to_js = None
    JS_NULL = None
    HAS_PYODIDE = False


# =============================================================================
# Python→JavaScript Conversion
# =============================================================================


def _to_js_value(value: Any) -> Any:
    """Convert Python value to JavaScript for Workers bindings.

    Centralizes the HAS_PYODIDE check and proper dict conversion.
    For dicts, uses Object.fromEntries to create proper JS objects.
    For other types (lists, primitives), uses plain to_js().

    Returns value unchanged in test environment (not Pyodide).
    """
    if not HAS_PYODIDE or to_js is None:
        return value
    if isinstance(value, dict):
        return to_js(value, dict_converter=js.Object.fromEntries)
    return to_js(value)


# =============================================================================
# JavaScript→Python Conversion
# =============================================================================


def _is_js_undefined(value: Any) -> bool:
    """Check if a value is JavaScript undefined (wrapped as JsProxy in Pyodide)."""
    if value is None:
        return False
    if not HAS_PYODIDE:
        return False
    # In Pyodide, JavaScript undefined has typeof == "undefined"
    try:
        if hasattr(value, "typeof") and value.typeof == "undefined":
            return True
        # Also check for JsUndefined type from pyodide.ffi
        type_name = type(value).__name__
        if type_name in ("JsUndefined", "JsNull"):
            return True
    except (AttributeError, TypeError):
        # Ignore type check errors
        pass
    return False


def _to_py_safe(value: Any, *, _depth: int = 0) -> Any:
    """Safely convert a JsProxy value to Python, handling undefined/null.

    Returns None for JavaScript undefined/null or Python None.
    Returns Python primitive for JsProxy primitives.
    Recursively converts dicts and lists.
    Passes through Python values unchanged.

    Args:
        value: The value to convert.
        _depth: Internal recursion depth counter. When _MAX_CONVERSION_DEPTH
            is exceeded the value is returned as-is to prevent unbounded
            recursion (e.g. from pathological JsProxy chains).
    """
    if value is None:
        return None

    # Guard against unbounded recursion
    if _depth >= _MAX_CONVERSION_DEPTH:
        return value

    # Check for undefined BEFORE any other checks
    if _is_js_undefined(value):
        return None

    # If it's already a basic Python type, return it
    if isinstance(value, int | float | str | bool):
        return value

    # Handle JsProxy with to_py() - try multiple approaches
    if HAS_PYODIDE and hasattr(value, "to_py"):
        try:
            converted = value.to_py()
            # to_py() might return a dict with JsProxy values, recurse
            return _to_py_safe(converted, _depth=_depth + 1)
        except (AttributeError, TypeError, ValueError):
            # JsProxy conversion failed, try other approaches
            pass

    # For dicts, recursively convert all values
    if isinstance(value, dict):
        return {k: _to_py_safe(v, _depth=_depth + 1) for k, v in value.items()}

    # For lists, recursively convert all items
    if isinstance(value, list):
        return [_to_py_safe(item, _depth=_depth + 1) for item in value]

    # For tuples (including time.struct_time from feedparser), convert to list
    # This ensures published_parsed can be indexed and converted to datetime
    if isinstance(value, tuple):
        return [_to_py_safe(item, _depth=_depth + 1) for item in value]

    # Try to convert to string as last resort
    try:
        str_val = str(value)
        # Check if it's a number string
        if str_val.isdigit():
            return int(str_val)
        return str_val
    except Exception:
        return None


def _safe_str(value: Any) -> str | None:
    """Convert a value to Python string, handling JsProxy/undefined/null.

    Returns None for JavaScript undefined/null or Python None.
    Returns str for any other value.
    """
    if value is None:
        return None
    if _is_js_undefined(value):
        return None
    # Convert to Python if JsProxy
    py_val = _to_py_safe(value)
    if py_val is None:
        return None
    return str(py_val) if py_val else None


def _extract_form_value(form: Any, key: str) -> str | None:
    """Extract a value from form data, handling both JsProxy (production) and dict (tests).

    In Cloudflare Workers Python (Pyodide), form_data() returns a JavaScript FormData
    object wrapped as JsProxy. The .get() method may return JavaScript undefined for
    missing keys (NOT Python None).
    """
    try:
        value = form.get(key)
        # Check for None and JavaScript undefined
        if value is None or _is_js_undefined(value):
            return None
        # In Pyodide, convert JsProxy to Python
        py_value = _to_py_safe(value)
        if py_value is None:
            return None
        # Handle case where value is already a string or has string conversion
        return str(py_value) if py_value else None
    except Exception:
        return None


def _to_py_list(js_array: Any) -> list[dict[str, Any]]:
    """Convert D1 query results (JsProxy array) to Python list of dicts.

    In Cloudflare Workers Python, D1 .results returns a JavaScript array of objects.
    We need to convert each row to a Python dict for proper dict access.
    """
    if js_array is None:
        return []

    # In test environment, it's already a Python list
    if isinstance(js_array, list):
        return js_array

    # In Pyodide, convert JsProxy array to Python list
    if HAS_PYODIDE and hasattr(js_array, "to_py"):
        return js_array.to_py()

    # Try iteration as fallback
    try:
        return [dict(row) if hasattr(row, "items") else row.to_py() for row in js_array]
    except Exception:
        return list(js_array)


def _to_d1_value(value: Any) -> Any:
    """Convert a Python value to a D1-safe value.

    This is the central conversion point for all D1 bind parameters.
    Handles the Python-to-JavaScript boundary for database operations.

    ALWAYS converts through _to_py_safe() first to ensure no JsProxy
    values slip through, then converts None to JS null for D1.

    IMPORTANT: In Pyodide, Python None becomes JS undefined when passed
    to JavaScript functions, but D1 requires JS null for SQL NULL values.
    """
    # Force convert to Python (catches all JsProxy/undefined)
    py_value = _to_py_safe(value)

    # Convert None to JS null (required by D1 in Pyodide)
    # Python None -> JS undefined (wrong), JS_NULL -> JS null (correct)
    if py_value is None and HAS_PYODIDE:
        return JS_NULL

    return py_value


# =============================================================================
# Safe Wrapper Classes
# =============================================================================


class SafeD1Statement:
    """Wrapper for D1 prepared statement that auto-converts results to Python."""

    def __init__(self, stmt: Any) -> None:
        """Initialize with a D1 prepared statement."""
        self._stmt = stmt

    def bind(self, *args: Any) -> "SafeD1Statement":
        """Bind parameters and return self for chaining.

        All parameters are converted via _to_d1_value() which:
        - Converts None to JS null (required by D1)
        - Catches any leaked JsProxy/undefined (defensive)
        """
        converted = []
        for arg in args:
            converted.append(_to_d1_value(arg))
        self._stmt = self._stmt.bind(*tuple(converted))
        return self

    async def first(self) -> dict[str, Any] | None:
        """Execute and return first result as Python dict."""
        result = await self._stmt.first()
        return _to_py_safe(result)

    async def all(self) -> Any:
        """Execute and return all results with Python list of dicts.

        Returns an object with .results (list[dict]) and .success (bool)
        to match the D1 API that callers expect.
        """
        result = await self._stmt.all()

        # Create result object with attributes (to match D1 API)
        class D1Result:
            def __init__(self, results: list[dict[str, Any]], success: bool) -> None:
                self.results = results
                self.success = success

        return D1Result(
            results=_to_py_list(result.results) if result else [],
            success=getattr(result, "success", True),
        )

    async def run(self) -> Any:
        """Execute statement (for INSERT/UPDATE/DELETE)."""
        return await self._stmt.run()


class SafeD1:
    """Wrapper for D1 database that auto-converts all results to Python."""

    def __init__(self, db: Any) -> None:
        """Initialize with a D1 database binding."""
        self._db = db

    def prepare(self, sql: str) -> SafeD1Statement:
        """Prepare a SQL statement with automatic result conversion."""
        return SafeD1Statement(self._db.prepare(sql))

    async def exec(self, sql: str) -> Any:
        """Execute raw SQL (for multi-statement DDL like schema creation)."""
        return await self._db.exec(sql)


class SafeAI:
    """Wrapper for Workers AI that auto-converts results to Python."""

    def __init__(self, ai: Any) -> None:
        """Initialize with a Workers AI binding."""
        self._ai = ai

    async def run(self, model: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run AI model and return Python dict result."""
        js_inputs = _to_js_value(inputs)
        result = await self._ai.run(model, js_inputs)
        return _to_py_safe(result)


class SafeVectorize:
    """Wrapper for Vectorize index that auto-converts results to Python."""

    def __init__(self, index: Any) -> None:
        """Initialize with a Vectorize index binding."""
        self._index = index

    async def query(self, vector: Any, options: dict[str, Any]) -> dict[str, Any]:
        """Query the index and return Python dict with matches."""
        js_vector = _to_js_value(vector)
        js_options = _to_js_value(options)
        result = await self._index.query(js_vector, js_options)
        py_result = _to_py_safe(result)
        if py_result is None:
            return {"matches": []}
        return py_result

    async def upsert(self, vectors: Any) -> Any:
        """Upsert vectors into the index."""
        js_vectors = _to_js_value(vectors)
        return await self._index.upsert(js_vectors)

    async def deleteByIds(self, ids: list[str]) -> Any:
        """Delete vectors by their IDs."""
        return await self._index.deleteByIds(ids)


class SafeQueue:
    """Wrapper for Queue that ensures Python dicts are sent correctly."""

    def __init__(self, queue: Any) -> None:
        """Initialize with a Queue binding."""
        self._queue = queue

    async def send(self, message: dict[str, Any]) -> Any:
        """Send a message to the queue."""
        return await self._queue.send(message)


class HttpResponse:
    """Normalized HTTP response for boundary layer."""

    def __init__(
        self, status_code: int, text: str, headers: dict[str, str], final_url: str
    ) -> None:
        """Initialize HTTP response with normalized Python values.

        Args:
            status_code: HTTP status code
            text: Response body as string
            headers: Response headers as Python dict
            final_url: Final URL after redirects

        """
        self.status_code = status_code
        self.text = text
        self.headers = headers  # Python dict
        self.final_url = final_url

    def json(self) -> dict:
        """Parse response text as JSON."""
        import json

        return json.loads(self.text)


async def safe_http_fetch(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    data: dict | None = None,
    timeout_seconds: int = _DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> HttpResponse:
    """Boundary-layer HTTP fetch that works in both Pyodide and test environments.

    Returns a normalized HttpResponse with all JavaScript values converted to Python.
    This centralizes all js_fetch/httpx logic so business code doesn't need HAS_PYODIDE.

    Args:
        url: The URL to fetch
        method: HTTP method (GET, POST, etc.)
        headers: Request headers
        data: Form data for POST requests (will be URL-encoded)
        timeout_seconds: Request timeout in seconds

    """
    headers = headers or {}

    if HAS_PYODIDE:
        # Production: Use native Workers fetch
        fetch_options_dict = {"method": method, "headers": headers, "redirect": "follow"}

        # Handle form data for POST
        if data and method.upper() == "POST":
            # URL-encode form data
            body = urlencode(data)
            fetch_options_dict["body"] = body
            if "content-type" not in {k.lower() for k in headers}:
                fetch_options_dict["headers"] = {
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                }

        fetch_options = _to_js_value(fetch_options_dict)
        js_response = await js_fetch(url, fetch_options)

        # Extract all values to Python before returning
        status_code = int(js_response.status)
        final_url = str(js_response.url) if js_response.url else url
        text = await js_response.text()

        # Convert headers to Python dict
        response_headers = {}
        headers_iter = js_response.headers.entries()
        while True:
            entry = headers_iter.next()
            done = entry.done if hasattr(entry, "done") else getattr(entry, "done", True)
            if done:
                break
            pair = entry.value if hasattr(entry, "value") else entry
            key = str(pair[0]).lower()
            value = str(pair[1])
            response_headers[key] = value

        return HttpResponse(status_code, text, response_headers, final_url)
    else:
        # Test environment: Use httpx
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_seconds) as client:
            response = await client.request(method, url, headers=headers, data=data)
            return HttpResponse(
                status_code=response.status_code,
                text=response.text,
                headers=dict(response.headers),
                final_url=str(response.url),
            )


class SafeEnv:
    """Wrapper for Worker environment bindings with automatic JsProxy conversion.

    This is the primary boundary layer between JavaScript and Python.
    All bindings are wrapped to ensure Python code never sees JsProxy objects.
    """

    def __init__(self, env: Any) -> None:
        """Initialize SafeEnv with wrapped bindings.

        Args:
            env: Raw Cloudflare Workers environment object (JsProxy)

        """
        self._env = env
        # Wrap each binding with its safe wrapper
        self.DB = SafeD1(env.DB)
        # AI and SEARCH_INDEX are optional (not present in lite mode)
        ai = getattr(env, "AI", None)
        self.AI = SafeAI(ai) if ai else None
        search_index = getattr(env, "SEARCH_INDEX", None)
        self.SEARCH_INDEX = SafeVectorize(search_index) if search_index else None
        # Queue bindings are optional (not supported in wrangler dev --remote)
        queue = getattr(env, "FEED_QUEUE", None)
        self.FEED_QUEUE = SafeQueue(queue) if queue else None
        dlq = getattr(env, "DEAD_LETTER_QUEUE", None)
        self.DEAD_LETTER_QUEUE = SafeQueue(dlq) if dlq else None

    def __getattr__(self, name: str) -> Any:
        """Pass through other environment variables (strings, etc.)."""
        return getattr(self._env, name)


# =============================================================================
# D1 Row Factory Functions
# =============================================================================


def feed_row_from_js(row: Any) -> dict[str, Any]:
    """Convert a single D1 feed row (JsProxy) to Python dict.

    Ensures all values are proper Python types, not JsProxy objects.
    """
    if row is None:
        return {}
    py_row = _to_py_safe(row)
    if not py_row:
        return {}
    return {
        "id": int(py_row.get("id", 0)),
        "url": _safe_str(py_row.get("url")) or "",
        "title": _safe_str(py_row.get("title")),
        "site_url": _safe_str(py_row.get("site_url")),
        "is_active": int(py_row.get("is_active", 0)),
        "consecutive_failures": int(py_row.get("consecutive_failures", 0)),
        "etag": _safe_str(py_row.get("etag")),
        "last_modified": _safe_str(py_row.get("last_modified")),
        "last_success_at": _safe_str(py_row.get("last_success_at")),
        "last_error_at": _safe_str(py_row.get("last_error_at")),
        "last_error_message": _safe_str(py_row.get("last_error_message")),
        "created_at": _safe_str(py_row.get("created_at")) or "",
        "updated_at": _safe_str(py_row.get("updated_at")) or "",
        # Computed fields from SQL queries (e.g., CASE expressions)
        "is_healthy": py_row.get("is_healthy"),
        # Optional fields from joins
        "author_name": _safe_str(py_row.get("author_name")),
        "author_email": _safe_str(py_row.get("author_email")),
        "last_fetch_at": _safe_str(py_row.get("last_fetch_at")),
        "fetch_error": _safe_str(py_row.get("fetch_error")),
        "fetch_error_count": py_row.get("fetch_error_count"),
    }


def feed_rows_from_d1(results: Any) -> list[dict[str, Any]]:
    """Convert D1 query results to list of feed row dicts.

    Args:
        results: D1 result.results (JsProxy array or Python list)

    Returns:
        List of feed row dicts with all values converted to Python types.
    """
    raw_list = _to_py_list(results)
    return [feed_row_from_js(row) for row in raw_list]


def entry_row_from_js(row: Any) -> dict[str, Any]:
    """Convert a single D1 entry row (JsProxy) to Python dict.

    Ensures all values are proper Python types, not JsProxy objects.
    """
    if row is None:
        return {}
    py_row = _to_py_safe(row)
    if not py_row:
        return {}
    return {
        "id": int(py_row.get("id", 0)),
        "feed_id": int(py_row.get("feed_id", 0)),
        "guid": _safe_str(py_row.get("guid")) or "",
        "url": _safe_str(py_row.get("url")) or "",
        "title": _safe_str(py_row.get("title")) or "",
        "author": _safe_str(py_row.get("author")),
        "content": _safe_str(py_row.get("content")) or "",
        "summary": _safe_str(py_row.get("summary")),
        "published_at": _safe_str(py_row.get("published_at")) or "",
        "created_at": _safe_str(py_row.get("created_at")) or "",
        "first_seen": _safe_str(py_row.get("first_seen")),
        # Joined fields
        "feed_title": _safe_str(py_row.get("feed_title")),
        "feed_site_url": _safe_str(py_row.get("feed_site_url")),
    }


def entry_rows_from_d1(results: Any) -> list[dict[str, Any]]:
    """Convert D1 query results to list of entry row dicts.

    Args:
        results: D1 result.results (JsProxy array or Python list)

    Returns:
        List of entry row dicts with all values converted to Python types.
    """
    raw_list = _to_py_list(results)
    return [entry_row_from_js(row) for row in raw_list]


def admin_row_from_js(row: Any) -> dict[str, Any] | None:
    """Convert a single D1 admin row (JsProxy) to Python dict.

    Returns None if row is None or empty.
    """
    if row is None:
        return None
    py_row = _to_py_safe(row)
    if not py_row:
        return None
    return {
        "id": int(py_row.get("id", 0)),
        "github_username": _safe_str(py_row.get("github_username")) or "",
        "github_id": py_row.get("github_id"),
        "display_name": _safe_str(py_row.get("display_name")) or "",
        "is_active": int(py_row.get("is_active", 0)),
        "last_login_at": _safe_str(py_row.get("last_login_at")),
        "created_at": _safe_str(py_row.get("created_at")) or "",
    }


def audit_row_from_js(row: Any) -> dict[str, Any]:
    """Convert a single D1 audit log row (JsProxy) to Python dict."""
    if row is None:
        return {}
    py_row = _to_py_safe(row)
    if not py_row:
        return {}
    return {
        "id": int(py_row.get("id", 0)),
        "admin_id": int(py_row.get("admin_id", 0)),
        "action": _safe_str(py_row.get("action")) or "",
        "target_type": _safe_str(py_row.get("target_type")),
        "target_id": py_row.get("target_id"),
        "details": _safe_str(py_row.get("details")),
        "created_at": _safe_str(py_row.get("created_at")) or "",
        # Joined fields
        "admin_username": _safe_str(py_row.get("admin_username")),
    }


def audit_rows_from_d1(results: Any) -> list[dict[str, Any]]:
    """Convert D1 query results to list of audit log row dicts."""
    raw_list = _to_py_list(results)
    return [audit_row_from_js(row) for row in raw_list]


# =============================================================================
# Helper Classes for Request/Form Data
# =============================================================================


class SafeHeaders:
    """Safe wrapper for extracting HTTP headers from request objects.

    Handles JsProxy conversion internally so callers get clean Python strings.
    """

    def __init__(self, request: Any) -> None:
        """Initialize with a request object (JsProxy or mock)."""
        self._request = request

    @property
    def user_agent(self) -> str:
        """Get User-Agent header."""
        return _safe_str(self._request.headers.get("user-agent")) or ""

    @property
    def referer(self) -> str:
        """Get Referer header."""
        return _safe_str(self._request.headers.get("referer")) or ""

    @property
    def cookie(self) -> str:
        """Get Cookie header."""
        return _safe_str(self._request.headers.get("Cookie")) or ""

    @property
    def content_type(self) -> str:
        """Get Content-Type header."""
        return _safe_str(self._request.headers.get("content-type")) or ""

    @property
    def accept(self) -> str:
        """Get Accept header."""
        return _safe_str(self._request.headers.get("accept")) or ""

    def get(self, name: str, default: str = "") -> str:
        """Get any header by name."""
        return _safe_str(self._request.headers.get(name)) or default


class SafeFormData:
    """Safe wrapper for form data extraction.

    Handles JsProxy conversion internally so callers get clean Python strings.
    """

    def __init__(self, form: Any) -> None:
        """Initialize with form data (JsProxy FormData or dict)."""
        self._form = form

    def get(self, key: str) -> str | None:
        """Get a form value by key, returns None if missing."""
        return _extract_form_value(self._form, key)

    def get_str(self, key: str, default: str = "") -> str:
        """Get a form value by key, returns default if missing."""
        return _extract_form_value(self._form, key) or default

    def get_int(self, key: str, default: int = 0) -> int:
        """Get a form value as int, returns default if missing or invalid."""
        val = _extract_form_value(self._form, key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default


class SafeFeedInfo:
    """Safe wrapper for feedparser feed info.

    Handles JsProxy conversion for feed metadata from feedparser.
    """

    def __init__(self, feed_info: Any) -> None:
        """Initialize with feedparser's feed dict (may be JsProxy)."""
        self._info = dict(_to_py_safe(feed_info)) if feed_info else {}

    @property
    def title(self) -> str | None:
        """Get feed title."""
        return _safe_str(self._info.get("title"))

    @property
    def link(self) -> str | None:
        """Get feed link/site URL."""
        return _safe_str(self._info.get("link"))

    @property
    def author(self) -> str | None:
        """Get feed author (tries author_detail.name, then author)."""
        author_detail = self._info.get("author_detail")
        if author_detail and isinstance(author_detail, dict):
            name = _safe_str(author_detail.get("name"))
            if name:
                return name
        return _safe_str(self._info.get("author"))

    @property
    def author_email(self) -> str | None:
        """Get feed author email from author_detail."""
        author_detail = self._info.get("author_detail")
        if author_detail and isinstance(author_detail, dict):
            return _safe_str(author_detail.get("email"))
        return None

    def get(self, key: str) -> Any:
        """Get any feed info value."""
        return _to_py_safe(self._info.get(key))


# =============================================================================
# Entry Binding Helper
# =============================================================================


def entry_bind_values(
    feed_id: int,
    guid: Any,
    url: Any,
    title: Any,
    author: Any,
    content: Any,
    summary: Any,
    published_at: Any,
) -> tuple:
    """Create a tuple of D1-safe values for entry INSERT/UPDATE.

    Converts all values through _safe_str to ensure clean Python strings.
    Returns tuple ready for .bind(*entry_bind_values(...)).
    """
    return (
        feed_id,
        _safe_str(guid),
        _safe_str(url),
        _safe_str(title),
        _safe_str(author),
        _safe_str(content),
        _safe_str(summary),
        _safe_str(published_at),
    )


def feed_bind_values(
    title: Any,
    site_url: Any,
    author_name: Any,
    author_email: Any,
    etag: Any,
    last_modified: Any,
    feed_id: int,
) -> tuple:
    """Create a tuple of D1-safe values for feed metadata UPDATE.

    Converts all values through _safe_str to ensure clean Python strings.
    Returns tuple ready for .bind(*feed_bind_values(...)).
    """
    return (
        _safe_str(title),
        _safe_str(site_url),
        _safe_str(author_name),
        _safe_str(author_email),
        _safe_str(etag),
        _safe_str(last_modified),
        feed_id,
    )


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Constants
    "HAS_PYODIDE",
    "JS_NULL",
    # D1 row factories
    "feed_row_from_js",
    "feed_rows_from_d1",
    "entry_row_from_js",
    "entry_rows_from_d1",
    "admin_row_from_js",
    "audit_row_from_js",
    "audit_rows_from_d1",
    # Helper classes
    "SafeHeaders",
    "SafeFormData",
    "SafeFeedInfo",
    # Binding helpers
    "entry_bind_values",
    "feed_bind_values",
    # Wrapper classes
    "SafeD1Statement",
    "SafeD1",
    "SafeAI",
    "SafeVectorize",
    "SafeQueue",
    "HttpResponse",
    "safe_http_fetch",
    "SafeEnv",
]
