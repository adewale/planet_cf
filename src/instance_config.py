# src/instance_config.py
"""Instance configuration loader for Planet.

This module provides configuration loading similar to Rogue Planet's config.ini,
but adapted for Cloudflare Workers environment where we read from environment
variables at runtime.

Configuration hierarchy (highest priority first):
1. Environment variables (PLANET_*, OAUTH_*, etc.)
2. Wrangler vars (set in wrangler.jsonc)
3. Defaults defined here

For local development, you can use config/instance.yaml with the
generate_wrangler_config.py script to generate wrangler.jsonc.
"""

from dataclasses import dataclass, field
from typing import Optional

from wrappers import SafeEnv

# =============================================================================
# Configuration Defaults (Smart Defaults - Rogue Planet inspired)
# =============================================================================
# These defaults are designed to "just work" for minimal configuration.
# All values can be overridden via environment variables.

DEFAULTS = {
    # Instance mode (full or lite)
    "INSTANCE_MODE": "full",

    # Core identity
    # PLANET_NAME: If not set, derived from PLANET_ID (e.g., "planet-python" -> "Planet Python")
    "PLANET_ID": "planet",
    "PLANET_NAME": "Planet",
    "PLANET_DESCRIPTION": "A feed aggregator",
    "PLANET_URL": "https://example.com",
    "PLANET_OWNER_NAME": "Planet Owner",
    "PLANET_OWNER_EMAIL": "planet@example.com",

    # Branding
    # THEME: Falls back to 'default' if specified theme doesn't exist
    "THEME": "default",
    "USER_AGENT_TEMPLATE": "{name}/1.0 (+{url}; {email})",
    "FOOTER_TEXT": "Powered by {name}",
    "SHOW_ADMIN_LINK": "true",

    # Content Display
    # CONTENT_DAYS: Show entries from last N days (default: 7)
    # If no entries in range, automatically shows 50 most recent entries
    "CONTENT_DAYS": "7",
    "GROUP_BY_DATE": "true",
    "MAX_ENTRIES_PER_FEED": "50",  # Max entries to keep per feed
    "RETENTION_DAYS": "90",  # Keep entries for 90 days
    "SUMMARY_MAX_LENGTH": "500",

    # Search
    "SEARCH_ENABLED": "true",
    "EMBEDDING_MAX_CHARS": "2000",
    "SEARCH_SCORE_THRESHOLD": "0.3",
    "SEARCH_TOP_K": "50",

    # Feed Processing (smart defaults for reliability)
    "HTTP_TIMEOUT_SECONDS": "30",  # HTTP request timeout
    "FEED_TIMEOUT_SECONDS": "60",  # Overall feed processing timeout
    "FEED_AUTO_DEACTIVATE_THRESHOLD": "10",  # Auto-deactivate after N failures
    "FEED_FAILURE_THRESHOLD": "3",  # Retry attempts before marking as failed
    "FEED_RETRY_ATTEMPTS": "3",  # Queue retry attempts for transient failures

    # Auth
    "OAUTH_PROVIDER": "github",
    "SESSION_TTL_SECONDS": "604800",  # 7 days
}


@dataclass
class PlanetIdentity:
    """Core planet identity settings."""

    id: str
    name: str
    description: str
    url: str
    owner_name: str
    owner_email: str


@dataclass
class BrandingConfig:
    """Branding and theme configuration."""

    theme: str
    user_agent: str  # Fully resolved (placeholders replaced)
    footer_text: str  # Fully resolved
    show_admin_link: bool


@dataclass
class ContentConfig:
    """Content display settings."""

    days: int
    group_by_date: bool
    max_entries_per_feed: int
    retention_days: int
    summary_max_length: int


@dataclass
class SearchConfig:
    """Semantic search configuration."""

    enabled: bool
    embedding_max_chars: int
    score_threshold: float
    top_k: int


@dataclass
class FeedConfig:
    """Feed processing configuration."""

    http_timeout_seconds: int
    feed_timeout_seconds: int
    auto_deactivate_threshold: int
    failure_threshold: int


@dataclass
class AuthConfig:
    """Authentication configuration."""

    provider: str
    session_ttl_seconds: int
    # Secrets loaded separately from env
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None


