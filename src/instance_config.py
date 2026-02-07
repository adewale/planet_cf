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
# Configuration Defaults
# =============================================================================
# Only keys that are actually consumed via _get_env() at runtime belong here.
# All other configuration values are read directly from env vars in src/main.py
# and src/config.py with their own defaults.

DEFAULTS = {
    # Instance mode (full or lite) - used by is_lite_mode()
    "INSTANCE_MODE": "full",
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
