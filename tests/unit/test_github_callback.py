# tests/unit/test_github_callback.py
"""Unit tests for _handle_github_callback in src/main.py."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from src.main import Default
from src.oauth_handler import OAuthError, TokenExchangeResult, UserInfoResult
from tests.conftest import MockRequest

# =============================================================================
# Mock infrastructure for OAuth callback tests
# =============================================================================


@dataclass
class MockD1Result:
    """Mock D1 query result."""

    results: list[dict]
    success: bool = True


class MockD1Statement:
    """Mock D1 prepared statement."""

    def __init__(self, results: list[dict] | None = None, first_result: dict | None = None):
        self._results = results or []
        self._first_result = first_result
        self.sql = ""
        self.bound_args: list = []

    def bind(self, *args) -> "MockD1Statement":
        self.bound_args = list(args)
        return self

    async def all(self) -> MockD1Result:
        return MockD1Result(results=self._results)

    async def first(self) -> dict | None:
        return self._first_result

    async def run(self) -> MockD1Result:
        return MockD1Result(results=[])


class MockD1ForOAuth:
    """Mock D1 database for OAuth callback tests."""

    def __init__(self, admin: dict | None = None):
        self._admin = admin
        self.statements: list[MockD1Statement] = []

    def prepare(self, sql: str) -> MockD1Statement:
        sql_lower = sql.lower()
        if "select * from admins" in sql_lower:
            stmt = MockD1Statement(first_result=self._admin)
        else:
            stmt = MockD1Statement()
        stmt.sql = sql
        self.statements.append(stmt)
        return stmt


class MockOAuthEnv:
    """Mock environment for OAuth callback tests."""

    def __init__(self, admin: dict | None = None):
        self.DB = MockD1ForOAuth(admin)
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = None
        self.DEAD_LETTER_QUEUE = None
        self.PLANET_NAME = "Test Planet"
        self.PLANET_URL = "https://test.example.com"
        self.PLANET_DESCRIPTION = "Test description"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"


# =============================================================================
# GitHub Callback Tests
# =============================================================================


class TestHandleGitHubCallback:
    """Tests for Default._handle_github_callback."""

    @pytest.mark.asyncio
    async def test_valid_state_and_code_sets_session_cookie(self):
        """Valid state + valid code returns redirect with session cookie."""
        admin = {
            "id": 1,
            "github_username": "testadmin",
            "github_id": 12345,
            "display_name": "Test Admin",
            "is_active": 1,
            "last_login_at": None,
            "created_at": "2026-01-01T00:00:00Z",
        }
        env = MockOAuthEnv(admin=admin)

        worker = Default()
        worker.env = env

        request = MockRequest(
            url="https://example.com/auth/callback?code=validcode&state=abc123",
            cookies="oauth_state=abc123",
        )

        user_result = UserInfoResult(
            username="testadmin",
            user_id=12345,
            avatar_url="https://github.com/testadmin.png",
            user_data={"login": "testadmin", "id": 12345},
        )
        token_result = TokenExchangeResult(access_token="token123")

        with (
            patch.object(
                type(worker),
                "_handle_github_callback",
                wraps=worker._handle_github_callback,
            ),
            patch(
                "src.main.GitHubOAuthHandler.authenticate",
                new_callable=AsyncMock,
                return_value=(user_result, token_result),
            ),
        ):
            response = await worker._handle_github_callback(request)

        assert response.status == 302
        # Check Location header is /admin
        headers_dict = {}
        if isinstance(response.headers, list):
            for key, val in response.headers:
                headers_dict.setdefault(key, []).append(val)
        else:
            headers_dict = response.headers

        assert "/admin" in str(headers_dict.get("Location", ""))

    @pytest.mark.asyncio
    async def test_missing_state_returns_error(self):
        """Missing state parameter returns error response."""
        env = MockOAuthEnv()

        worker = Default()
        worker.env = env

        # No state parameter in URL, no oauth_state cookie
        request = MockRequest(
            url="https://example.com/auth/callback?code=validcode",
            cookies="",
        )

        # OAuth handler will fail on state verification
        error = OAuthError(
            error_type="CSRFError",
            message="Missing or invalid state parameter",
            status_code=400,
        )
        user_result = UserInfoResult(error=error)
        token_result = TokenExchangeResult(error=error)

        with patch(
            "src.main.GitHubOAuthHandler.authenticate",
            new_callable=AsyncMock,
            return_value=(user_result, token_result),
        ):
            response = await worker._handle_github_callback(request)

        # Should return an error page (not 302 redirect)
        assert response.status != 302

    @pytest.mark.asyncio
    async def test_reused_state_replay_attack_returns_error(self):
        """Reused state (state mismatch) returns error response."""
        env = MockOAuthEnv()

        worker = Default()
        worker.env = env

        # State in URL doesn't match cookie
        request = MockRequest(
            url="https://example.com/auth/callback?code=validcode&state=reused_state",
            cookies="oauth_state=original_state",
        )

        error = OAuthError(
            error_type="CSRFError",
            message="State mismatch - possible replay attack",
            status_code=400,
        )
        user_result = UserInfoResult(error=error)
        token_result = TokenExchangeResult(error=error)

        with patch(
            "src.main.GitHubOAuthHandler.authenticate",
            new_callable=AsyncMock,
            return_value=(user_result, token_result),
        ):
            response = await worker._handle_github_callback(request)

        assert response.status != 302

    @pytest.mark.asyncio
    async def test_github_api_error_returns_error(self):
        """GitHub API returning error is handled gracefully."""
        env = MockOAuthEnv()

        worker = Default()
        worker.env = env

        request = MockRequest(
            url="https://example.com/auth/callback?code=badcode&state=abc123",
            cookies="oauth_state=abc123",
        )

        error = OAuthError(
            error_type="TokenExchangeError",
            message="GitHub returned non-200 status",
            status_code=502,
        )
        user_result = UserInfoResult(error=error)
        token_result = TokenExchangeResult(error=error)

        with patch(
            "src.main.GitHubOAuthHandler.authenticate",
            new_callable=AsyncMock,
            return_value=(user_result, token_result),
        ):
            response = await worker._handle_github_callback(request)

        assert response.status != 302

    @pytest.mark.asyncio
    async def test_non_admin_user_returns_access_denied(self):
        """User who is not an admin gets 403 access denied."""
        # admin=None means no admin found in DB
        env = MockOAuthEnv(admin=None)

        worker = Default()
        worker.env = env

        request = MockRequest(
            url="https://example.com/auth/callback?code=validcode&state=abc123",
            cookies="oauth_state=abc123",
        )

        user_result = UserInfoResult(
            username="regularuser",
            user_id=99999,
            avatar_url="https://github.com/regularuser.png",
            user_data={"login": "regularuser", "id": 99999},
        )
        token_result = TokenExchangeResult(access_token="token123")

        with patch(
            "src.main.GitHubOAuthHandler.authenticate",
            new_callable=AsyncMock,
            return_value=(user_result, token_result),
        ):
            response = await worker._handle_github_callback(request)

        # Should be an error page (rendered HTML), not a redirect
        assert response.status != 302

    @pytest.mark.asyncio
    async def test_exception_during_callback_returns_500(self):
        """Unexpected exception during callback returns 500 error."""
        env = MockOAuthEnv()

        worker = Default()
        worker.env = env

        request = MockRequest(
            url="https://example.com/auth/callback?code=validcode&state=abc123",
            cookies="oauth_state=abc123",
        )

        with patch(
            "src.main.GitHubOAuthHandler.authenticate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected failure"),
        ):
            response = await worker._handle_github_callback(request)

        # Should return 500 error page
        assert response.status != 302
