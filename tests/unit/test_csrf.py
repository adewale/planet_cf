"""CSRF protection tests for admin endpoints (finding H15).

The admin dashboard is JS-driven and form-driven; every state-changing request
must carry a session-bound CSRF token, delivered via the X-CSRF-Token header
(admin.js fetches) or a csrf_token form field (HTML form posts). These tests
verify the token is REQUIRED and correctly bound to the session — the bulk of
the other admin tests rely on MockRequest auto-supplying a valid token, so the
negative cases live here.
"""

from src.auth import generate_csrf_token, verify_csrf_token
from tests.conftest import (
    TEST_SESSION_SECRET,
    MockRequest,
    create_signed_session,
    csrf_token_for,
    make_authenticated_worker,
)

# asyncio_mode = "auto" (pyproject) handles the async tests; no module mark needed.


# =============================================================================
# Token primitives (auth.py)
# =============================================================================


class TestCsrfTokenPrimitives:
    def test_token_is_deterministic_for_a_session(self):
        session = {"github_id": 7, "exp": 1234567890}
        t1 = generate_csrf_token(session, TEST_SESSION_SECRET)
        t2 = generate_csrf_token(session, TEST_SESSION_SECRET)
        assert t1 == t2
        assert len(t1) == 64  # sha256 hex

    def test_token_differs_per_session(self):
        a = generate_csrf_token({"github_id": 1, "exp": 100}, TEST_SESSION_SECRET)
        b = generate_csrf_token({"github_id": 2, "exp": 100}, TEST_SESSION_SECRET)
        c = generate_csrf_token({"github_id": 1, "exp": 200}, TEST_SESSION_SECRET)
        assert a != b  # different user
        assert a != c  # different login (exp)

    def test_token_depends_on_secret(self):
        session = {"github_id": 1, "exp": 100}
        assert generate_csrf_token(session, "secret-a") != generate_csrf_token(session, "secret-b")

    def test_verify_accepts_matching_token(self):
        session = {"github_id": 1, "exp": 100}
        token = generate_csrf_token(session, TEST_SESSION_SECRET)
        assert verify_csrf_token(token, session, TEST_SESSION_SECRET) is True

    def test_verify_rejects_missing_or_wrong_token(self):
        session = {"github_id": 1, "exp": 100}
        assert verify_csrf_token(None, session, TEST_SESSION_SECRET) is False
        assert verify_csrf_token("", session, TEST_SESSION_SECRET) is False
        assert verify_csrf_token("deadbeef", session, TEST_SESSION_SECRET) is False


# =============================================================================
# Enforcement at the admin dispatch layer
# =============================================================================


async def _admin_post(worker, path, cookie, **kwargs):
    request = MockRequest(url=f"https://example.com{path}", method="POST", cookies=cookie, **kwargs)
    return await worker._handle_admin(request, path, None)


class TestCsrfEnforcement:
    async def test_post_without_token_is_rejected(self):
        worker, _env, cookie = make_authenticated_worker()
        # csrf=False => MockRequest supplies neither header nor form field.
        resp = await _admin_post(worker, "/admin/regenerate", cookie, csrf=False)
        assert resp.status == 403

    async def test_post_with_wrong_header_token_is_rejected(self):
        worker, _env, cookie = make_authenticated_worker()
        resp = await _admin_post(
            worker, "/admin/regenerate", cookie, csrf=False, headers={"X-CSRF-Token": "wrong"}
        )
        assert resp.status == 403

    async def test_post_with_valid_header_token_passes_csrf(self):
        worker, _env, cookie = make_authenticated_worker()
        token = csrf_token_for(cookie)
        resp = await _admin_post(
            worker, "/admin/regenerate", cookie, csrf=False, headers={"X-CSRF-Token": token}
        )
        # Passes CSRF -> reaches the handler (not a 403).
        assert resp.status != 403

    async def test_form_field_token_path_passes(self):
        """No header — token only in the form body (the HTML-form path)."""
        worker, _env, cookie = make_authenticated_worker()
        token = csrf_token_for(cookie)
        request = MockRequest(
            url="https://example.com/admin/feeds",
            method="POST",
            cookies=cookie,
            csrf=False,
            headers={"content-type": "application/x-www-form-urlencoded"},
            form_data={"csrf_token": token, "url": ""},  # empty url -> handler validation, not CSRF
        )
        resp = await worker._handle_admin(request, "/admin/feeds", None)
        assert resp.status != 403  # CSRF passed; handler may 4xx on the empty URL separately

    async def test_form_field_wrong_token_rejected(self):
        worker, _env, cookie = make_authenticated_worker()
        request = MockRequest(
            url="https://example.com/admin/feeds",
            method="POST",
            cookies=cookie,
            csrf=False,
            headers={"content-type": "application/x-www-form-urlencoded"},
            form_data={"csrf_token": "nope", "url": "https://e.com/f.xml"},
        )
        resp = await worker._handle_admin(request, "/admin/feeds", None)
        assert resp.status == 403

    async def test_token_from_another_session_is_rejected(self):
        """A token minted for a different session must not be accepted."""
        worker, _env, cookie = make_authenticated_worker()
        other_cookie = create_signed_session(
            secret=TEST_SESSION_SECRET, username="testadmin", github_id=999999
        )
        other_token = csrf_token_for(other_cookie)
        resp = await _admin_post(
            worker, "/admin/regenerate", cookie, csrf=False, headers={"X-CSRF-Token": other_token}
        )
        assert resp.status == 403

    async def test_get_requests_do_not_require_token(self):
        worker, _env, cookie = make_authenticated_worker()
        request = MockRequest(url="https://example.com/admin", method="GET", cookies=cookie)
        resp = await worker._handle_admin(request, "/admin", None)
        assert resp.status == 200

    async def test_delete_verb_requires_token(self):
        worker, _env, cookie = make_authenticated_worker(
            feeds=[{"id": 1, "url": "https://e.com/f.xml", "title": "F", "is_active": 1}]
        )
        request = MockRequest(
            url="https://example.com/admin/feeds/1", method="DELETE", cookies=cookie, csrf=False
        )
        resp = await worker._handle_admin(request, "/admin/feeds/1", None)
        assert resp.status == 403


class TestCsrfTokenInRenderedPages:
    async def test_dashboard_embeds_csrf_meta_and_form_field(self):
        worker, _env, cookie = make_authenticated_worker()
        request = MockRequest(url="https://example.com/admin", method="GET", cookies=cookie)
        resp = await worker._handle_admin(request, "/admin", None)
        body = resp.body if isinstance(resp.body, str) else str(resp.body)
        token = csrf_token_for(cookie)
        assert 'name="csrf-token"' in body
        assert token in body  # the real token is rendered into the page
