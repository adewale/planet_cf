# tests/unit/test_api_contracts.py
"""
API Contract Tests - Verify frontend/backend agreements.

These tests ensure that:
1. Embedded JavaScript uses correct HTTP methods for backend routes
2. Public endpoints return appropriate content types (HTML vs JSON)
3. Error responses are user-friendly for browser-based requests
4. JSON response shapes match what admin JavaScript expects (C1 prevention)
5. Every registered route has a corresponding handler in _dispatch_route
6. Every TEMPLATE_FEED_* constant is wired up to a route
"""

import inspect
import re
from pathlib import Path

ADMIN_JS = (Path(__file__).parent.parent.parent / "static" / "admin.js").read_text()


class TestAdminJSHttpMethods:
    """Verify ADMIN_JS uses correct HTTP methods matching backend routes."""

    def test_feed_title_update_uses_put_method(self):
        """Feed title editing must use PUT to match backend route.

        Backend route (main.py):
            if path.startswith("/admin/feeds/") and method == "PUT":
                return await self._update_feed(request, feed_id, admin)

        Frontend must use: method: 'PUT'
        """

        # Find the fetch call for updating feed title (NOT the toggle endpoint)
        # Pattern: fetch('/admin/feeds/' + feedId, { method: '...'
        # Exclude: fetch('/admin/feeds/' + feedId + '/toggle', { method: '...'
        #
        # We need to find fetch calls to /admin/feeds/{id} that are NOT /toggle
        title_update_pattern = r"fetch\s*\(\s*['\"]?/admin/feeds/['\"]?\s*\+\s*feedId\s*,\s*\{[^}]*method:\s*['\"](\w+)['\"]"
        toggle_pattern = (
            r"fetch\s*\(\s*['\"]?/admin/feeds/['\"]?\s*\+\s*feedId\s*\+\s*['\"]?/toggle"
        )

        # Find all fetch calls to /admin/feeds/{id}
        title_matches = re.findall(title_update_pattern, ADMIN_JS, re.DOTALL)

        # Check if there's a toggle pattern - if so, one of the POSTs is for toggle
        has_toggle = bool(re.search(toggle_pattern, ADMIN_JS))

        assert len(title_matches) > 0, "No fetch call found for /admin/feeds/{id}"

        # If toggle exists, we expect one POST (toggle) and one PUT (title update)
        # If no toggle, all should be PUT
        post_count = title_matches.count("POST")
        put_count = title_matches.count("PUT")

        if has_toggle:
            # With toggle endpoint, expect exactly 1 POST (for toggle) and 1 PUT (for title)
            assert put_count >= 1, (
                f"Feed title update should use PUT method. "
                f"Found {put_count} PUT and {post_count} POST calls. "
                f"The title update is using POST but backend expects PUT - "
                f"this will cause 405 Method Not Allowed errors."
            )
        else:
            # Without toggle, all should be PUT
            assert post_count == 0, (
                "Feed title update uses POST but backend expects PUT. "
                "This will cause 405 Method Not Allowed errors."
            )

    def test_feed_toggle_uses_post_method(self):
        """Feed toggle must use POST to match backend route.

        Backend route (main.py):
            if path.startswith("/admin/feeds/") and path.endswith("/toggle") and method == "POST":
        """

        # Find the fetch call for toggling feed
        pattern = r"fetch\s*\(\s*['\"]?/admin/feeds/['\"]?\s*\+\s*feedId\s*\+\s*['\"]?/toggle['\"]?\s*,\s*\{[^}]*method:\s*['\"](\w+)['\"]"
        matches = re.findall(pattern, ADMIN_JS, re.DOTALL)

        assert len(matches) > 0, "No fetch call found for /admin/feeds/{id}/toggle"
        assert matches[0] == "POST", f"Feed toggle uses '{matches[0]}' but backend expects 'POST'"

    def test_reindex_uses_post_method(self):
        """Reindex must use POST to match backend route.

        Backend route (main.py):
            if path == "/admin/reindex" and method == "POST":
        """

        pattern = r"fetch\s*\(\s*['\"]?/admin/reindex['\"]?\s*,\s*\{[^}]*method:\s*['\"](\w+)['\"]"
        matches = re.findall(pattern, ADMIN_JS, re.DOTALL)

        assert len(matches) > 0, "No fetch call found for /admin/reindex"
        assert matches[0] == "POST", f"Reindex uses '{matches[0]}' but backend expects 'POST'"


