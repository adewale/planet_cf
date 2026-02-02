# src/config.py
"""Configuration management for Planet CF.

Environment-based configuration with type-safe getters and defaults.
These functions take an env object and return configuration values.
"""

from typing import Any

from utils import log_op

# =============================================================================
# Constants
# =============================================================================

# Timeouts
FEED_TIMEOUT_SECONDS = 60  # Max wall time per feed
HTTP_TIMEOUT_SECONDS = 30  # HTTP request timeout

# User agent for feed fetching
USER_AGENT = "PlanetCF/1.0 (+https://planetcf.com; contact@planetcf.com)"

# Security limits
MAX_SEARCH_QUERY_LENGTH = 1000  # Max search query length
MAX_SEARCH_WORDS = 10  # Max words in multi-word search
MAX_OPML_FEEDS = 100  # Max feeds per OPML import
REINDEX_COOLDOWN_SECONDS = 300  # 5 minute cooldown between reindex

# Retention policy defaults
DEFAULT_RETENTION_DAYS = 90
DEFAULT_MAX_ENTRIES_PER_FEED = 50

# Search defaults
DEFAULT_EMBEDDING_MAX_CHARS = 2000
DEFAULT_SEARCH_SCORE_THRESHOLD = 0.3
DEFAULT_SEARCH_TOP_K = 50

# Feed failure thresholds
DEFAULT_FEED_AUTO_DEACTIVATE_THRESHOLD = 10
DEFAULT_FEED_FAILURE_THRESHOLD = 3


# =============================================================================
# Configuration Getters
# =============================================================================


def get_config_value(
    env: Any,
    env_key: str,
    default: int | float,
    value_type: type[int] | type[float] = int,
) -> int | float:
    """Get a configuration value from environment with type conversion.

    Args:
        env: The Worker environment object
        env_key: The environment variable name
        default: Default value if not set or on error
        value_type: Type to convert to (int or float)

    Returns:
        The configured value or default.
    """
    try:
        value = getattr(env, env_key, None)
        return value_type(value) if value else default
    except (ValueError, TypeError) as e:
        log_op(
            "config_validation_error",
            config_key=env_key,
            error=str(e),
        )
        return default


def get_planet_config(env: Any) -> dict[str, str]:
    """Get planet configuration from environment.

    Returns:
        Dict with name, description, and link.
    """
    return {
        "name": getattr(env, "PLANET_NAME", None) or "Planet CF",
        "description": getattr(env, "PLANET_DESCRIPTION", None)
        or "Aggregated posts from Cloudflare employees and community",
        "link": getattr(env, "PLANET_URL", None) or "https://planetcf.com",
    }


# =============================================================================
# Config Registry
# =============================================================================

# Registry of integer config values: (env_key, default_value)
_INT_CONFIG_REGISTRY: dict[str, tuple[str, int]] = {
    "retention_days": ("RETENTION_DAYS", DEFAULT_RETENTION_DAYS),
    "max_entries_per_feed": ("MAX_ENTRIES_PER_FEED", DEFAULT_MAX_ENTRIES_PER_FEED),
    "embedding_max_chars": ("EMBEDDING_MAX_CHARS", DEFAULT_EMBEDDING_MAX_CHARS),
    "search_top_k": ("SEARCH_TOP_K", DEFAULT_SEARCH_TOP_K),
    "feed_auto_deactivate_threshold": (
        "FEED_AUTO_DEACTIVATE_THRESHOLD",
        DEFAULT_FEED_AUTO_DEACTIVATE_THRESHOLD,
    ),
    "feed_failure_threshold": ("FEED_FAILURE_THRESHOLD", DEFAULT_FEED_FAILURE_THRESHOLD),
    "feed_timeout": ("FEED_TIMEOUT", FEED_TIMEOUT_SECONDS),
    "http_timeout": ("HTTP_TIMEOUT", HTTP_TIMEOUT_SECONDS),
}


def _get_int_config(env: Any, config_name: str) -> int:
    """Get an integer config value from the registry."""
    env_key, default = _INT_CONFIG_REGISTRY[config_name]
    return int(get_config_value(env, env_key, default))


# Convenience functions that use the registry
def get_retention_days(env: Any) -> int:
    """Get entry retention period in days."""
    return _get_int_config(env, "retention_days")


def get_max_entries_per_feed(env: Any) -> int:
    """Get maximum entries to keep per feed."""
    return _get_int_config(env, "max_entries_per_feed")


def get_embedding_max_chars(env: Any) -> int:
    """Get maximum characters to embed per entry."""
    return _get_int_config(env, "embedding_max_chars")


def get_search_score_threshold(env: Any) -> float:
    """Get minimum similarity score for search results."""
    return float(
        get_config_value(env, "SEARCH_SCORE_THRESHOLD", DEFAULT_SEARCH_SCORE_THRESHOLD, float)
    )


def get_search_top_k(env: Any) -> int:
    """Get max semantic search results before filtering."""
    return _get_int_config(env, "search_top_k")


def get_feed_auto_deactivate_threshold(env: Any) -> int:
    """Get consecutive failures before auto-deactivating a feed."""
    return _get_int_config(env, "feed_auto_deactivate_threshold")


def get_feed_failure_threshold(env: Any) -> int:
    """Get consecutive failures before marking feed as unhealthy."""
    return _get_int_config(env, "feed_failure_threshold")


def get_feed_timeout(env: Any) -> int:
    """Get per-feed processing timeout in seconds."""
    return _get_int_config(env, "feed_timeout")


def get_http_timeout(env: Any) -> int:
    """Get HTTP request timeout in seconds."""
    return _get_int_config(env, "http_timeout")
