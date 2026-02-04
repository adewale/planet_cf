# src/oauth_handler.py
"""GitHub OAuth handler for authentication flow.

This module provides the GitHubOAuthHandler class that encapsulates
the OAuth flow with GitHub:
- State verification (CSRF protection)
- Token exchange with GitHub API
- User info fetching
- Error handling for each step

Usage:
    handler = GitHubOAuthHandler(
        client_id="...",
        client_secret="...",
        user_agent="PlanetCF/1.0"
    )

    # Verify state and exchange code for token
    result = await handler.exchange_code(code, state, expected_state)
    if result.error:
        return error_response(result.error)

    # Get user info
    user_result = await handler.get_user_info(result.access_token)
    if user_result.error:
        return error_response(user_result.error)

    # Use user_result.user_data
"""

from dataclasses import dataclass
from typing import Any

from wrappers import safe_http_fetch


@dataclass
class OAuthError:
    """Represents an OAuth error.

    Attributes:
        error_type: Type of error (e.g., "ValidationError", "TokenExchangeError")
        message: Human-readable error message
        status_code: HTTP status code to return
    """

    error_type: str
    message: str
    status_code: int = 400


@dataclass
class TokenExchangeResult:
    """Result of token exchange operation.

    Attributes:
        access_token: The GitHub access token (if successful)
        error: Error information (if failed)
    """

    access_token: str | None = None
    error: OAuthError | None = None

    @property
    def success(self) -> bool:
        """Return True if token exchange was successful."""
        return self.access_token is not None and self.error is None


@dataclass
class UserInfoResult:
    """Result of user info fetch operation.

    Attributes:
        username: GitHub username (if successful)
        user_id: GitHub user ID (if successful)
        avatar_url: User's avatar URL (if successful)
        user_data: Full user data dict (if successful)
        error: Error information (if failed)
    """

    username: str | None = None
    user_id: int | None = None
    avatar_url: str | None = None
    user_data: dict[str, Any] | None = None
    error: OAuthError | None = None

    @property
    def success(self) -> bool:
        """Return True if user info fetch was successful."""
        return self.username is not None and self.error is None


class GitHubOAuthHandler:
    """Handler for GitHub OAuth authentication flow.

    Encapsulates the OAuth flow:
    1. State verification (CSRF protection)
    2. Token exchange with GitHub
    3. User info fetching

    Attributes:
        client_id: GitHub OAuth app client ID
        client_secret: GitHub OAuth app client secret
        user_agent: User agent string for API requests
    """

    GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105
    GITHUB_USER_URL = "https://api.github.com/user"
    GITHUB_API_VERSION = "2022-11-28"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str = "PlanetCF/1.0",
    ):
        """Initialize the OAuth handler.

        Args:
            client_id: GitHub OAuth app client ID
            client_secret: GitHub OAuth app client secret
            user_agent: User agent string for API requests
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent

    def verify_state(self, state: str, expected_state: str | None) -> OAuthError | None:
        """Verify the OAuth state parameter matches expected value.

        Args:
            state: State parameter from callback
            expected_state: Expected state from cookie

        Returns:
            OAuthError if verification failed, None if successful
        """
        if not state or not expected_state or state != expected_state:
            return OAuthError(
                error_type="CSRFError",
                message="Security verification failed. Please try signing in again.",
                status_code=400,
            )
        return None

    async def exchange_code(
        self,
        code: str,
        state: str | None = None,
        expected_state: str | None = None,
    ) -> TokenExchangeResult:
        """Exchange authorization code for access token.

        Optionally verifies state parameter if provided.

        Args:
            code: Authorization code from GitHub callback
            state: State parameter from callback (optional)
            expected_state: Expected state from cookie (optional)

        Returns:
            TokenExchangeResult with access token or error
        """
        # Validate code is present
        if not code:
            return TokenExchangeResult(
                error=OAuthError(
                    error_type="ValidationError",
                    message="Missing authorization code",
                    status_code=400,
                )
            )

        # Verify state if provided
        if state is not None or expected_state is not None:
            state_error = self.verify_state(state or "", expected_state)
            if state_error:
                return TokenExchangeResult(error=state_error)

        # Exchange code for token
        try:
            response = await safe_http_fetch(
                self.GITHUB_TOKEN_URL,
                method="POST",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": self.user_agent,
                },
            )

            if response.status_code != 200:
                return TokenExchangeResult(
                    error=OAuthError(
                        error_type="TokenExchangeError",
                        message=f"GitHub token exchange failed with status {response.status_code}",
                        status_code=502,
                    )
                )

            token_data = response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                error_desc = token_data.get("error_description", "Unknown error")
                return TokenExchangeResult(
                    error=OAuthError(
                        error_type="OAuthError",
                        message=f"GitHub OAuth failed: {error_desc}",
                        status_code=400,
                    )
                )

            return TokenExchangeResult(access_token=access_token)

        except Exception as e:
            return TokenExchangeResult(
                error=OAuthError(
                    error_type="NetworkError",
                    message=f"Failed to connect to GitHub: {str(e)}",
                    status_code=502,
                )
            )

    async def get_user_info(self, access_token: str) -> UserInfoResult:
        """Fetch user information from GitHub API.

        Args:
            access_token: GitHub access token

        Returns:
            UserInfoResult with user data or error
        """
        if not access_token:
            return UserInfoResult(
                error=OAuthError(
                    error_type="ValidationError",
                    message="Missing access token",
                    status_code=400,
                )
            )

        try:
            response = await safe_http_fetch(
                self.GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": self.user_agent,
                    "X-GitHub-Api-Version": self.GITHUB_API_VERSION,
                },
            )

            if response.status_code != 200:
                return UserInfoResult(
                    error=OAuthError(
                        error_type="GitHubAPIError",
                        message=f"GitHub API error: {response.status_code}",
                        status_code=502,
                    )
                )

            user_data = response.json()
            return UserInfoResult(
                username=user_data.get("login"),
                user_id=user_data.get("id"),
                avatar_url=user_data.get("avatar_url"),
                user_data=user_data,
            )

        except Exception as e:
            return UserInfoResult(
                error=OAuthError(
                    error_type="NetworkError",
                    message=f"Failed to fetch user info: {str(e)}",
                    status_code=502,
                )
            )

    async def authenticate(
        self,
        code: str,
        state: str,
        expected_state: str | None,
    ) -> tuple[UserInfoResult, TokenExchangeResult]:
        """Complete the full OAuth authentication flow.

        Combines state verification, code exchange, and user info fetch.

        Args:
            code: Authorization code from GitHub callback
            state: State parameter from callback
            expected_state: Expected state from cookie

        Returns:
            Tuple of (UserInfoResult, TokenExchangeResult)
            Check user_result.success to determine if auth succeeded.
        """
        # Exchange code for token (includes state verification)
        token_result = await self.exchange_code(code, state, expected_state)
        if not token_result.success:
            return UserInfoResult(error=token_result.error), token_result

        # Get user info
        if token_result.access_token is None:
            return UserInfoResult(
                error=OAuthError(
                    error_type="TokenExchangeError",
                    message="Missing access token from token exchange",
                    status_code=500,
                )
            ), token_result
        user_result = await self.get_user_info(token_result.access_token)
        return user_result, token_result


def extract_oauth_state_from_cookies(cookie_header: str) -> str | None:
    """Extract OAuth state from cookie header.

    Args:
        cookie_header: Raw Cookie header string

    Returns:
        OAuth state value if found, None otherwise
    """
    for cookie in cookie_header.split(";"):
        cookie = cookie.strip()
        if cookie.startswith("oauth_state="):
            return cookie[12:]
    return None
