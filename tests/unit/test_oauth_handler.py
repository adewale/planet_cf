# tests/unit/test_oauth_handler.py
"""Tests for the GitHub OAuth handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.oauth_handler import (
    GitHubOAuthHandler,
    OAuthError,
    TokenExchangeResult,
    UserInfoResult,
    extract_oauth_state_from_cookies,
)


class TestOAuthError:
    """Tests for OAuthError dataclass."""

    def test_error_properties(self):
        """OAuthError has correct properties."""
        error = OAuthError(
            error_type="ValidationError",
            message="Test error",
            status_code=400,
        )

        assert error.error_type == "ValidationError"
        assert error.message == "Test error"
        assert error.status_code == 400

    def test_default_status_code(self):
        """Default status code is 400."""
        error = OAuthError(error_type="Test", message="Test")

        assert error.status_code == 400
        assert error.error_type == "Test"
        assert error.message == "Test"


class TestTokenExchangeResult:
    """Tests for TokenExchangeResult dataclass."""

    def test_success_result(self):
        """Success result has access token."""
        result = TokenExchangeResult(access_token="token123")

        assert result.success is True
        assert result.access_token == "token123"
        assert result.error is None

    def test_error_result(self):
        """Error result has error info."""
        error = OAuthError(error_type="Test", message="Failed")
        result = TokenExchangeResult(error=error)

        assert result.success is False
        assert result.access_token is None
        assert result.error == error
        assert result.error.error_type == "Test"
        assert result.error.message == "Failed"


class TestUserInfoResult:
    """Tests for UserInfoResult dataclass."""

    def test_success_result(self):
        """Success result has user data."""
        result = UserInfoResult(
            username="testuser",
            user_id=12345,
            avatar_url="https://example.com/avatar.png",
            user_data={"login": "testuser", "id": 12345},
        )

        assert result.success is True
        assert result.username == "testuser"
        assert result.user_id == 12345
        assert result.error is None
        assert result.avatar_url == "https://example.com/avatar.png"
        assert result.user_data == {"login": "testuser", "id": 12345}

    def test_error_result(self):
        """Error result has error info."""
        error = OAuthError(error_type="Test", message="Failed")
        result = UserInfoResult(error=error)

        assert result.success is False
        assert result.username is None
        assert result.user_id is None
        assert result.avatar_url is None
        assert result.user_data is None
        assert result.error == error


class TestExtractOAuthStateFromCookies:
    """Tests for cookie state extraction."""

    def test_extracts_state_from_cookies(self):
        """Extracts oauth_state from cookie header."""
        cookies = "session=abc123; oauth_state=xyz789; other=value"
        result = extract_oauth_state_from_cookies(cookies)

        assert result == "xyz789"

    def test_handles_only_oauth_state(self):
        """Handles cookie header with only oauth_state."""
        cookies = "oauth_state=state123"
        result = extract_oauth_state_from_cookies(cookies)

        assert result == "state123"
        assert isinstance(result, str)

    def test_returns_none_when_missing(self):
        """Returns None when oauth_state not present."""
        cookies = "session=abc; other=value"
        result = extract_oauth_state_from_cookies(cookies)

        assert result is None
        # Ensure it doesn't match similar-but-different cookie names
        assert extract_oauth_state_from_cookies("not_oauth_state=xyz") is None

    def test_handles_empty_string(self):
        """Handles empty cookie string."""
        result = extract_oauth_state_from_cookies("")

        assert result is None
        # Also returns None for whitespace-only string
        assert extract_oauth_state_from_cookies("   ") is None

    def test_handles_whitespace(self):
        """Handles whitespace in cookie header."""
        cookies = "  oauth_state=state123  ;  other=value  "
        result = extract_oauth_state_from_cookies(cookies)

        assert result == "state123"
        # Verify no leading/trailing whitespace leaked into the value
        assert not result.startswith(" ")
        assert not result.endswith(" ")


class TestGitHubOAuthHandlerStateVerification:
    """Tests for state verification in OAuth handler."""

    def test_verify_state_success(self):
        """State verification succeeds when values match."""
        handler = GitHubOAuthHandler("client_id", "client_secret")
        result = handler.verify_state("state123", "state123")

        assert result is None
        # Verify handler properties were initialized correctly
        assert handler.client_id == "client_id"
        assert handler.client_secret == "client_secret"  # pragma: allowlist secret

    def test_verify_state_mismatch(self):
        """State verification fails when values don't match."""
        handler = GitHubOAuthHandler("client_id", "client_secret")
        result = handler.verify_state("state123", "state456")

        assert result is not None
        assert result.error_type == "CSRFError"
        assert result.status_code == 400
        assert "try signing in" in result.message.lower()

    def test_verify_state_missing_state(self):
        """State verification fails when state is missing."""
        handler = GitHubOAuthHandler("client_id", "client_secret")
        result = handler.verify_state("", "expected")

        assert result is not None
        assert result.error_type == "CSRFError"
        assert result.status_code == 400
        assert isinstance(result, OAuthError)

    def test_verify_state_missing_expected(self):
        """State verification fails when expected is missing."""
        handler = GitHubOAuthHandler("client_id", "client_secret")
        result = handler.verify_state("state123", None)

        assert result is not None
        assert result.error_type == "CSRFError"
        assert result.status_code == 400
        assert result.message  # error message should not be empty