@dataclass
class InstanceConfig:
    """Complete instance configuration."""

    planet: PlanetIdentity
    branding: BrandingConfig
    content: ContentConfig
    search: SearchConfig
    feeds: FeedConfig
    auth: AuthConfig

    # Instance mode: "full" or "lite"
    mode: str = field(default="full")

    # Cloudflare resource names (for reference)
    database_name: str = field(default="")
    vectorize_index: str = field(default="")
    feed_queue: str = field(default="")
    dead_letter_queue: str = field(default="")

    def is_lite_mode(self) -> bool:
        """Check if this instance is running in lite mode.

        Lite mode disables:
        - Semantic search (Vectorize)
        - OAuth authentication
        - Admin dashboard

        Returns:
            True if running in lite mode, False for full mode.
        """
        return self.mode.lower() == "lite"

    def is_full_mode(self) -> bool:
        """Check if this instance is running in full mode.

        Returns:
            True if running in full mode (default), False for lite mode.
        """
        return not self.is_lite_mode()


def _get_env(env: SafeEnv, key: str, default: Optional[str] = None) -> str:
    """Get environment variable with fallback to defaults."""
    value = getattr(env, key, None)
    if value is not None:
        return str(value)
    if default is not None:
        return default
    return DEFAULTS.get(key, "")


def _get_bool(env: SafeEnv, key: str) -> bool:
    """Get boolean environment variable."""
    value = _get_env(env, key)
    return value.lower() in ("true", "1", "yes", "on")


def _get_int(env: SafeEnv, key: str) -> int:
    """Get integer environment variable."""
    value = _get_env(env, key)
    try:
        return int(value)
    except (ValueError, TypeError):
        return int(DEFAULTS.get(key, "0"))


def _get_float(env: SafeEnv, key: str) -> float:
    """Get float environment variable."""
    value = _get_env(env, key)
    try:
        return float(value)
    except (ValueError, TypeError):
        return float(DEFAULTS.get(key, "0.0"))


def load_config(env: SafeEnv) -> InstanceConfig:
    """Load instance configuration from environment.

    This is the main entry point for configuration loading.
    Call this once at request start and pass the config through.

    Args:
        env: SafeEnv wrapper around Worker environment bindings

    Returns:
        Complete InstanceConfig with all settings resolved
    """
    # Load instance mode first (affects other config loading)
    instance_mode = _get_env(env, "INSTANCE_MODE", "full").lower()
    is_lite = instance_mode == "lite"

    # Load core identity
    planet_id = _get_env(env, "PLANET_ID", _get_env(env, "INSTANCE_ID", "planet"))

    # Smart default: Derive planet name from instance ID if not explicitly set
    # e.g., "planet-python" -> "Planet Python"
    explicit_name = getattr(env, "PLANET_NAME", None)
    if explicit_name:
        planet_name = str(explicit_name)
    else:
        # Convert instance ID to a readable name
        # "planet-python" -> "Planet Python", "my_feed" -> "My Feed"
        planet_name = planet_id.replace("-", " ").replace("_", " ").title()

    planet_url = _get_env(env, "PLANET_URL")
    owner_email = _get_env(env, "PLANET_OWNER_EMAIL")

    planet = PlanetIdentity(
        id=planet_id,
        name=planet_name,
        description=_get_env(env, "PLANET_DESCRIPTION"),
        url=planet_url,
        owner_name=_get_env(env, "PLANET_OWNER_NAME"),
        owner_email=owner_email,
    )

    # Resolve branding placeholders
    user_agent_template = _get_env(env, "USER_AGENT_TEMPLATE")
    user_agent = user_agent_template.format(
        name=planet_name,
        url=planet_url,
        email=owner_email,
        id=planet_id,
    )

    footer_template = _get_env(env, "FOOTER_TEXT")
    footer_text = footer_template.format(
        name=planet_name,
        url=planet_url,
        id=planet_id,
    )

    # In lite mode, hide admin link by default
    show_admin_link = _get_bool(env, "SHOW_ADMIN_LINK") if not is_lite else False

    branding = BrandingConfig(
        theme=_get_env(env, "THEME"),
        user_agent=user_agent,
        footer_text=footer_text,
        show_admin_link=show_admin_link,
    )

    content = ContentConfig(
        days=_get_int(env, "CONTENT_DAYS"),
        group_by_date=_get_bool(env, "GROUP_BY_DATE"),
        max_entries_per_feed=_get_int(env, "MAX_ENTRIES_PER_FEED"),
        retention_days=_get_int(env, "RETENTION_DAYS"),
        summary_max_length=_get_int(env, "SUMMARY_MAX_LENGTH"),
    )

    # In lite mode, search is always disabled (no Vectorize)
    search_enabled = _get_bool(env, "SEARCH_ENABLED") if not is_lite else False

    search = SearchConfig(
        enabled=search_enabled,
        embedding_max_chars=_get_int(env, "EMBEDDING_MAX_CHARS"),
        score_threshold=_get_float(env, "SEARCH_SCORE_THRESHOLD"),
        top_k=_get_int(env, "SEARCH_TOP_K"),
    )

    feeds = FeedConfig(
        http_timeout_seconds=_get_int(env, "HTTP_TIMEOUT_SECONDS"),
        feed_timeout_seconds=_get_int(env, "FEED_TIMEOUT_SECONDS"),
        auto_deactivate_threshold=_get_int(env, "FEED_AUTO_DEACTIVATE_THRESHOLD"),
        failure_threshold=_get_int(env, "FEED_FAILURE_THRESHOLD"),
    )

    # Auth config - in lite mode, auth is disabled (no OAuth secrets needed)
    if is_lite:
        auth = AuthConfig(
            provider="none",
            session_ttl_seconds=0,
            client_id=None,
            client_secret=None,
            redirect_uri=None,
        )
    else:
        auth = AuthConfig(
            provider=_get_env(env, "OAUTH_PROVIDER"),
            session_ttl_seconds=_get_int(env, "SESSION_TTL_SECONDS"),
            client_id=getattr(env, "OAUTH_CLIENT_ID", None)
            or getattr(env, "GITHUB_CLIENT_ID", None),
            client_secret=getattr(env, "OAUTH_CLIENT_SECRET", None)
            or getattr(env, "GITHUB_CLIENT_SECRET", None),
            redirect_uri=getattr(env, "OAUTH_REDIRECT_URI", None),
        )

    # Cloudflare resource names (derived from planet_id if not explicit)
    database_name = _get_env(env, "DATABASE_NAME", f"{planet_id}-db")
    # In lite mode, vectorize_index is empty (not used)
    vectorize_index = "" if is_lite else _get_env(env, "VECTORIZE_INDEX", f"{planet_id}-entries")
    feed_queue = _get_env(env, "FEED_QUEUE_NAME", f"{planet_id}-feed-queue")
    dead_letter_queue = _get_env(env, "DLQ_NAME", f"{planet_id}-feed-dlq")

    return InstanceConfig(
        planet=planet,
        branding=branding,
        content=content,
        search=search,
        feeds=feeds,
        auth=auth,
        mode=instance_mode,
        database_name=database_name,
        vectorize_index=vectorize_index,
        feed_queue=feed_queue,
        dead_letter_queue=dead_letter_queue,
    )


