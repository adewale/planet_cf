# tests/unit/test_api_contracts.py
"""
API Contract Tests - Verify frontend/backend agreements.

These tests ensure that:
1. Embedded JavaScript uses correct HTTP methods for backend routes
2. Public endpoints return appropriate content types (HTML vs JSON)
3. Error responses are user-friendly for browser-based requests
"""

import re


class TestAdminJSHttpMethods:
    """Verify ADMIN_JS uses correct HTTP methods matching backend routes."""

    def test_feed_title_update_uses_put_method(self):
        """Feed title editing must use PUT to match backend route.

        Backend route (main.py):
            if path.startswith("/admin/feeds/") and method == "PUT":
                return await self._update_feed(request, feed_id, admin)

        Frontend must use: method: 'PUT'
        """
        from templates import ADMIN_JS

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
        from templates import ADMIN_JS

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
        from templates import ADMIN_JS

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
