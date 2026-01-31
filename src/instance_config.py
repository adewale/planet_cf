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
    # Auth
    "OAUTH_PROVIDER": "github",
    "SESSION_TTL_SECONDS": "604800",  # 7 days
}


# =============================================================================
# Environment Variable Helpers
# =============================================================================


def _get_env(env: SafeEnv, key: str, default: str | None = None) -> str:
    """Get environment variable with fallback to defaults."""
    value = getattr(env, key, None)
    if value is not None:
        return str(value)
    if default is not None:
        return default
    return DEFAULTS.get(key, "")


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