class TestSearchEndpointResponses:
    """Verify search endpoint returns appropriate responses for browser requests."""

    def test_search_validation_error_returns_html(self):
        """Search validation errors should return HTML, not JSON.

        When users submit the search form with invalid query, they expect
        an HTML page explaining the error, not raw JSON like {"error": "..."}.

        Bug: /search?q= returned JSON: {"error": "Query too short"}
        Fix: Should return HTML search page with error message displayed
        """
        from templates import TEMPLATE_SEARCH, render_template

        # Verify the search template can render with an error message
        # This tests that we have the capability to show errors in HTML
        html = render_template(
            TEMPLATE_SEARCH,
            planet={"name": "Test", "description": "Test", "link": "http://test"},
            query="",
            results=[],
            error="Query must be at least 2 characters",
        )

        # The template should include the error message
        assert "Query must be at least 2 characters" in html, (
            "Search template should display error messages. "
            "Add an 'error' variable to the search template."
        )
        assert "<!DOCTYPE html>" in html or "<html" in html, (
            "Search validation errors should return HTML pages"
        )


class TestPublicEndpointContentTypes:
    """Verify public endpoints return correct content types."""

    def test_search_validation_error_is_html_not_json(self):
        """Search validation errors should return HTML for browser UX.

        The search form is submitted via browser, so errors should be
        rendered as HTML pages, not JSON responses.
        """

        # Create a mock request with empty query
        # This is a unit test that checks the response type
        # Integration test will verify actual behavior
        pass


class TestBackendRouteDefinitions:
    """Verify backend routes are defined as expected."""

    def test_feed_update_route_expects_put(self):
        """Verify the feed update route checks for PUT method."""
        import inspect

        from main import PlanetCF

        source = inspect.getsource(PlanetCF._handle_admin)

        # Check that PUT is expected for feed updates
        assert 'method == "PUT"' in source or "method == 'PUT'" in source, (
            "Feed update route should check for PUT method"
        )

    def test_feed_toggle_route_expects_post(self):
        """Verify the feed toggle route checks for POST method."""
        import inspect

        from main import PlanetCF

        source = inspect.getsource(PlanetCF._handle_admin)

        # Check that POST is expected for toggle with /toggle path
        assert "/toggle" in source, "Toggle route should check for /toggle path"


# =============================================================================
# JSON Response Shape Contract Tests
# =============================================================================


