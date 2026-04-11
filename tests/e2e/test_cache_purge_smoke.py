# tests/e2e/test_cache_purge_smoke.py
"""E2E smoke test for cache purging in real Pyodide.

This test exercises the purge_edge_cache() and purge_edge_cache_global()
code paths in the actual Workers runtime. Unit tests cannot cover the
Pyodide branch (HAS_PYODIDE=True), so this is the only way to verify
that the js.caches.default.delete() and js_fetch() FFI calls don't crash.

Limitation: test-planet runs on *.workers.dev, which has no edge caching.
The purge code runs but has nothing to actually purge. This test proves
the code doesn't throw AttributeError / JsException — not that purging
works end-to-end. Full cache invalidation can only be verified against
a custom-domain deployment (e.g., www.planetcloudflare.dev).
"""

import httpx

from tests.e2e.conftest import E2E_BASE_URL, create_test_session, requires_server


@requires_server
class TestCachePurgeSmoke:
    """Verify cache purge code doesn't crash in real Pyodide."""

    def setup_method(self):
        session_value = create_test_session()
        self.client = httpx.Client(
            base_url=E2E_BASE_URL,
            follow_redirects=False,
            cookies={"session": session_value},
            timeout=httpx.Timeout(60.0, connect=30.0),
        )

    def teardown_method(self):
        self.client.close()

    def test_regenerate_does_not_crash_on_purge(self):
        """POST /admin/regenerate triggers _purge_edge_cache; must not 500.

        Regenerate is the safest content-modifying admin action to test:
        it re-queues feeds and purges cache, but doesn't require specific
        feed state to succeed.
        """
        response = self.client.post("/admin/regenerate")
        # 302 = success (redirect to /admin)
        # 200 = rendered response
        # 403 = admin not in DB (seed issue, not purge issue)
        # 500 = purge or other code crashed in Pyodide
        assert response.status_code != 500, (
            f"Regenerate returned 500 — possible purge crash in Pyodide. "
            f"Body: {response.text[:500]}"
        )

    def test_cacheable_routes_have_cache_control(self):
        """Public cacheable routes include Cache-Control headers.

        This doesn't test edge caching (workers.dev doesn't cache),
        but verifies the headers are set correctly in the response.
        """
        routes = ["/", "/titles", "/feed.atom", "/feed.rss"]
        for route in routes:
            response = self.client.get(route)
            assert response.status_code == 200, f"{route} returned {response.status_code}"
            cc = response.headers.get("cache-control", "")
            assert "max-age" in cc, f"{route} missing max-age in Cache-Control: {cc}"
            assert "stale-while-revalidate" in cc, (
                f"{route} missing stale-while-revalidate in Cache-Control: {cc}"
            )

    def test_admin_routes_have_no_store(self):
        """Admin routes include Cache-Control: no-store."""
        response = self.client.get("/admin")
        if response.status_code == 200:
            cc = response.headers.get("cache-control", "")
            assert "no-store" in cc, f"/admin missing no-store in Cache-Control: {cc}"