class TestGitHubOAuthHandlerTokenExchange:
    """Tests for token exchange in OAuth handler."""

    @pytest.mark.asyncio
    async def test_exchange_code_missing_code(self):
        """Returns error when code is missing."""
        handler = GitHubOAuthHandler("client_id", "client_secret")
        result = await handler.exchange_code("")

        assert result.success is False
        assert result.error.error_type == "ValidationError"
        assert "Missing authorization code" in result.error.message
        assert result.error.status_code == 400
        assert result.access_token is None

    @pytest.mark.asyncio
    async def test_exchange_code_state_verification_fails(self):
        """Returns error when state verification fails."""
        handler = GitHubOAuthHandler("client_id", "client_secret")
        result = await handler.exchange_code("code123", state="wrong", expected_state="expected")

        assert result.success is False
        assert result.error.error_type == "CSRFError"
        assert result.error.status_code == 400
        assert result.access_token is None

    @pytest.mark.asyncio
    async def test_exchange_code_success(self):
        """Successful token exchange returns access token."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token123"}

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            result = await handler.exchange_code("code123")

        assert result.success is True
        assert result.access_token == "token123"
        assert result.error is None
        mock_fetch.assert_called_once()
        # Verify fetch was called with correct GitHub token URL
        call_args = mock_fetch.call_args
        assert call_args[0][0] == GitHubOAuthHandler.GITHUB_TOKEN_URL
        # Verify Accept header requests JSON
        assert call_args[1]["headers"]["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_exchange_code_github_error(self):
        """Returns error when GitHub returns non-200."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            result = await handler.exchange_code("code123")

        assert result.success is False
        assert result.error.error_type == "TokenExchangeError"
        assert result.error.status_code == 502
        assert result.access_token is None
        assert "500" in result.error.message

    @pytest.mark.asyncio
    async def test_exchange_code_no_access_token(self):
        """Returns error when GitHub doesn't return access token."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Code has expired",
        }

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            result = await handler.exchange_code("code123")

        assert result.success is False
        assert result.error.error_type == "OAuthError"
        assert "Code has expired" in result.error.message
        assert result.error.status_code == 400
        assert result.access_token is None

    @pytest.mark.asyncio
    async def test_exchange_code_network_error(self):
        """Returns error on network failure."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Connection refused")
            result = await handler.exchange_code("code123")

        assert result.success is False
        assert result.error.error_type == "NetworkError"
        assert result.error.status_code == 502
        assert "Connection refused" in result.error.message
        assert result.access_token is None


class TestGitHubOAuthHandlerUserInfo:
    """Tests for user info fetching in OAuth handler."""

    @pytest.mark.asyncio
    async def test_get_user_info_missing_token(self):
        """Returns error when token is missing."""
        handler = GitHubOAuthHandler("client_id", "client_secret")
        result = await handler.get_user_info("")

        assert result.success is False
        assert result.error.error_type == "ValidationError"
        assert result.error.status_code == 400
        assert "Missing access token" in result.error.message
        assert result.username is None

    @pytest.mark.asyncio
    async def test_get_user_info_success(self):
        """Successful user info fetch returns user data."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "login": "testuser",
            "id": 12345,
            "avatar_url": "https://example.com/avatar.png",
        }

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            result = await handler.get_user_info("token123")

        assert result.success is True
        assert result.username == "testuser"
        assert result.user_id == 12345
        assert result.avatar_url == "https://example.com/avatar.png"
        assert result.error is None
        assert result.user_data is not None
        # Verify fetch was called with Bearer token and correct GitHub API URL
        call_args = mock_fetch.call_args
        assert call_args[0][0] == GitHubOAuthHandler.GITHUB_USER_URL
        assert call_args[1]["headers"]["Authorization"] == "Bearer token123"

    @pytest.mark.asyncio
    async def test_get_user_info_github_error(self):
        """Returns error when GitHub API returns non-200."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            result = await handler.get_user_info("token123")

        assert result.success is False
        assert result.error.error_type == "GitHubAPIError"
        assert result.error.status_code == 502
        assert "401" in result.error.message
        assert result.username is None
        assert result.user_data is None

    @pytest.mark.asyncio
    async def test_get_user_info_network_error(self):
        """Returns error on network failure."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("Connection refused")
            result = await handler.get_user_info("token123")

        assert result.success is False
        assert result.error.error_type == "NetworkError"
        assert result.error.status_code == 502
        assert "Connection refused" in result.error.message
        assert result.username is None


class TestGitHubOAuthHandlerAuthenticate:
    """Tests for full authentication flow."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        """Full authentication succeeds with valid inputs."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "token123"}

        user_response = MagicMock()
        user_response.status_code = 200
        user_response.json.return_value = {
            "login": "testuser",
            "id": 12345,
            "avatar_url": "https://example.com/avatar.png",
        }

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [token_response, user_response]
            user_result, token_result = await handler.authenticate(
                "code123", "state123", "state123"
            )

        assert token_result.success is True
        assert token_result.access_token == "token123"
        assert token_result.error is None
        assert user_result.success is True
        assert user_result.username == "testuser"
        assert user_result.user_id == 12345
        assert user_result.error is None
        # Two fetches: token exchange + user info
        assert mock_fetch.call_count == 2

    @pytest.mark.asyncio
    async def test_authenticate_token_exchange_fails(self):
        """Authentication fails if token exchange fails."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("src.oauth_handler.safe_http_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response
            user_result, token_result = await handler.authenticate(
                "code123", "state123", "state123"
            )

        assert token_result.success is False
        assert token_result.error.error_type == "TokenExchangeError"
        assert user_result.success is False
        assert user_result.error == token_result.error
        assert user_result.username is None
        # Only one fetch (token exchange) should have been attempted since it failed
        assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_authenticate_state_mismatch(self):
        """Authentication fails on state mismatch."""
        handler = GitHubOAuthHandler("client_id", "client_secret")

        user_result, token_result = await handler.authenticate(
            "code123", "wrong_state", "expected_state"
        )

        assert token_result.success is False
        assert token_result.error.error_type == "CSRFError"
        assert token_result.error.status_code == 400
        assert user_result.success is False
        assert user_result.error == token_result.error
