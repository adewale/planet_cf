# src/main.py
"""
Planet CF - Feed Aggregator for Cloudflare Python Workers

Main Worker entrypoint handling all triggers:
- scheduled(): Hourly cron to enqueue feed fetches
- queue(): Queue consumer for feed fetching
- fetch(): HTTP request handling (generates content on-demand)
"""

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import feedparser
import httpx
from workers import Response, WorkerEntrypoint

# Pyodide-specific imports (only available in Cloudflare Workers environment)
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

from models import BleachSanitizer
from observability import (
    FeedFetchEvent,
    GenerationEvent,
    PageServeEvent,
    Timer,
    emit_event,
)
from templates import (
    ADMIN_JS,
    STATIC_CSS,
    TEMPLATE_ADMIN_DASHBOARD,
    TEMPLATE_ADMIN_LOGIN,
    TEMPLATE_FEED_ATOM,
    TEMPLATE_FEED_RSS,
    TEMPLATE_FEEDS_OPML,
    TEMPLATE_INDEX,
    TEMPLATE_SEARCH,
    render_template,
)

# =============================================================================
# Configuration
# =============================================================================

FEED_TIMEOUT_SECONDS = 60  # Max wall time per feed
HTTP_TIMEOUT_SECONDS = 30  # HTTP request timeout
# Issue 9.3/9.5: Include contact info for good netizen behavior
USER_AGENT = "PlanetCF/1.0 (+https://planetcf.com; contact@planetcf.com)"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
# Security: Maximum search query length to prevent DoS
MAX_SEARCH_QUERY_LENGTH = 1000

# Retention policy defaults (can be overridden via env vars)
DEFAULT_RETENTION_DAYS = 90  # Default to 90 days
DEFAULT_MAX_ENTRIES_PER_FEED = 100  # Max entries to keep per feed

# HTML sanitizer instance (uses settings from types.py)
_sanitizer = BleachSanitizer()

# Constants for content limits
EMBEDDING_MAX_CONTENT_LENGTH = 2000
SUMMARY_MAX_LENGTH = 500


# =============================================================================
# Form Data Helper (handles JsProxy in production, dict in tests)
# =============================================================================


def _is_js_undefined(value) -> bool:
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


def _safe_str(value) -> str | None:
    """
    Convert a value to Python string, handling JsProxy/undefined/null.

    Returns None for JavaScript undefined/null or Python None.
    Returns str for any other value.
    """
    if value is None:
        return None
    if _is_js_undefined(value):
        return None
    # Convert to Python if JsProxy
    py_val = _to_py_primitive(value)
    if py_val is None:
        return None
    return str(py_val) if py_val else None


def _to_py_primitive(value):
    """
    Force convert a value to a Python primitive type.

    This is more aggressive than to_py() and handles cases where
    JsProxy values are nested or not properly converted.
    """
    if value is None:
        return None

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
            return _to_py_primitive(converted)
        except (AttributeError, TypeError, ValueError):
            # JsProxy conversion failed, try other approaches
            pass

    # For dicts, recursively convert all values
    if isinstance(value, dict):
        return {k: _to_py_primitive(v) for k, v in value.items()}

    # For lists, recursively convert all items
    if isinstance(value, list):
        return [_to_py_primitive(item) for item in value]

    # For tuples (including time.struct_time from feedparser), convert to list
    # This ensures published_parsed can be indexed and converted to datetime
    if isinstance(value, tuple):
        return [_to_py_primitive(item) for item in value]

    # Try to convert to string as last resort
    try:
        str_val = str(value)
        # Check if it's a number string
        if str_val.isdigit():
            return int(str_val)
        return str_val
    except Exception:
        return None


def _to_py_safe(value):
    """
    Safely convert a JsProxy value to Python, handling undefined.

    Returns None for JavaScript undefined/null.
    Returns Python primitive for JsProxy primitives.
    Recursively converts dicts and lists.
    Passes through Python values unchanged.
    """
    return _to_py_primitive(value)


def _extract_form_value(form, key: str) -> str | None:
    """
    Extract a value from form data, handling both JsProxy (production) and dict (tests).

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


def _to_py_list(js_array) -> list[dict]:
    """
    Convert D1 query results (JsProxy array) to Python list of dicts.

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


def _to_d1_value(value):
    """
    Convert a Python value to a D1-safe value.

    This is the central conversion point for all D1 bind parameters.
    Handles the Python-to-JavaScript boundary for database operations.

    ALWAYS converts through _to_py_primitive() first to ensure no JsProxy
    values slip through, then converts None to JS null for D1.

    IMPORTANT: In Pyodide, Python None becomes JS undefined when passed
    to JavaScript functions, but D1 requires JS null for SQL NULL values.
    """
    # Force convert to Python primitive (catches all JsProxy/undefined)
    py_value = _to_py_primitive(value)

    # Convert None to JS null (required by D1 in Pyodide)
    # Python None -> JS undefined (wrong), JS_NULL -> JS null (correct)
    if py_value is None and HAS_PYODIDE:
        return JS_NULL

    return py_value


# Cloud metadata endpoints to block (SSRF protection)
BLOCKED_METADATA_IPS = {
    "169.254.169.254",  # AWS/GCP/Azure metadata
    "100.100.100.200",  # Alibaba Cloud metadata
    "192.0.0.192",  # Oracle Cloud metadata
}


# =============================================================================
# JavaScript/Python Boundary Layer
# =============================================================================
#
# These wrapper classes provide a clean boundary between JavaScript (Pyodide/JsProxy)
# and Python. All JavaScript bindings (D1, AI, Vectorize, Queue) are wrapped to
# automatically convert JsProxy objects to native Python types.
#
# This ensures that application code NEVER sees JsProxy objects - they are
# converted at the boundary layer before reaching business logic.
# =============================================================================


class SafeD1Statement:
    """Wrapper for D1 prepared statement that auto-converts results to Python."""

    def __init__(self, stmt):
        self._stmt = stmt

    def bind(self, *args):
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

    async def first(self) -> dict | None:
        """Execute and return first result as Python dict."""
        result = await self._stmt.first()
        return _to_py_safe(result)

    async def all(self):
        """Execute and return all results with Python list of dicts.

        Returns an object with .results (list[dict]) and .success (bool)
        to match the D1 API that callers expect.
        """
        result = await self._stmt.all()

        # Create result object with attributes (to match D1 API)
        class D1Result:
            def __init__(self, results: list, success: bool):
                self.results = results
                self.success = success

        return D1Result(
            results=_to_py_list(result.results) if result else [],
            success=getattr(result, "success", True),
        )

    async def run(self):
        """Execute statement (for INSERT/UPDATE/DELETE)."""
        return await self._stmt.run()


class SafeD1:
    """Wrapper for D1 database that auto-converts all results to Python."""

    def __init__(self, db):
        self._db = db

    def prepare(self, sql: str) -> SafeD1Statement:
        """Prepare a SQL statement with automatic result conversion."""
        return SafeD1Statement(self._db.prepare(sql))


class SafeAI:
    """Wrapper for Workers AI that auto-converts results to Python."""

    def __init__(self, ai):
        self._ai = ai

    async def run(self, model: str, inputs: dict) -> dict:
        """Run AI model and return Python dict result."""
        result = await self._ai.run(model, inputs)
        return _to_py_safe(result)


class SafeVectorize:
    """Wrapper for Vectorize index that auto-converts results to Python."""

    def __init__(self, index):
        self._index = index

    async def query(self, vector, options: dict) -> dict:
        """Query the index and return Python dict with matches."""
        result = await self._index.query(vector, options)
        # Convert the result and its nested matches
        py_result = _to_py_safe(result)
        if py_result is None:
            return {"matches": []}
        return py_result

    async def upsert(self, vectors):
        """Upsert vectors into the index."""
        return await self._index.upsert(vectors)

    async def deleteByIds(self, ids: list[str]):
        """Delete vectors by their IDs."""
        return await self._index.deleteByIds(ids)


class SafeQueue:
    """Wrapper for Queue that ensures Python dicts are sent correctly."""

    def __init__(self, queue):
        self._queue = queue

    async def send(self, message: dict):
        """Send a message to the queue."""
        return await self._queue.send(message)