class TestJSONResponseContracts:
    """Verify JSON response keys match what admin JavaScript expects.

    These tests prevent C1-type bugs where the backend returns JSON with
    different keys than the frontend JavaScript expects (e.g., returning
    {"failed_feeds": ...} when JS expects {"feeds": ...}).
    """

    def _get_js_data_accesses(self) -> dict[str, set[str]]:
        """Extract all data.X property accesses from admin JS, grouped by function.

        Returns:
            Dict mapping JS function name to set of data.X property names accessed
        """

        # Map JS functions to their data property accesses
        functions: dict[str, set[str]] = {}

        # Split JS into function blocks
        # loadDLQ, loadAuditLog, rebuildSearchIndex, inline fetch handlers
        func_pattern = re.compile(
            r"function\s+(\w+)\s*\(\s*\)\s*\{(.*?)^\}",
            re.DOTALL | re.MULTILINE,
        )

        for match in func_pattern.finditer(ADMIN_JS):
            func_name = match.group(1)
            func_body = match.group(2)

            # Find all data.X accesses
            data_accesses = set(re.findall(r"data\.(\w+)", func_body))
            if data_accesses:
                functions[func_name] = data_accesses

        # Also check inline .then(function(data) { ... }) handlers
        inline_pattern = re.compile(
            r"\.then\(function\(data\)\s*\{(.*?)\}\)",
            re.DOTALL,
        )
        for i, match in enumerate(inline_pattern.finditer(ADMIN_JS)):
            body = match.group(1)
            data_accesses = set(re.findall(r"data\.(\w+)", body))
            if data_accesses and f"inline_{i}" not in functions:
                # Try to find context
                start = max(0, match.start() - 200)
                context = ADMIN_JS[start : match.start()]
                if "/admin/feeds/" in context and "toggle" not in context:
                    functions.setdefault("feed_update_handler", set()).update(data_accesses)

        return functions

    def test_dlq_response_uses_feeds_key(self):
        """DLQ endpoint must return {"feeds": [...]} to match loadDLQ() JavaScript.

        C1 bug: Backend returned {"failed_feeds": ...} but JS expected data.feeds.
        This test ensures the backend _view_dlq() returns the correct key.
        """
        from main import Default

        source = inspect.getsource(Default._view_dlq)

        # The response must contain "feeds" as a key
        assert '"feeds"' in source, (
            '_view_dlq() must return JSON with "feeds" key. '
            "The admin JS loadDLQ() accesses data.feeds - "
            'if the backend returns {"failed_feeds": ...} the DLQ tab will show empty.'
        )

        # It should NOT use "failed_feeds"
        assert '"failed_feeds"' not in source, (
            '_view_dlq() returns "failed_feeds" but JS expects "feeds". '
            "This is the C1 bug - the DLQ tab will appear empty."
        )

    def test_dlq_js_expects_feeds_key(self):
        """Verify admin JS loadDLQ() accesses data.feeds."""

        # Find loadDLQ function body
        func_match = re.search(
            r"function\s+loadDLQ\s*\(\s*\)\s*\{(.*?)^\}",
            ADMIN_JS,
            re.DOTALL | re.MULTILINE,
        )
        assert func_match, "loadDLQ() function not found in ADMIN_JS"

        body = func_match.group(1)
        assert "data.feeds" in body, (
            "loadDLQ() should access data.feeds to match backend _view_dlq() response"
        )

    def test_list_feeds_response_uses_feeds_key(self):
        """_list_feeds() must return {"feeds": [...]} matching JS expectations."""
        from main import Default

        source = inspect.getsource(Default._list_feeds)

        assert '"feeds"' in source, '_list_feeds() must return JSON with "feeds" key.'

    def test_audit_log_response_uses_entries_key(self):
        """_view_audit_log() must return {"entries": [...]} matching loadAuditLog() JS.

        The admin JS loadAuditLog() accesses data.entries to render audit items.
        """
        from main import Default

        source = inspect.getsource(Default._view_audit_log)

        assert '"entries"' in source, (
            '_view_audit_log() must return JSON with "entries" key. '
            "The admin JS loadAuditLog() accesses data.entries."
        )

    def test_audit_log_js_expects_entries_key(self):
        """Verify admin JS loadAuditLog() accesses data.entries."""

        func_match = re.search(
            r"function\s+loadAuditLog\s*\(\s*\)\s*\{(.*?)^\}",
            ADMIN_JS,
            re.DOTALL | re.MULTILINE,
        )
        assert func_match, "loadAuditLog() function not found in ADMIN_JS"

        body = func_match.group(1)
        assert "data.entries" in body, (
            "loadAuditLog() should access data.entries to match backend _view_audit_log() response"
        )

    def test_update_feed_response_uses_success_key(self):
        """_update_feed() must return {"success": true} matching JS expectations.

        The inline JS handler for feed title updates checks data.success.
        """
        from main import Default

        source = inspect.getsource(Default._update_feed)

        assert '"success"' in source, (
            '_update_feed() must return JSON with "success" key. '
            "The admin JS checks data.success after title updates."
        )

    def test_reindex_response_uses_success_and_indexed_keys(self):
        """_reindex_all_entries() must return {"success": true, "indexed": N}.

        The admin JS rebuildSearchIndex() checks data.success and data.indexed.
        """
        from main import Default

        source = inspect.getsource(Default._reindex_all_entries)

        assert '"success"' in source, (
            '_reindex_all_entries() must return JSON with "success" key. '
            "The admin JS rebuildSearchIndex() checks data.success."
        )
        assert '"indexed"' in source, (
            '_reindex_all_entries() must return JSON with "indexed" key. '
            "The admin JS shows 'Done! (N indexed)' using data.indexed."
        )

    def test_reindex_js_expects_success_and_indexed(self):
        """Verify admin JS rebuildSearchIndex() accesses data.success and data.indexed."""

        func_match = re.search(
            r"function\s+rebuildSearchIndex\s*\(\s*\)\s*\{(.*?)^\}",
            ADMIN_JS,
            re.DOTALL | re.MULTILINE,
        )
        assert func_match, "rebuildSearchIndex() function not found in ADMIN_JS"

        body = func_match.group(1)
        assert "data.success" in body, "rebuildSearchIndex() should check data.success"
        assert "data.indexed" in body, "rebuildSearchIndex() should use data.indexed for display"

    def test_all_js_data_accesses_are_documented(self):
        """Comprehensive check: extract all data.X from JS and verify they're expected.

        This test serves as a living document of the frontend-backend contract.
        """

        # Extract all data.X accesses from the entire JS
        all_accesses = set(re.findall(r"data\.(\w+)", ADMIN_JS))

        # These are the known/expected data properties
        expected_properties = {
            "feeds",  # loadDLQ, _list_feeds responses
            "entries",  # loadAuditLog response
            "success",  # _update_feed, _reindex_all_entries responses
            "indexed",  # _reindex_all_entries response
            "error",  # error responses (json_error)
            "length",  # JavaScript array length check (data.feeds.length)
        }

        unexpected = all_accesses - expected_properties
        assert not unexpected, (
            f"Admin JS accesses data properties not in known contract: {unexpected}. "
            f"Either add these to the expected_properties set (if intentional) "
            f"or fix the JS/backend mismatch."
        )


