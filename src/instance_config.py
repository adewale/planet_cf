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
create_instance.py script to generate wrangler.jsonc.
"""

from wrappers import SafeEnv

# =============================================================================
# Configuration Defaults
# =============================================================================
# Only keys that are actually consumed via _get_env() at runtime belong here.
# All other configuration values are read directly from env vars in src/main.py
# and src/config.py with their own defaults.

DEFAULTS = {
    # Instance mode (full, admin, or lite)
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
# Instance Mode Helper Functions
# =============================================================================

_VALID_MODES = {"lite", "admin", "full"}


def get_instance_mode(env: SafeEnv) -> str:
    """Return the normalised instance mode string.

    Reads INSTANCE_MODE from the environment and normalises it to one of
    the three recognised values: ``"lite"``, ``"admin"``, or ``"full"``.
    Unrecognised values fall back to ``"full"``.

    Args:
        env: SafeEnv wrapper around Worker environment bindings.

    Returns:
        One of ``"lite"``, ``"admin"``, or ``"full"``.
    """
    mode = _get_env(env, "INSTANCE_MODE", "full").lower()
    if mode not in _VALID_MODES:
        return "full"
    return mode


def is_admin_enabled(env: SafeEnv) -> bool:
    """Check whether the admin dashboard and OAuth are available.

    Returns ``True`` for the ``"admin"`` and ``"full"`` instance modes.
    In ``"lite"`` mode the admin surface is disabled.

    Args:
        env: SafeEnv wrapper around Worker environment bindings.

    Returns:
        True if admin features are enabled, False otherwise.
    """
    return get_instance_mode(env) in {"admin", "full"}


def is_search_enabled(env: SafeEnv) -> bool:
    """Check whether Vectorize semantic search and AI features are available.

    Returns ``True`` only for the ``"full"`` instance mode, which is the
    only mode that provisions Vectorize indexes and AI bindings.

    Args:
        env: SafeEnv wrapper around Worker environment bindings.

    Returns:
        True if search features are enabled, False otherwise.
    """
    return get_instance_mode(env) == "full"


def is_lite_mode(env: SafeEnv) -> bool:
    """Check if the instance is running in lite mode.

    Thin backward-compatible wrapper around :func:`get_instance_mode`.

    Args:
        env: SafeEnv wrapper around Worker environment bindings.

    Returns:
        True if running in lite mode, False otherwise.
    """
    return get_instance_mode(env) == "lite"