class HttpResponse:
    """Normalized HTTP response for boundary layer."""

    def __init__(self, status_code: int, text: str, headers: dict, final_url: str):
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
    timeout_seconds: int = 30,
) -> HttpResponse:
    """
    Boundary-layer HTTP fetch that works in both Pyodide and test environments.

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
            body = "&".join(f"{k}={v}" for k, v in data.items())
            fetch_options_dict["body"] = body
            if "content-type" not in {k.lower() for k in headers}:
                fetch_options_dict["headers"] = {
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                }

        fetch_options = to_js(fetch_options_dict, dict_converter=js.Object.fromEntries)
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
    """
    Wrapper for Worker environment bindings with automatic JsProxy conversion.

    This is the primary boundary layer between JavaScript and Python.
    All bindings are wrapped to ensure Python code never sees JsProxy objects.
    """

    def __init__(self, env):
        self._env = env
        # Wrap each binding with its safe wrapper
        self.DB = SafeD1(env.DB)
        self.AI = SafeAI(env.AI)
        self.SEARCH_INDEX = SafeVectorize(env.SEARCH_INDEX)
        self.FEED_QUEUE = SafeQueue(env.FEED_QUEUE)
        self.DEAD_LETTER_QUEUE = SafeQueue(env.DEAD_LETTER_QUEUE)

    def __getattr__(self, name: str):
        """Pass through other environment variables (strings, etc.)."""
        return getattr(self._env, name)


# =============================================================================
# Structured Logging Helper
# =============================================================================


def log_op(event_type: str, **kwargs) -> None:
    """
    Log an operational event as structured JSON.

    Unlike wide events (FeedFetchEvent, etc.), these are simpler operational
    logs for debugging and monitoring internal operations.
    """
    event = {
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **kwargs,
    }
    print(json.dumps(event))


# =============================================================================
# Response Helpers
# =============================================================================


def html_response(content: str, cache_max_age: int = 3600) -> Response:
    """Create an HTML response with caching and security headers."""
    # Content Security Policy - defense in depth against XSS
    # - default-src 'self': Only allow same-origin resources by default
    # - script-src 'self': Only allow same-origin scripts (blocks inline)
    # - style-src 'self' 'unsafe-inline': Allow inline styles (needed for templates)
    # - img-src https: data:: HTTPS images + data URIs (for inline images)
    # - frame-ancestors 'none': Prevent clickjacking (cannot be framed)
    # - base-uri 'self': Prevent base tag injection attacks
    # - form-action 'self': Forms can only submit to same origin
    csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src https: data:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return Response(
        content,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": f"public, max-age={cache_max_age}, stale-while-revalidate=60",
            "Content-Security-Policy": csp,
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        },
    )


def json_response(data: dict, status: int = 200) -> Response:
    """Create a JSON response."""
    return Response(
        json.dumps(data),
        status=status,
        headers={"Content-Type": "application/json"},
    )


def json_error(message: str, status: int = 400) -> Response:
    """Create a JSON error response."""
    return json_response({"error": message}, status=status)


def redirect_response(location: str) -> Response:
    """Create a redirect response."""
    return Response("", status=302, headers={"Location": location})


def feed_response(content: str, content_type: str, cache_max_age: int = 3600) -> Response:
    """Create a feed response (Atom/RSS/OPML) with caching headers."""
    return Response(
        content,
        headers={
            "Content-Type": f"{content_type}; charset=utf-8",
            "Cache-Control": f"public, max-age={cache_max_age}, stale-while-revalidate=60",
        },
    )


# =============================================================================
# Main Worker Class
# =============================================================================


class Default(WorkerEntrypoint):
    """
    Main Worker entrypoint handling all triggers:
    - scheduled(): Hourly cron to enqueue feed fetches
    - queue(): Queue consumer for feed fetching
    - fetch(): HTTP request handling (generates content on-demand)
    """

    _cached_safe_env = None  # Cached wrapped environment

    @property
    def env(self):
        """
        Override env access to return a SafeEnv-wrapped version.

        This ensures all D1/AI/Vectorize/Queue access goes through our
        boundary layer wrappers that handle JsProxy conversion.
        """
        # Get the actual env from the parent class
        raw_env = super().__getattribute__("_env_from_runtime")
        if self._cached_safe_env is None:
            object.__setattr__(self, "_cached_safe_env", SafeEnv(raw_env))
        return self._cached_safe_env

    @env.setter
    def env(self, value):
        """Store raw env from runtime, will be wrapped on access."""
        object.__setattr__(self, "_env_from_runtime", value)
        object.__setattr__(self, "_cached_safe_env", None)  # Clear cache

    # =========================================================================
    # Cron Handler - Scheduler
    # =========================================================================

    async def scheduled(self, event, env, ctx):
        """
        Hourly cron trigger - enqueue feeds for fetching.
        Content (HTML/RSS/Atom) is generated on-demand by fetch(), not pre-generated.

        Note: env and ctx are passed by the runtime but we use self.env and self.ctx
        which are set up during worker initialization.
        """
        return await self._run_scheduler()

    async def _run_scheduler(self):
        """
        Hourly scheduler - enqueue each active feed as a separate message.

        Each feed gets its own queue message to ensure:
        - Isolated retries (only failed feed is retried)
        - Isolated timeouts (slow feed doesn't block others)
        - Accurate dead-lettering (DLQ shows exactly which feeds fail)
        - Parallel processing (consumers can scale independently)
        """

        # Get all active feeds from D1
        result = await self.env.DB.prepare("""
            SELECT id, url, etag, last_modified
            FROM feeds
            WHERE is_active = 1
        """).all()

        feeds = _to_py_list(result.results)
        enqueue_count = 0

        # Enqueue each feed as a SEPARATE message
        # Do NOT batch multiple feeds into one message
        for feed in feeds:
            message = {
                "feed_id": feed["id"],
                "url": feed["url"],
                "etag": feed.get("etag"),
                "last_modified": feed.get("last_modified"),
                "scheduled_at": datetime.utcnow().isoformat(),
            }

            await self.env.FEED_QUEUE.send(message)
            enqueue_count += 1

        log_op("scheduler_complete", feeds_enqueued=enqueue_count)

        return {"enqueued": enqueue_count}

    # =========================================================================
    # Queue Handler - Feed Fetcher
    # =========================================================================

    async def queue(self, batch, env, ctx):
        """
        Process a batch of feed messages from the queue.

        Each message contains exactly ONE feed to fetch.
        This ensures isolated retries and timeouts per feed.

        Note: Workers Python runtime passes (batch, env, ctx) but we use self.env from __init__.
        """

        log_op("queue_batch_received", batch_size=len(batch.messages))

        for message in batch.messages:
            # CRITICAL: Convert JsProxy message body to Python dict
            feed_job_raw = message.body
            feed_job = _to_py_safe(feed_job_raw)
            if not feed_job or not isinstance(feed_job, dict):
                log_op("queue_message_invalid", body_type=type(feed_job_raw).__name__)
                message.ack()  # Don't retry invalid messages
                continue

            feed_url = feed_job.get("url", "unknown")
            feed_id = feed_job.get("feed_id", 0)

            # Initialize wide event for this feed fetch
            event = FeedFetchEvent(
                feed_id=feed_id,
                feed_url=feed_url,
                queue_message_id=str(getattr(message, "id", "")),
                queue_attempt=getattr(message, "attempts", 1),
            )

            with Timer() as timer:
                try:
                    # Wrap entire feed processing in a timeout
                    # This is WALL TIME, not CPU time - network I/O counts here
                    result = await asyncio.wait_for(
                        self._process_single_feed(feed_job, event), timeout=FEED_TIMEOUT_SECONDS
                    )

                    event.wall_time_ms = timer.elapsed()
                    event.outcome = "success"
                    event.entries_added = result.get("entries_added", 0)
                    event.entries_found = result.get("entries_found", 0)
                    message.ack()

                except TimeoutError:
                    event.wall_time_ms = timer.elapsed()
                    event.outcome = "error"
                    event.error_type = "TimeoutError"
                    event.error_message = f"Timeout after {FEED_TIMEOUT_SECONDS}s"
                    event.error_retriable = True
                    await self._record_feed_error(feed_id, "Timeout")
                    message.retry()

                except Exception as e:
                    event.wall_time_ms = timer.elapsed()
                    event.outcome = "error"
                    event.error_type = type(e).__name__
                    event.error_message = str(e)[:500]
                    event.error_retriable = not isinstance(e, ValueError)
                    await self._record_feed_error(feed_id, str(e))
                    message.retry()

            # Emit wide event (sampling applied)
            emit_event(event)

    async def _process_single_feed(self, job, event: FeedFetchEvent | None = None):
        """
        Fetch, parse, and store a single feed.

        This function should complete within FEED_TIMEOUT_SECONDS.

        Args:
            job: Feed job dict with feed_id, url, etag, last_modified
            event: Optional FeedFetchEvent to populate with details
        """

        feed_id = job["feed_id"]
        url = job["url"]
        etag = job.get("etag")
        last_modified = job.get("last_modified")

        # SSRF protection - validate URL before fetching
        if not self._is_safe_url(url):
            raise ValueError(f"URL failed SSRF validation: {url}")

        # Build conditional request headers (good netizen behavior)
        headers = {"User-Agent": USER_AGENT}
        if etag:
            headers["If-None-Match"] = str(etag)
        if last_modified:
            headers["If-Modified-Since"] = str(last_modified)

        # Fetch using boundary-layer safe_http_fetch
        with Timer() as http_timer:
            http_response = await safe_http_fetch(
                url, headers=headers, timeout_seconds=HTTP_TIMEOUT_SECONDS
            )

        # Extract normalized response data (all values are Python)
        status_code = http_response.status_code
        final_url = http_response.final_url
        response_headers = http_response.headers
        response_text = http_response.text if status_code != 304 else ""
        response_size = len(response_text.encode("utf-8")) if response_text else 0

        # Populate event with HTTP details
        if event:
            event.http_latency_ms = http_timer.elapsed_ms
            event.http_status = status_code
            event.http_cached = status_code == 304
            event.http_redirected = final_url != url
            event.response_size_bytes = response_size
            event.etag_present = bool(response_headers.get("etag"))
            event.last_modified_present = bool(response_headers.get("last-modified"))

        # Re-validate final URL after redirects (SSRF protection)
        if final_url != url and not self._is_safe_url(final_url):
            raise ValueError(f"Redirect target failed SSRF validation: {final_url}")

        # Handle 429/503 with Retry-After (good netizen behavior)
        if status_code in (429, 503):
            retry_after = response_headers.get("retry-after")
            error_msg = f"Rate limited (HTTP {status_code})"
            if retry_after:
                error_msg += f", retry after {retry_after}"
                await self._set_feed_retry_after(feed_id, retry_after)
            raise ValueError(error_msg)

        # Handle 304 Not Modified - feed hasn't changed
        if status_code == 304:
            await self._update_feed_success(feed_id, etag, last_modified)
            return {"status": "not_modified", "entries_added": 0, "entries_found": 0}

        # Handle permanent redirects (301, 308) - update stored URL
        if final_url != url:
            # Note: We can't distinguish redirect types with fetch API
            # Treat any redirect as potentially permanent
            await self._update_feed_url(feed_id, final_url)
            log_op("feed_url_updated", old_url=url, new_url=final_url)

        # Check for HTTP errors
        if status_code >= 400:
            raise ValueError(f"HTTP error {status_code}")

        # Parse feed with feedparser - response_text is now pure Python string
        feed_data = feedparser.parse(response_text)

        if feed_data.bozo and not feed_data.entries:
            raise ValueError(f"Feed parse error: {feed_data.bozo_exception}")

        # Extract cache headers from response (response_headers is Python dict in both paths)
        new_etag = response_headers.get("etag")
        new_last_modified = response_headers.get("last-modified")

        # Update feed metadata
        await self._update_feed_metadata(feed_id, feed_data.feed, new_etag, new_last_modified)

        # Process and store entries (boundary conversion handled by _to_py_list)
        entries_list = _to_py_list(feed_data.entries)

        entries_added = 0
        entries_found = len(entries_list)
        if event:
            event.entries_found = entries_found

        log_op("feed_entries_found", feed_id=feed_id, entries_count=entries_found)

        for entry in entries_list:
            # Ensure entry is Python dict (boundary conversion handled by _to_py_safe)
            py_entry = _to_py_safe(entry)
            if not isinstance(py_entry, dict):
                log_op("entry_not_dict", entry_type=type(py_entry).__name__)
                continue

            entry_id = await self._upsert_entry(feed_id, py_entry)
            if entry_id:
                entries_added += 1
            else:
                entry_title = str(py_entry.get("title", ""))[:50]
                log_op("entry_upsert_failed", feed_id=feed_id, entry_title=entry_title)

        # Mark fetch as successful
        await self._update_feed_success(feed_id, new_etag, new_last_modified)

        log_op("feed_processed", feed_url=url, entries_added=entries_added)
        return {"status": "ok", "entries_added": entries_added, "entries_found": entries_found}

    def _normalize_urls(self, content: str, base_url: str) -> str:
        """
        Convert relative URLs in content to absolute URLs.

        Handles href and src attributes with relative paths like:
        - /images/foo.png -> https://example.com/images/foo.png
        - ../assets/bar.css -> https://example.com/assets/bar.css
        - image.jpg -> https://example.com/path/image.jpg
        """
        parsed_base = urlparse(base_url)
        base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
        base_path = parsed_base.path.rsplit("/", 1)[0] if "/" in parsed_base.path else ""

        def resolve_url(match):
            attr = match.group(1)  # href or src
            quote = match.group(2)  # ' or "
            url = match.group(3)  # the URL value

            # Skip if already absolute or special protocol
            if url.startswith(("http://", "https://", "//", "data:", "mailto:", "#")):
                return match.group(0)

            # Resolve relative URL
            if url.startswith("/"):
                # Absolute path relative to origin
                resolved = f"{base_origin}{url}"
            else:
                # Relative path
                resolved = f"{base_origin}{base_path}/{url}"

            return f"{attr}={quote}{resolved}{quote}"

        # Match href="..." or src="..." with relative URLs
        pattern = r'(href|src)=(["\'])([^"\']+)\2'
        return re.sub(pattern, resolve_url, content, flags=re.I)

    async def _fetch_full_content(self, url: str) -> str | None:
        """
        Fetch full article content from a URL when feed only provides summary.

        Uses regex-based extraction for Pyodide compatibility (no BeautifulSoup).
        Returns None if extraction fails, so caller can fall back to summary.
        """
        if not url or not self._is_safe_url(url):
            return None

        try:
            response = await safe_http_fetch(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout_seconds=HTTP_TIMEOUT_SECONDS,
            )

            if response.status_code != 200:
                return None

            html = response.text

            # Remove script and style tags with their content
            html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
            html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.I)
            html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.I)
            html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.I)

            # Try to extract content from common article containers
            # Order matters - more specific patterns first
            patterns = [
                r"<article[^>]*>(.*?)</article>",
                r"<main[^>]*>(.*?)</main>",
                r'<div[^>]*class="[^"]*(?:post-content|entry-content|article-content)[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*id="content"[^>]*>(.*?)</div>',
            ]

            content = None
            for pattern in patterns:
                match = re.search(pattern, html, flags=re.DOTALL | re.I)
                if match:
                    content = match.group(1)
                    break

            if not content:
                # Fallback: extract all paragraphs
                paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.DOTALL | re.I)
                if len(paragraphs) >= 3:
                    # Join paragraphs into content
                    content = "".join(f"<p>{p}</p>" for p in paragraphs[:50])

            if content and len(content) > 500:
                # Normalize relative URLs to absolute URLs
                content = self._normalize_urls(content, url)
                return content

            return None

        except Exception as e:
            log_op("content_fetch_error", url=url, error=str(e)[:100])
            return None

    async def _upsert_entry(self, feed_id, entry):
        """Insert or update a single entry with sanitized content."""

        # Generate stable GUID - must be non-empty
        guid = entry.get("id") or entry.get("link") or entry.get("title")
        # Ensure GUID is valid (not empty, whitespace-only, or None)
        if not guid or not str(guid).strip():
            # Generate hash-based GUID as fallback
            content_hash = hashlib.sha256(
                f"{feed_id}:{entry.get('title', '')}:{entry.get('link', '')}".encode()
            ).hexdigest()[:16]
            guid = f"generated:{content_hash}"

        # Extract content (prefer full content over summary)
        # Note: After JsProxy conversion, entry is a plain dict, so use .get() not hasattr()
        content = ""
        entry_content = entry.get("content")
        if entry_content and isinstance(entry_content, list) and len(entry_content) > 0:
            first_content = entry_content[0]
            if isinstance(first_content, dict):
                content = first_content.get("value", "")
            else:
                content = str(first_content)
        elif entry.get("summary"):
            content = entry.get("summary", "")

        # If content is just a short summary, try to fetch full article content
        # This handles feeds that only provide <description> without <content:encoded>
        entry_url = entry.get("link")
        if len(content) < 500 and entry_url:
            fetched_content = await self._fetch_full_content(entry_url)
            if fetched_content:
                content = fetched_content
                log_op(
                    "full_content_fetched",
                    url=entry_url[:100],
                    content_len=len(content),
                )

        # Sanitize HTML (XSS prevention)
        sanitized_content = self._sanitize_html(content)

        # Parse published date - use None if missing (don't fake current time)
        # This ensures retention policy can correctly identify old entries
        # Note: After JsProxy conversion, entry is a plain dict, so use .get() not hasattr()
        published_at = None
        pub_parsed = entry.get("published_parsed")
        upd_parsed = entry.get("updated_parsed")
        if pub_parsed and isinstance(pub_parsed, list | tuple) and len(pub_parsed) >= 6:
            published_at = datetime(*pub_parsed[:6]).isoformat()
        elif upd_parsed and isinstance(upd_parsed, list | tuple) and len(upd_parsed) >= 6:
            published_at = datetime(*upd_parsed[:6]).isoformat()
        # If no date available, leave as None (will use CURRENT_TIMESTAMP in DB)

        title = entry.get("title", "")

        # Truncate summary with indicator
        raw_summary = entry.get("summary") or ""
        if len(raw_summary) > SUMMARY_MAX_LENGTH:
            summary = raw_summary[: SUMMARY_MAX_LENGTH - 3] + "..."
        else:
            summary = raw_summary

        # Upsert to D1 - use _safe_str to convert any JsProxy/undefined to Python
        # first_seen is set on INSERT only - preserved on UPDATE to prevent spam attacks
        # where feeds retroactively add old entries that would appear as new
        result_raw = (
            await self.env.DB.prepare("""
            INSERT INTO entries (
                feed_id, guid, url, title, author, content, summary,
                published_at, first_seen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
            ON CONFLICT(feed_id, guid) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """)
            .bind(
                feed_id,
                _safe_str(guid),
                _safe_str(entry.get("link")),
                _safe_str(title),
                _safe_str(entry.get("author")),
                _safe_str(sanitized_content),
                _safe_str(summary),
                _safe_str(published_at),
            )
            .first()
        )

        # Convert JsProxy to Python dict
        result = _to_py_safe(result_raw)
        entry_id = result.get("id") if result else None

        # Index for semantic search (may fail in local dev - Vectorize not supported)
        if entry_id and title:
            try:
                await self._index_entry_for_search(entry_id, title, sanitized_content)
            except Exception as e:
                # Log but don't fail - entry is still usable without search
                log_op(
                    "search_index_skipped",
                    entry_id=entry_id,
                    error_type=type(e).__name__,
                    error=str(e)[:100],
                )

        return entry_id

    async def _index_entry_for_search(self, entry_id, title, content):
        """Generate embedding and store in Vectorize for semantic search."""

        # Combine title and content for embedding (truncate to model limit)
        text = f"{title}\n\n{content[:EMBEDDING_MAX_CONTENT_LENGTH]}"

        # Generate embedding using Workers AI with cls pooling for accuracy
        # Note: SafeAI.run() already converts result to Python dict
        embedding_result = await self.env.AI.run(
            "@cf/baai/bge-base-en-v1.5", {"text": [text], "pooling": "cls"}
        )
        if not embedding_result or "data" not in embedding_result:
            log_op("embedding_failed", entry_id=entry_id, reason="no_data_in_result")
            return

        vector = embedding_result["data"][0]

        # Upsert to Vectorize with entry_id as the vector ID
        await self.env.SEARCH_INDEX.upsert(
            [
                {
                    "id": str(entry_id),
                    "values": vector,
                    "metadata": {"title": title[:200], "entry_id": entry_id},
                }
            ]
        )

    def _sanitize_html(self, html_content):
        """Sanitize HTML to prevent XSS attacks (CVE-2009-2937 mitigation)."""
        return _sanitizer.clean(html_content)

    def _is_safe_url(self, url):
        """SSRF protection - reject internal/private URLs."""

        try:
            parsed = urlparse(url)
        except Exception as e:
            log_op("url_parse_error", url=url, error_type=type(e).__name__, error=str(e))
            return False

        # Only allow http/https
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname.lower() if parsed.hostname else ""

        if not hostname:
            return False

        # Block localhost variants
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False

        # Block cloud metadata endpoints
        if hostname in BLOCKED_METADATA_IPS:
            return False

        # Block private IP ranges
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
            # Block IPv6 unique local addresses (fc00::/7, which includes fd00::/8)
            # Check first byte: 0xFC or 0xFD (binary: 1111110x)
            if ip.version == 6 and (ip.packed[0] & 0xFE) == 0xFC:
                return False
        except ValueError:
            pass  # Not an IP address

        # Block internal domain patterns
        if hostname.endswith(".internal") or hostname.endswith(".local"):
            return False

        # Block cloud metadata hostnames
        metadata_hosts = [
            "metadata.google.internal",
            "metadata.azure.internal",
            "instance-data",
        ]
        return not any(hostname == h or hostname.endswith("." + h) for h in metadata_hosts)

    async def _update_feed_success(self, feed_id, etag, last_modified):
        """Mark feed fetch as successful."""
        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                last_fetch_at = CURRENT_TIMESTAMP,
                last_success_at = CURRENT_TIMESTAMP,
                etag = ?,
                last_modified = ?,
                fetch_error = NULL,
                consecutive_failures = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(_safe_str(etag), _safe_str(last_modified), feed_id)
            .run()
        )

    async def _record_feed_error(self, feed_id, error_message):
        """Record a feed fetch error and auto-deactivate after too many failures."""
        # Issue 9.4: Auto-deactivate feeds after 10+ consecutive failures
        result_raw = await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                last_fetch_at = CURRENT_TIMESTAMP,
                fetch_error = ?,
                fetch_error_count = fetch_error_count + 1,
                consecutive_failures = consecutive_failures + 1,
                is_active = CASE WHEN consecutive_failures >= 10 THEN 0 ELSE is_active END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING consecutive_failures, is_active
        """)
            .bind(error_message[:500], feed_id)
            .first()
        )
        # Convert JsProxy to Python dict
        result = _to_py_safe(result_raw)
        if result and result.get("is_active") == 0:
            log_op(
                "feed_auto_deactivated",
                feed_id=feed_id,
                consecutive_failures=result.get("consecutive_failures"),
                reason="Too many consecutive failures",
            )

    async def _update_feed_url(self, feed_id, new_url):
        """Update feed URL after permanent redirect."""
        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                url = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(new_url, feed_id)
            .run()
        )

    async def _set_feed_retry_after(self, feed_id, retry_after: str):
        """
        Store Retry-After time for a feed (good netizen behavior).

        The retry_after value can be:
        - A number of seconds (e.g., "3600")
        - An HTTP date (e.g., "Wed, 21 Oct 2015 07:28:00 GMT")
        """
        # Parse retry_after - could be seconds or HTTP date
        try:
            seconds = int(retry_after)
            retry_until = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat() + "Z"
        except ValueError:
            # Assume it's an HTTP date, store as-is for simplicity
            retry_until = retry_after

        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                fetch_error = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(f"Rate limited until {retry_until}", feed_id)
            .run()
        )

    async def _update_feed_metadata(self, feed_id, feed_info, etag, last_modified):
        """Update feed title and other metadata from feed content."""
        # Convert feedparser's FeedParserDict to plain Python dict (boundary-safe)
        safe_info = dict(_to_py_safe(feed_info)) if feed_info else {}

        title = _safe_str(safe_info.get("title"))
        site_url = _safe_str(safe_info.get("link"))

        # Issue 1.1: Extract author info from feed
        author_name = None
        author_email = None
        author_detail = safe_info.get("author_detail")
        if author_detail and isinstance(author_detail, dict):
            author_name = _safe_str(author_detail.get("name"))
            author_email = _safe_str(author_detail.get("email"))
        elif safe_info.get("author"):
            author_name = _safe_str(safe_info.get("author"))

        await (
            self.env.DB.prepare("""
            UPDATE feeds SET
                title = COALESCE(?, title),
                site_url = COALESCE(?, site_url),
                author_name = COALESCE(?, author_name),
                author_email = COALESCE(?, author_email),
                etag = ?,
                last_modified = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """)
            .bind(
                title,
                site_url,
                author_name,
                author_email,
                _safe_str(etag),
                _safe_str(last_modified),
                feed_id,
            )
            .run()
        )

    # =========================================================================
    # HTTP Handler
    # =========================================================================

    async def fetch(self, request, env=None, ctx=None):
        """Handle HTTP requests."""

        # Initialize page serve event
        url = request.url
        path = (
            url.pathname
            if hasattr(url, "pathname")
            else url.split("?")[0].split("://", 1)[-1].split("/", 1)[-1]
        )
        if not path.startswith("/"):
            path = "/" + path

        # Safely extract request headers (may be JsProxy in Pyodide)
        user_agent = _safe_str(request.headers.get("user-agent")) or ""
        referer = _safe_str(request.headers.get("referer")) or ""

        event = PageServeEvent(
            method=request.method,
            path=path,
            user_agent=user_agent[:200],
            referer=referer[:200],
            country=getattr(request.cf, "country", None) if hasattr(request, "cf") else None,
            colo=getattr(request.cf, "colo", None) if hasattr(request, "cf") else None,
        )

        with Timer() as timer:
            try:
                # Public routes
                if path == "/" or path == "/index.html":
                    response = await self._serve_html()
                    event.content_type = "html"

                elif path == "/feed.atom":
                    response = await self._serve_atom()
                    event.content_type = "atom"

                elif path == "/feed.rss":
                    response = await self._serve_rss()
                    event.content_type = "rss"

                elif path == "/feeds.opml":
                    response = await self._export_opml()
                    event.content_type = "opml"

                elif path == "/search":
                    response = await self._search_entries(request)
                    event.content_type = "search"

                elif path.startswith("/static/"):
                    response = await self._serve_static(path)
                    event.content_type = "static"

                # OAuth routes
                elif path == "/auth/github":
                    response = self._redirect_to_github_oauth(request)
                    event.content_type = "auth"

                elif path == "/auth/github/callback":
                    response = await self._handle_github_callback(request)
                    event.content_type = "auth"

                # Admin routes (show login page if not authenticated)
                elif path.startswith("/admin"):
                    response = await self._handle_admin(request, path)
                    event.content_type = "admin"

                else:
                    response = Response("Not Found", status=404)
                    event.content_type = "error"

            except Exception as e:
                log_op("request_error", path=path, error_type=type(e).__name__, error=str(e)[:200])
                event.wall_time_ms = timer.elapsed()
                event.status_code = 500
                emit_event(event)
                raise

        # Finalize and emit event
        event.wall_time_ms = timer.elapsed()
        event.status_code = response.status
        # Issue 10.3: Set response size if available (skip if JsProxy)
        try:
            if hasattr(response, "body") and response.body:
                body = response.body
                if isinstance(body, str):
                    event.response_size_bytes = len(body.encode("utf-8"))
                elif isinstance(body, bytes):
                    event.response_size_bytes = len(body)
                # Skip JsProxy or other non-standard types
        except (TypeError, AttributeError):
            pass  # Size calculation failed (JsProxy or other non-standard type)
        emit_event(event)

        return response

    async def _serve_html(self):
        """
        Generate and serve the HTML page on-demand.

        No KV caching - edge cache handles repeat requests:
        - First request: D1 query + Jinja2 render (~300-500ms)
        - Edge caches response for 1 hour
        - Subsequent requests: 0ms (served from edge)

        For a planet aggregator with ~10-20 cache misses/hour globally,
        this latency is acceptable and eliminates KV complexity.
        """
        html = await self._generate_html()
        return html_response(html)

    async def _generate_html(self, trigger: str = "http", triggered_by: str | None = None):
        """
        Generate the aggregated HTML page on-demand.
        Called by fetch() for / requests. Edge cache handles caching.

        Args:
            trigger: What triggered generation ("http", "cron", "admin_manual")
            triggered_by: Admin username if manually triggered
        """

        # Initialize generation event
        event = GenerationEvent(trigger=trigger, triggered_by=triggered_by)

        try:
            with Timer() as total_timer:
                # Get planet config from environment
                planet = self._get_planet_config()

                # Apply retention policy first (delete old entries and their vectors)
                await self._apply_retention_policy()

                # Query entries using configurable retention period
                # Uses first_seen for ordering/grouping to prevent spam from retroactive entries
                # Per-feed-per-day limit prevents any single feed from dominating when added
                retention_days = self._get_retention_days()
                max_per_feed = self._get_max_entries_per_feed()

                with Timer() as d1_timer:
                    # Query entries, grouping by published_at (actual publication date)
                    # Fall back to first_seen only when published_at is missing
                    entries_result = await self.env.DB.prepare(
                        f"""
                        WITH ranked AS (
                            SELECT
                                e.*,
                                f.title as feed_title,
                                f.site_url as feed_site_url,
                                ROW_NUMBER() OVER (
                                    PARTITION BY e.feed_id,
                                        date(COALESCE(e.published_at, e.first_seen))
                                    ORDER BY COALESCE(e.published_at, e.first_seen) DESC
                                ) as rn_per_day,
                                ROW_NUMBER() OVER (
                                    PARTITION BY e.feed_id
                                    ORDER BY COALESCE(e.published_at, e.first_seen) DESC
                                ) as rn_total
                            FROM entries e
                            JOIN feeds f ON e.feed_id = f.id
                            WHERE COALESCE(e.published_at, e.first_seen)
                                >= datetime('now', '-{retention_days} days')
                            AND f.is_active = 1
                        )
                        SELECT * FROM ranked
                        WHERE rn_per_day <= 5 AND rn_total <= {max_per_feed}
                        ORDER BY COALESCE(published_at, first_seen) DESC
                        LIMIT 500
                        """
                    ).all()

                    # Get feeds for sidebar
                    feeds_result = await self.env.DB.prepare("""
                        SELECT
                            id, title, site_url, last_success_at,
                            CASE WHEN consecutive_failures < 3 THEN 1 ELSE 0 END as is_healthy
                        FROM feeds
                        WHERE is_active = 1
                        ORDER BY title
                    """).all()

                event.d1_query_time_ms = d1_timer.elapsed_ms

                # Convert JsProxy results to Python lists for dict access
                entries = _to_py_list(entries_result.results)
                feeds = _to_py_list(feeds_result.results)

                # Group entries by published_at (actual publication date from feed)
                # Fall back to first_seen only if published_at is missing
                # This ensures entries appear under their true publication date
                entries_by_date = {}
                for entry in entries:
                    # Prefer published_at for accurate grouping, fall back to first_seen
                    group_date = entry.get("published_at") or entry.get("first_seen") or ""
                    date_str = group_date[:10] if group_date else "Unknown"  # YYYY-MM-DD

                    # Convert to absolute date label (e.g., "January 15, 2026")
                    date_label = self._format_date_label(date_str)
                    if date_label not in entries_by_date:
                        entries_by_date[date_label] = []

                    # Add display date (same as group date for consistency)
                    if date_str and date_str != "Unknown":
                        entry["published_at_display"] = self._format_pub_date(group_date)
                    else:
                        entry["published_at_display"] = ""
                    entries_by_date[date_label].append(entry)

                # Sort entries within each day by published_at (newest first)
                for date_label in entries_by_date:
                    entries_by_date[date_label].sort(
                        key=lambda e: e.get("published_at") or "", reverse=True
                    )

                # Sort date groups by date (most recent first)
                # Extract YYYY-MM-DD from entries to sort properly
                def get_sort_date(date_label_and_entries):
                    entries_list = date_label_and_entries[1]
                    if entries_list:
                        return entries_list[0].get("published_at") or ""
                    return ""

                entries_by_date = dict(
                    sorted(entries_by_date.items(), key=get_sort_date, reverse=True)
                )

                for feed in feeds:
                    feed["last_success_at_relative"] = self._relative_time(feed["last_success_at"])

                # Render template - track template time
                with Timer() as render_timer:
                    html = render_template(
                        TEMPLATE_INDEX,
                        planet=planet,
                        entries_by_date=entries_by_date,
                        feeds=feeds,
                        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                    )

                event.template_render_time_ms = render_timer.elapsed_ms

            # Populate and emit event on success
            event.wall_time_ms = total_timer.elapsed_ms
            event.entries_total = len(entries)
            event.feeds_active = len(feeds)
            event.feeds_healthy = sum(1 for f in feeds if f.get("is_healthy"))
            event.html_size_bytes = len(html.encode("utf-8"))
            emit_event(event)

            return html

        except Exception as e:
            # Issue 4.4: Mark event as error and emit before re-raising
            event.outcome = "error"
            event.error_type = type(e).__name__
            event.error_message = str(e)[:200]
            emit_event(event, force=True)  # Always emit errors
            raise

    async def _apply_retention_policy(self):
        """Delete old entries and clean up vectors based on configurable retention policy."""

        retention_days = self._get_retention_days()
        max_per_feed = self._get_max_entries_per_feed()

        # Get IDs of entries to delete
        to_delete = await self.env.DB.prepare(f"""
            WITH ranked_entries AS (
                SELECT
                    id,
                    feed_id,
                    published_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY feed_id
                        ORDER BY published_at DESC
                    ) as rn
                FROM entries
            ),
            entries_to_delete AS (
                SELECT id FROM ranked_entries
                WHERE rn > {max_per_feed}
                OR published_at < datetime('now', '-{retention_days} days')
            )
            SELECT id FROM entries_to_delete
        """).all()

        deleted_ids = [row["id"] for row in _to_py_list(to_delete.results)]

        if deleted_ids:
            # Delete vectors from Vectorize (Issue 11.2: handle errors gracefully)
            try:
                await self.env.SEARCH_INDEX.deleteByIds([str(id) for id in deleted_ids])
            except Exception as e:
                log_op(
                    "vectorize_delete_error",
                    error_type=type(e).__name__,
                    error_message=str(e)[:200],
                    ids_count=len(deleted_ids),
                )
                # Continue with D1 deletion even if vector cleanup fails

            # Delete entries from D1 (in batches to stay under parameter limit)
            for i in range(0, len(deleted_ids), 50):
                batch = deleted_ids[i : i + 50]
                placeholders = ",".join("?" * len(batch))
                await (
                    self.env.DB.prepare(f"""
                    DELETE FROM entries WHERE id IN ({placeholders})
                """)
                    .bind(*batch)
                    .run()
                )

            log_op("retention_cleanup", entries_deleted=len(deleted_ids))

    def _format_datetime(self, iso_string: str | None) -> str:
        """Format ISO datetime string for display."""
        if not iso_string:
            return ""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            return dt.strftime("%B %d, %Y at %I:%M %p")
        except (ValueError, AttributeError):
            return iso_string

    def _format_pub_date(self, iso_string: str | None) -> str:
        """Format publication date concisely (e.g., 'Jun 2013' or 'Jan 15')."""
        if not iso_string:
            return ""
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            now = datetime.utcnow()
            # If same year, show "Mon Day" (e.g., "Jun 15")
            if dt.year == now.year:
                return dt.strftime("%b %d")
            # Otherwise show "Mon Year" (e.g., "Jun 2013")
            return dt.strftime("%b %Y")
        except (ValueError, AttributeError):
            return ""

    def _relative_time(self, iso_string: str | None) -> str:
        """Convert ISO datetime to relative time (e.g., '2 hours ago')."""
        if not iso_string:
            return "never"
        try:
            dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            now = datetime.utcnow()
            delta = now - dt.replace(tzinfo=None)

            if delta.days > 30:
                return f"{delta.days // 30} months ago"
            elif delta.days > 0:
                return f"{delta.days} days ago"
            elif delta.seconds > 3600:
                return f"{delta.seconds // 3600} hours ago"
            elif delta.seconds > 60:
                return f"{delta.seconds // 60} minutes ago"
            else:
                return "just now"
        except (ValueError, AttributeError):
            return "unknown"

    def _format_date_label(self, date_str: str) -> str:
        """
        Convert YYYY-MM-DD to absolute date like 'August 25, 2025'.

        Always shows the actual date rather than relative labels like 'Today'.
        This is clearer when there are gaps between posts.
        """
        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            # Format as "August 25, 2025"
            return entry_date.strftime("%B %d, %Y")
        except (ValueError, AttributeError):
            return date_str

    async def _serve_atom(self):
        """Generate and serve Atom feed on-demand."""
        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        atom = self._generate_atom_feed(planet, entries)
        return feed_response(atom, "application/atom+xml")

    async def _serve_rss(self):
        """Generate and serve RSS feed on-demand."""
        entries = await self._get_recent_entries(50)
        planet = self._get_planet_config()
        rss = self._generate_rss_feed(planet, entries)
        return feed_response(rss, "application/rss+xml")

    async def _get_recent_entries(self, limit):
        """Query recent entries for feeds."""

        result = (
            await self.env.DB.prepare("""
            SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            WHERE f.is_active = 1
            ORDER BY e.published_at DESC
            LIMIT ?
        """)
            .bind(limit)
            .all()
        )

        return _to_py_list(result.results)

    def _get_planet_config(self) -> dict[str, str]:
        """Get planet configuration from environment."""
        return {
            "name": getattr(self.env, "PLANET_NAME", None) or "Planet CF",
            "description": getattr(self.env, "PLANET_DESCRIPTION", None)
            or "Aggregated posts from Cloudflare employees and community",
            "link": getattr(self.env, "PLANET_URL", None) or "https://planetcf.com",
        }

    def _get_retention_days(self) -> int:
        """Get retention days from environment, default 90."""
        try:
            days = getattr(self.env, "RETENTION_DAYS", None)
            return int(days) if days else DEFAULT_RETENTION_DAYS
        except (ValueError, TypeError):
            return DEFAULT_RETENTION_DAYS

    def _get_max_entries_per_feed(self) -> int:
        """Get max entries per feed from environment, default 100."""
        try:
            max_entries = getattr(self.env, "RETENTION_MAX_ENTRIES_PER_FEED", None)
            return int(max_entries) if max_entries else DEFAULT_MAX_ENTRIES_PER_FEED
        except (ValueError, TypeError):
            return DEFAULT_MAX_ENTRIES_PER_FEED

    def _generate_atom_feed(self, planet, entries):
        """Generate Atom 1.0 feed XML using template."""
        # Prepare entries with defaults for template
        template_entries = [
            {
                "title": e.get("title", ""),
                "url": e.get("url", ""),
                "guid": e.get("guid", e.get("url", "")),
                "published_at": e.get("published_at", ""),
                "author": e.get("author", e.get("feed_title", "")),
                "content": e.get("content", ""),
            }
            for e in entries
        ]
        return render_template(
            TEMPLATE_FEED_ATOM,
            planet=planet,
            entries=template_entries,
            updated_at=f"{datetime.utcnow().isoformat()}Z",
        )

    def _generate_rss_feed(self, planet, entries):
        """Generate RSS 2.0 feed XML using template."""
        # Prepare entries with CDATA-safe content
        template_entries = [
            {
                "title": e.get("title", ""),
                "url": e.get("url", ""),
                "guid": e.get("guid", e.get("url", "")),
                "published_at": e.get("published_at", ""),
                "author": e.get("author", ""),
                # Escape ]]> in CDATA to prevent breakout attacks (Issue 2.1)
                "content_cdata": e.get("content", "").replace("]]>", "]]]]><![CDATA[>"),
            }
            for e in entries
        ]
        return render_template(
            TEMPLATE_FEED_RSS,
            planet=planet,
            entries=template_entries,
            last_build_date=datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000"),
        )

    async def _export_opml(self):
        """Export all active feeds as OPML using template."""
        feeds_result = await self.env.DB.prepare("""
            SELECT url, title, site_url
            FROM feeds
            WHERE is_active = 1
            ORDER BY title
        """).all()

        # Prepare feed data for template
        template_feeds = [
            {
                "title": f["title"] or f["url"],
                "url": f["url"],
                "site_url": f["site_url"] or "",
            }
            for f in _to_py_list(feeds_result.results)
        ]

        planet = self._get_planet_config()
        owner_name = getattr(self.env, "PLANET_OWNER_NAME", "Planet CF")

        opml = render_template(
            TEMPLATE_FEEDS_OPML,
            planet=planet,
            feeds=template_feeds,
            owner_name=owner_name,
            date_created=datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000"),
        )

        return Response(
            opml,
            headers={
                "Content-Type": "application/xml; charset=utf-8",
                "Content-Disposition": 'attachment; filename="planetcf-feeds.opml"',
            },
        )

    async def _search_entries(self, request):
        """Search entries by semantic similarity."""

        # Parse query string
        url_str = str(request.url)
        query = ""
        if "?" in url_str:
            qs = parse_qs(url_str.split("?", 1)[1])
            query = qs.get("q", [""])[0]

        if not query or len(query) < 2:
            return json_error("Query too short")
        if len(query) > MAX_SEARCH_QUERY_LENGTH:
            return json_error("Query too long (max 1000 characters)")

        # Generate embedding for search query
        # Note: SafeAI.run() already converts result to Python dict
        embedding_result = await self.env.AI.run(
            "@cf/baai/bge-base-en-v1.5", {"text": [query], "pooling": "cls"}
        )
        if not embedding_result or "data" not in embedding_result:
            return json_error("Failed to generate embedding")
        query_vector = embedding_result["data"][0]

        # Search Vectorize
        # Note: SafeVectorize.query() already converts result to Python dict
        results = await self.env.SEARCH_INDEX.query(
            query_vector, {"topK": 20, "returnMetadata": True}
        )
        matches = results.get("matches", []) if results else []

        # Fetch full entries from D1
        if not matches:
            # Return HTML search page with no results
            planet = self._get_planet_config()
            html = render_template(TEMPLATE_SEARCH, planet=planet, query=query, results=[])
            return html_response(html, cache_max_age=0)

        entry_ids = [int(m["id"]) for m in matches]
        placeholders = ",".join("?" * len(entry_ids))

        entries = (
            await self.env.DB.prepare(f"""
            SELECT e.*, f.title as feed_title, f.site_url as feed_site_url
            FROM entries e
            JOIN feeds f ON e.feed_id = f.id
            WHERE e.id IN ({placeholders})
        """)
            .bind(*entry_ids)
            .all()
        )

        # Sort by Vectorize score
        entry_map = {e["id"]: e for e in _to_py_list(entries.results)}
        sorted_results = [
            {**entry_map[int(m["id"])], "score": m.get("score", 0)}
            for m in matches
            if int(m["id"]) in entry_map
        ]

        # Return HTML search results page
        planet = self._get_planet_config()
        html = render_template(TEMPLATE_SEARCH, planet=planet, query=query, results=sorted_results)
        return html_response(html, cache_max_age=0)

    async def _serve_static(self, path):
        """Serve static files."""
        # In production, static files would be served via assets binding
        # For now, serve CSS and JS inline
        if path == "/static/style.css":
            css = self._get_default_css()
            return Response(
                css,
                headers={
                    "Content-Type": "text/css",
                    "Cache-Control": "public, max-age=86400",
                },
            )
        if path == "/static/admin.js":
            js = self._get_admin_js()
            return Response(
                js,
                headers={
                    "Content-Type": "application/javascript",
                    "Cache-Control": "public, max-age=86400",
                },
            )
        return Response("Not Found", status=404)

    def _get_default_css(self) -> str:
        """Return default CSS styling from templates module."""
        return STATIC_CSS

    def _get_admin_js(self) -> str:
        """Return admin dashboard JavaScript from templates module."""
        return ADMIN_JS

    # =========================================================================
    # Admin Routes
    # =========================================================================

    async def _handle_admin(self, request, path):
        """Handle admin routes with GitHub OAuth."""

        # Verify signed session cookie (stateless, no KV)
        session = self._verify_signed_cookie(request)
        if not session:
            # Show login page instead of auto-redirecting
            return self._serve_admin_login()

        # Verify user is still an authorized admin (may have been revoked)
        admin_result = (
            await self.env.DB.prepare(
                "SELECT * FROM admins WHERE github_username = ? AND is_active = 1"
            )
            .bind(session["github_username"])
            .first()
        )

        # Convert JsProxy to Python dict
        admin = _to_py_safe(admin_result)

        if not admin:
            return Response("Unauthorized: Not an admin", status=403)

        # Ensure admin_id is a Python int (D1 requires Python primitives)
        if "id" in admin:
            admin["id"] = int(admin["id"]) if admin["id"] is not None else None

        # Route admin requests
        method = request.method

        if path == "/admin" or path == "/admin/":
            return await self._serve_admin_dashboard(admin)

        if path == "/admin/feeds" and method == "GET":
            return await self._list_feeds()

        if path == "/admin/feeds" and method == "POST":
            return await self._add_feed(request, admin)

        if path.startswith("/admin/feeds/") and method == "DELETE":
            feed_id = path.split("/")[-1]
            return await self._remove_feed(feed_id, admin)

        if path.startswith("/admin/feeds/") and method == "PUT":
            feed_id = path.split("/")[-1]
            return await self._update_feed(request, feed_id, admin)

        if path.startswith("/admin/feeds/") and method == "POST":
            # Handle form override for DELETE
            form = await request.form_data()
            if _extract_form_value(form, "_method") == "DELETE":
                feed_id = path.split("/")[-1]
                return await self._remove_feed(feed_id, admin)
            return Response("Method not allowed", status=405)

        if path == "/admin/import-opml" and method == "POST":
            return await self._import_opml(request, admin)

        if path == "/admin/regenerate" and method == "POST":
            return await self._trigger_regenerate(admin)

        if path == "/admin/dlq" and method == "GET":
            return await self._view_dlq()

        if path.startswith("/admin/dlq/") and path.endswith("/retry") and method == "POST":
            # Extract feed_id from /admin/dlq/{id}/retry
            parts = path.split("/")
            if len(parts) >= 4:
                feed_id = parts[3]
                return await self._retry_dlq_feed(feed_id, admin)
            return Response("Invalid path", status=400)

        if path == "/admin/audit" and method == "GET":
            return await self._view_audit_log()

        if path == "/admin/logout" and method == "POST":
            return self._logout(request)

        return Response("Not Found", status=404)

    def _serve_admin_login(self):
        """Serve the admin login page."""
        planet = self._get_planet_config()
        html = render_template(TEMPLATE_ADMIN_LOGIN, planet=planet)
        return html_response(html, cache_max_age=0)

    async def _serve_admin_dashboard(self, admin):
        """Serve the admin dashboard."""
        feeds_result = await self.env.DB.prepare("""
            SELECT * FROM feeds ORDER BY title
        """).all()

        planet = self._get_planet_config()
        html = render_template(
            TEMPLATE_ADMIN_DASHBOARD,
            planet=planet,
            admin=admin,
            feeds=_to_py_list(feeds_result.results),
        )
        return html_response(html, cache_max_age=0)

    async def _list_feeds(self):
        """List all feeds as JSON."""
        result = await self.env.DB.prepare("""
            SELECT * FROM feeds ORDER BY title
        """).all()
        return json_response({"feeds": _to_py_list(result.results)})

    async def _validate_feed_url(self, url: str) -> dict:
        """
        Validate a feed URL by fetching and parsing it.

        Returns dict with:
        - valid: bool
        - title: str or None (extracted from feed)
        - site_url: str or None
        - entry_count: int
        - error: str or None (if invalid)
        """
        try:
            headers = {"User-Agent": USER_AGENT}

            # Use centralized safe_http_fetch for boundary-safe HTTP
            http_response = await safe_http_fetch(url, headers=headers, timeout_seconds=10)
            status_code = http_response.status_code
            final_url = http_response.final_url
            response_text = http_response.text

            if status_code >= 400:
                return {"valid": False, "error": f"HTTP {status_code}"}

            # Check for redirects to unsafe URLs
            if final_url != url and not self._is_safe_url(final_url):
                return {
                    "valid": False,
                    "error": f"Redirect to unsafe URL: {final_url}",
                }

            # Parse with feedparser - response_text is pure Python string
            feed_data = feedparser.parse(response_text)

            # Check for parse errors
            if feed_data.bozo and not feed_data.entries:
                # Security: Log detailed error internally, return generic message
                bozo_exc = feed_data.bozo_exception
                log_op(
                    "feed_validation_parse_error",
                    url=url,
                    error_type=type(bozo_exc).__name__ if bozo_exc else "Unknown",
                    error_detail=str(bozo_exc)[:200] if bozo_exc else "Invalid format",
                )
                return {
                    "valid": False,
                    "error": "Feed format is invalid or not a recognized RSS/Atom feed",
                }

            # Extract metadata - use _safe_str for JsProxy safety
            feed_info = feed_data.feed
            title = _safe_str(feed_info.get("title"))
            site_url = _safe_str(feed_info.get("link"))
            entry_count = len(feed_data.entries)

            # Require at least a title or some entries to be considered valid
            if not title and entry_count == 0:
                return {
                    "valid": False,
                    "error": "Feed has no title and no entries",
                }

            return {
                "valid": True,
                "title": title,
                "site_url": site_url,
                "entry_count": entry_count,
                "final_url": final_url if final_url != url else None,
                "error": None,
            }

        except Exception as e:
            error_msg = str(e)[:200]
            if "timeout" in error_msg.lower():
                return {"valid": False, "error": "Timeout fetching feed (10s)"}
            return {"valid": False, "error": error_msg}

    async def _add_feed(self, request, admin):
        """
        Add a new feed with validation.

        Flow:
        1. Validate URL (SSRF protection)
        2. Fetch and parse the feed to verify it works
        3. Extract title if not provided
        4. Insert into database
        5. Queue for immediate full processing
        """
        form = await request.form_data()
        url = _extract_form_value(form, "url")
        title = _extract_form_value(form, "title")

        if not url:
            return json_error("URL is required")

        # Validate URL (SSRF protection)
        if not self._is_safe_url(url):
            return json_error("Invalid or unsafe URL")

        # Validate the feed by fetching and parsing it
        validation = await self._validate_feed_url(url)

        if not validation["valid"]:
            return json_error(f"Feed validation failed: {validation['error']}")

        # Use extracted title if admin didn't provide one
        if not title:
            title = validation.get("title")

        # If feed was permanently redirected, use the new URL
        final_url = validation.get("final_url") or url

        try:
            # Insert the validated feed
            result_raw = (
                await self.env.DB.prepare("""
                INSERT INTO feeds (url, title, site_url, is_active)
                VALUES (?, ?, ?, 1)
                RETURNING id
            """)
                .bind(final_url, title, validation.get("site_url"))
                .first()
            )

            # Convert JsProxy to Python dict
            result = _to_py_safe(result_raw)
            feed_id = result.get("id") if result else None

            # Audit log with validation info
            await self._log_admin_action(
                admin["id"],
                "add_feed",
                "feed",
                feed_id,
                {
                    "url": final_url,
                    "original_url": url if final_url != url else None,
                    "title": title,
                    "entry_count": validation.get("entry_count", 0),
                },
            )

            # Queue the feed for immediate full processing (fetch entries)
            await self.env.FEED_QUEUE.send(
                {
                    "feed_id": feed_id,
                    "url": final_url,
                }
            )

            log_op(
                "feed_added_and_queued",
                feed_id=feed_id,
                url=final_url,
                title=title,
                entry_count=validation.get("entry_count", 0),
            )

            # Redirect back to admin
            return redirect_response("/admin")

        except Exception as e:
            return json_error(str(e), status=500)

    async def _remove_feed(self, feed_id, admin):
        """Remove a feed."""
        try:
            feed_id = int(feed_id)

            # Get feed info for audit log
            feed_result = (
                await self.env.DB.prepare("SELECT * FROM feeds WHERE id = ?").bind(feed_id).first()
            )

            # Convert JsProxy to Python dict
            feed = _to_py_safe(feed_result)

            if not feed or not isinstance(feed, dict):
                return json_error("Feed not found", status=404)

            # Delete feed (entries will cascade)
            await self.env.DB.prepare("DELETE FROM feeds WHERE id = ?").bind(feed_id).run()

            # Audit log - feed is now a Python dict
            await self._log_admin_action(
                admin["id"],
                "remove_feed",
                "feed",
                feed_id,
                {"url": feed.get("url"), "title": feed.get("title")},
            )

            # Redirect back to admin
            return redirect_response("/admin")

        except Exception as e:
            return json_error(str(e), status=500)

    async def _update_feed(self, request, feed_id, admin):
        """Update a feed (enable/disable)."""
        try:
            feed_id = int(feed_id)
            data_raw = await request.json()

            # Convert JsProxy to Python dict if needed
            data = _to_py_safe(data_raw) or {}

            is_active = data.get("is_active", 1)

            await (
                self.env.DB.prepare("""
                UPDATE feeds SET
                    is_active = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """)
                .bind(is_active, feed_id)
                .run()
            )

            # Audit log
            await self._log_admin_action(
                admin["id"], "update_feed", "feed", feed_id, {"is_active": is_active}
            )

            return json_response({"success": True})

        except Exception as e:
            return json_error(str(e), status=500)

    async def _import_opml(self, request, admin):
        """Import feeds from uploaded OPML file. Admin only."""
        form = await request.form_data()
        # File uploads need direct access, not string conversion
        opml_file = form.get("opml")

        # Check for both Python None and JavaScript undefined
        if not opml_file or _is_js_undefined(opml_file):
            return json_error("No file uploaded")

        # Handle both JsProxy File and test mock
        if hasattr(opml_file, "text"):
            result = opml_file.text()
            # Await if it's a coroutine or JS Promise (JsProxy with 'then' method)
            if asyncio.iscoroutine(result) or hasattr(result, "then"):
                content = await result
            else:
                content = result
        else:
            # Already a string (test fallback)
            content = str(opml_file)

        # Parse OPML with XXE/Billion Laughs protection
        # Security: forbid_dtd=True prevents DOCTYPE declarations and entity expansion
        try:
            parser = ET.XMLParser(forbid_dtd=True)
            root = ET.fromstring(content, parser=parser)
        except ET.ParseError as e:
            # Don't expose detailed parse errors to users
            log_op("opml_parse_error", error=str(e)[:200])
            return json_error("Invalid OPML format")

        imported = 0
        skipped = 0
        errors = []

        for outline in root.iter("outline"):
            xml_url = outline.get("xmlUrl")
            if not xml_url:
                continue

            title = outline.get("title") or outline.get("text") or xml_url
            html_url = outline.get("htmlUrl")

            # Validate URL (SSRF protection)
            if not self._is_safe_url(xml_url):
                errors.append(f"Skipped unsafe URL: {xml_url}")
                continue

            try:
                await (
                    self.env.DB.prepare("""
                    INSERT INTO feeds (url, title, site_url, is_active)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(url) DO NOTHING
                """)
                    .bind(xml_url, title, html_url)
                    .run()
                )
                imported += 1
            except Exception as e:
                skipped += 1
                errors.append(f"Failed to import {xml_url}: {e}")

        # Audit log
        await self._log_admin_action(
            admin["id"],
            "import_opml",
            "feeds",
            None,
            {"imported": imported, "skipped": skipped, "errors": errors[:10]},
        )

        # Redirect back to admin
        return redirect_response("/admin")

    async def _trigger_regenerate(self, admin):
        """Force regeneration by clearing edge cache (not really possible, but log the action)."""
        # In practice, edge cache expires on its own. This is more of a manual trigger to re-fetch.
        await self._log_admin_action(admin["id"], "manual_refresh", None, None, {})

        # Queue all active feeds for immediate fetch
        await self._run_scheduler()

        return redirect_response("/admin")

    async def _view_dlq(self):
        """View dead letter queue contents (failed feeds with 3+ consecutive failures)."""
        result = await self.env.DB.prepare("""
            SELECT id, url, title, consecutive_failures, last_fetch_at, fetch_error as last_error
            FROM feeds
            WHERE consecutive_failures >= 3
            ORDER BY consecutive_failures DESC, last_fetch_at DESC
        """).all()
        return json_response({"failed_feeds": _to_py_list(result.results)})

    async def _retry_dlq_feed(self, feed_id, admin):
        """Retry a failed feed by resetting its failure count and re-queuing."""
        try:
            feed_id = int(feed_id)

            # Get feed info
            feed_result = (
                await self.env.DB.prepare("SELECT * FROM feeds WHERE id = ?").bind(feed_id).first()
            )

            # Convert JsProxy to Python dict
            feed = _to_py_safe(feed_result)

            if not feed or not isinstance(feed, dict):
                return json_error("Feed not found", status=404)

            # Reset failure count
            await (
                self.env.DB.prepare("""
                UPDATE feeds SET
                    consecutive_failures = 0,
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """)
                .bind(feed_id)
                .run()
            )

            # Queue the feed for immediate fetch - feed is now a Python dict
            message = {
                "feed_id": feed_id,
                "url": feed.get("url"),
                "etag": feed.get("etag"),
                "last_modified": feed.get("last_modified"),
            }
            await self.env.FEED_QUEUE.send(message)

            # Audit log
            await self._log_admin_action(
                admin["id"],
                "retry_dlq",
                "feed",
                feed_id,
                {"url": feed.get("url"), "previous_failures": feed.get("consecutive_failures")},
            )

            return redirect_response("/admin")

        except Exception as e:
            log_op("dlq_retry_error", feed_id=feed_id, error=str(e))
            return json_error(str(e), status=500)

    async def _view_audit_log(self):
        """View audit log."""
        result = await self.env.DB.prepare("""
            SELECT al.*, a.github_username, a.display_name
            FROM audit_log al
            LEFT JOIN admins a ON al.admin_id = a.id
            ORDER BY al.created_at DESC
            LIMIT 100
        """).all()
        return json_response({"audit_log": _to_py_list(result.results)})

    async def _log_admin_action(self, admin_id, action, target_type, target_id, details):
        """Log an admin action to the audit log."""
        # CRITICAL: First convert all inputs through _to_py_primitive to handle JsProxy
        # Python None can become JavaScript undefined, which D1 rejects
        admin_id_py = _to_py_primitive(admin_id)
        action_py = _to_py_primitive(action)
        target_type_py = _to_py_primitive(target_type)
        target_id_py = _to_py_primitive(target_id)

        # Convert to safe types with fallbacks
        safe_admin_id = int(admin_id_py) if admin_id_py is not None else 0
        safe_action = str(action_py) if action_py else ""
        safe_target_type = str(target_type_py) if target_type_py else ""
        safe_target_id = int(target_id_py) if target_id_py is not None else 0

        # Ensure details dict values are Python primitives for json.dumps
        # Filter out None values to avoid any potential undefined issues
        safe_details = {}
        if details:
            for k, v in details.items():
                v_py = _to_py_primitive(v)
                if v_py is not None:
                    safe_details[k] = v_py

        details_json = json.dumps(safe_details)
        await (
            self.env.DB.prepare("""
            INSERT INTO audit_log (admin_id, action, target_type, target_id, details)
            VALUES (?, ?, ?, ?, ?)
        """)
            .bind(safe_admin_id, safe_action, safe_target_type, safe_target_id, details_json)
            .run()
        )

    # =========================================================================
    # OAuth & Session Management
    # =========================================================================

    def _verify_signed_cookie(self, request):
        """
        Verify the signed session cookie (stateless, no KV).
        Cookie format: base64(json_payload).signature
        """

        # Safely extract Cookie header (may be JsProxy in Pyodide)
        cookies = _safe_str(request.headers.get("Cookie")) or ""
        session_cookie = None
        for cookie in cookies.split(";"):
            if cookie.strip().startswith("session="):
                session_cookie = cookie.strip()[8:]
                break

        if not session_cookie or "." not in session_cookie:
            return None

        try:
            payload_b64, signature = session_cookie.rsplit(".", 1)

            # Verify signature
            expected_sig = hmac.new(
                self.env.SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            # Decode payload
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            # Check expiration (Issue 10.4: 60-second grace period for clock skew)
            if payload.get("exp", 0) < time.time() - 60:
                return None

            return payload
        except Exception as e:
            log_op("session_verify_failed", error_type=type(e).__name__, error=str(e)[:100])
            return None

    def _redirect_to_github_oauth(self, request):
        """Redirect to GitHub OAuth authorization."""

        state = secrets.token_urlsafe(32)
        client_id = getattr(self.env, "GITHUB_CLIENT_ID", "")

        # Security: Use configured redirect_uri to prevent open redirect attacks
        # OAUTH_REDIRECT_URI should be set in wrangler.toml for production
        configured_redirect = getattr(self.env, "OAUTH_REDIRECT_URI", None)
        if configured_redirect:
            redirect_uri = configured_redirect
        else:
            # Fallback for local dev: extract origin from request URL
            # Note: In Cloudflare Workers, request.url is not user-controlled
            url = request.url
            if hasattr(url, "origin"):
                origin = url.origin
            else:
                url_str = str(url)
                parsed = urlparse(url_str)
                origin = f"{parsed.scheme}://{parsed.netloc}"
            redirect_uri = f"{origin}/auth/github/callback"

        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope=read:user"
            f"&state={state}"
        )

        state_cookie = f"oauth_state={state}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=600"
        return Response(
            "",
            status=302,
            headers={"Location": auth_url, "Set-Cookie": state_cookie},
        )

    async def _handle_github_callback(self, request):
        """Handle GitHub OAuth callback."""
        try:
            url_str = str(request.url)
            qs = parse_qs(url_str.split("?", 1)[1]) if "?" in url_str else {}
            code = qs.get("code", [""])[0]
            state = qs.get("state", [""])[0]

            if not code:
                return Response("Missing authorization code", status=400)

            # Verify state parameter matches cookie (CSRF protection)
            # Safely extract Cookie header (may be JsProxy in Pyodide)
            cookies = _safe_str(request.headers.get("Cookie")) or ""
            expected_state = None
            for cookie in cookies.split(";"):
                if cookie.strip().startswith("oauth_state="):
                    expected_state = cookie.strip()[12:]
                    break

            if not state or not expected_state or state != expected_state:
                return Response("Invalid state parameter", status=400)

            client_id = getattr(self.env, "GITHUB_CLIENT_ID", "")
            client_secret = getattr(self.env, "GITHUB_CLIENT_SECRET", "")

            # Exchange code for access token using centralized safe_http_fetch
            token_response = await safe_http_fetch(
                "https://github.com/login/oauth/access_token",
                method="POST",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )

            if token_response.status_code != 200:
                log_op("github_token_exchange_failed", status_code=token_response.status_code)
                return Response("Failed to exchange authorization code", status=502)

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                error_desc = token_data.get("error_description", "Unknown error")
                log_op("github_oauth_error", error=token_data.get("error"), description=error_desc)
                return Response(f"GitHub OAuth failed: {error_desc}", status=400)

            # Fetch user info using centralized safe_http_fetch
            github_headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            }

            user_response = await safe_http_fetch(
                "https://api.github.com/user",
                headers=github_headers,
            )

            if user_response.status_code != 200:
                log_op(
                    "github_api_error",
                    status_code=user_response.status_code,
                    response=user_response.text[:200],
                )
                return Response(f"GitHub API error: {user_response.status_code}", status=502)

            user_data = user_response.json()
            github_username = user_data.get("login")
            github_id = user_data.get("id")

            # Verify user is an admin
            admin_result = (
                await self.env.DB.prepare(
                    "SELECT * FROM admins WHERE github_username = ? AND is_active = 1"
                )
                .bind(github_username)
                .first()
            )

            # Convert JsProxy to Python dict using centralized helper
            admin = _to_py_safe(admin_result)

            if not admin:
                return Response("Unauthorized: Not an admin", status=403)

            # Update admin's github_id and last_login_at
            await (
                self.env.DB.prepare("""
                UPDATE admins SET github_id = ?, last_login_at = CURRENT_TIMESTAMP
                WHERE github_username = ?
            """)
                .bind(github_id, github_username)
                .run()
            )

            # Create signed session cookie (stateless, no KV)
            session_cookie = self._create_signed_cookie(
                {
                    "github_username": github_username,
                    "github_id": github_id,
                    "avatar_url": user_data.get("avatar_url"),
                    "exp": int(time.time()) + SESSION_TTL_SECONDS,
                }
            )

            # Clear oauth_state cookie and set session cookie
            # Use list of tuples to support multiple Set-Cookie headers
            clear_state = "oauth_state=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0"
            session = (
                f"session={session_cookie}; HttpOnly; Secure; "
                f"SameSite=Lax; Path=/; Max-Age={SESSION_TTL_SECONDS}"
            )
            return Response(
                "",
                status=302,
                headers=[
                    ("Location", "/admin"),
                    ("Set-Cookie", clear_state),
                    ("Set-Cookie", session),
                ],
            )

        except Exception as e:
            # Issue 4.5/6.5: Use log_op() for structured logging
            log_op(
                "oauth_error",
                error_type=type(e).__name__,
                error_message=str(e)[:200],
            )
            return Response("Authentication failed. Please try again.", status=500)

    def _create_signed_cookie(self, payload):
        """Create an HMAC-signed cookie. Format: base64(json_payload).signature"""

        payload_json = json.dumps(payload)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()

        signature = hmac.new(
            self.env.SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()

        return f"{payload_b64}.{signature}"

    def _logout(self, request):
        """Log out by clearing the session cookie (stateless - nothing to delete)."""

        return Response(
            "",
            status=302,
            headers={
                "Location": "/",
                "Set-Cookie": "session=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0",
            },
        )


# Alias for tests which import PlanetCF
PlanetCF = Default