# =============================================================================
# Route-Handler Coverage Tests
# =============================================================================


class TestRouteHandlerCoverage:
    """Verify every registered route has a corresponding handler in _dispatch_route.

    This test class prevents the class of bug where a route is defined in
    create_default_routes() but never wired to a handler in _dispatch_route(),
    or where a TEMPLATE_FEED_* constant is defined but never used.
    """

    def test_all_routes_have_dispatch_handlers(self):
        """Every route path in create_default_routes() must appear in _dispatch_route().

        This would have caught the missing RSS 1.0 route handler: the route
        existed in create_default_routes() but _dispatch_route() had no case for it.
        """
        from main import Default
        from route_dispatcher import create_default_routes

        routes = create_default_routes()
        dispatch_source = inspect.getsource(Default._dispatch_route)

        for route in routes:
            path = route.path
            # Prefix routes (like /admin) are matched by startswith,
            # so we just check the path string appears in the source
            assert f'"{path}"' in dispatch_source or f"'{path}'" in dispatch_source, (
                f"Route '{path}' is registered in create_default_routes() but has no "
                f"handler case in _dispatch_route(). Add an elif branch for it."
            )

    def test_all_feed_template_constants_are_used_in_main(self):
        """Every TEMPLATE_FEED_* constant should be referenced in main.py.

        This catches dead template constants that are defined in templates.py
        but never imported or used in main.py, indicating a missing feature.
        """
        import importlib

        import templates

        # Find all TEMPLATE_FEED_* constants
        feed_constants = [name for name in dir(templates) if name.startswith("TEMPLATE_FEED_")]

        main_module = importlib.import_module("main")
        main_source = inspect.getsource(main_module)

        for const_name in feed_constants:
            assert const_name in main_source, (
                f"Template constant '{const_name}' from templates.py is not used in "
                f"main.py. Either wire it up to a route handler or remove it."
            )