# =============================================================================
# Lite Mode Helper Functions
# =============================================================================


def is_lite_mode(env: SafeEnv) -> bool:
    """Check if the instance is running in lite mode.

    This is a convenience function for checking lite mode without loading
    the full configuration. Useful for early checks in request handling.

    Lite mode disables:
    - Semantic search (Vectorize)
    - OAuth authentication
    - Admin dashboard

    Args:
        env: SafeEnv wrapper around Worker environment bindings

    Returns:
        True if running in lite mode, False for full mode.
    """
    mode = _get_env(env, "INSTANCE_MODE", "full").lower()
    return mode == "lite"


def is_full_mode(env: SafeEnv) -> bool:
    """Check if the instance is running in full mode.

    Args:
        env: SafeEnv wrapper around Worker environment bindings

    Returns:
        True if running in full mode (default), False for lite mode.
    """
    return not is_lite_mode(env)


# =============================================================================
# OAuth Provider Configuration (like Rogue Planet's extensibility)
# =============================================================================

OAUTH_PROVIDERS = {
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "user_info_url": "https://api.github.com/user",
        "default_scopes": ["user:email"],
        "username_field": "login",
        "id_field": "id",
        "avatar_field": "avatar_url",
    },
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "user_info_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "default_scopes": ["email", "profile"],
        "username_field": "email",
        "id_field": "id",
        "avatar_field": "picture",
    },
    # Add more providers as needed
}


def get_oauth_config(provider: str) -> dict:
    """Get OAuth configuration for a provider.

    Args:
        provider: Provider name (github, google, etc.)

    Returns:
        OAuth configuration dict

    Raises:
        ValueError: If provider is not supported
    """
    if provider not in OAUTH_PROVIDERS:
        raise ValueError(
            f"Unsupported OAuth provider: {provider}. "
            f"Supported: {', '.join(OAUTH_PROVIDERS.keys())}"
        )
    return OAUTH_PROVIDERS[provider]
