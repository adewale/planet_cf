# tests/unit/test_instance_config.py
"""Tests for instance_config module."""

from src.instance_config import (
    DEFAULTS,
    _VALID_MODES,
    _get_env,
    get_instance_mode,
    is_admin_enabled,
    is_lite_mode,
    is_search_enabled,
)


class MockEnv:
    """Mock environment that simulates SafeEnv attribute access.

    Attributes return their value or None (via __getattr__).
    """

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name):
        # Return None for any unset attribute (like SafeEnv does)
        return None


class TestIsLiteMode:
    """Tests for the is_lite_mode() function."""

    def test_returns_true_for_lite(self):
        """Lite mode string returns True."""
        env = MockEnv(INSTANCE_MODE="lite")
        assert is_lite_mode(env) is True

    def test_returns_false_for_full(self):
        """Full mode string returns False."""
        env = MockEnv(INSTANCE_MODE="full")
        assert is_lite_mode(env) is False

    def test_returns_false_for_default(self):
        """When INSTANCE_MODE is not set, defaults to full (False)."""
        env = MockEnv()
        assert is_lite_mode(env) is False

    def test_case_insensitive_lite(self):
        """LITE (uppercase) returns True."""
        env = MockEnv(INSTANCE_MODE="LITE")
        assert is_lite_mode(env) is True

    def test_case_insensitive_mixed(self):
        """Lite (mixed case) returns True."""
        env = MockEnv(INSTANCE_MODE="Lite")
        assert is_lite_mode(env) is True

    def test_case_insensitive_full(self):
        """FULL (uppercase) returns False."""
        env = MockEnv(INSTANCE_MODE="FULL")
        assert is_lite_mode(env) is False


class TestGetInstanceMode:
    """Tests for the get_instance_mode() function."""

    def test_returns_full_by_default(self):
        """When INSTANCE_MODE is not set, defaults to 'full'."""
        env = MockEnv()
        assert get_instance_mode(env) == "full"

    def test_returns_lite(self):
        """INSTANCE_MODE='lite' returns 'lite'."""
        env = MockEnv(INSTANCE_MODE="lite")
        assert get_instance_mode(env) == "lite"

    def test_returns_admin(self):
        """INSTANCE_MODE='admin' returns 'admin'."""
        env = MockEnv(INSTANCE_MODE="admin")
        assert get_instance_mode(env) == "admin"

    def test_returns_full(self):
        """INSTANCE_MODE='full' returns 'full'."""
        env = MockEnv(INSTANCE_MODE="full")
        assert get_instance_mode(env) == "full"

    def test_case_insensitive(self):
        """INSTANCE_MODE='ADMIN' returns 'admin'."""
        env = MockEnv(INSTANCE_MODE="ADMIN")
        assert get_instance_mode(env) == "admin"

    def test_unknown_value_defaults_to_full(self):
        """Unrecognized INSTANCE_MODE values default to 'full'."""
        env = MockEnv(INSTANCE_MODE="invalid")
        assert get_instance_mode(env) == "full"


class TestIsAdminEnabled:
    """Tests for the is_admin_enabled() function."""

    def test_true_for_full(self):
        """Admin is enabled in full mode."""
        env = MockEnv(INSTANCE_MODE="full")
        assert is_admin_enabled(env) is True

    def test_true_for_admin(self):
        """Admin is enabled in admin mode."""
        env = MockEnv(INSTANCE_MODE="admin")
        assert is_admin_enabled(env) is True

    def test_false_for_lite(self):
        """Admin is disabled in lite mode."""
        env = MockEnv(INSTANCE_MODE="lite")
        assert is_admin_enabled(env) is False


class TestIsSearchEnabled:
    """Tests for the is_search_enabled() function."""

    def test_true_for_full(self):
        """Search is enabled in full mode."""
        env = MockEnv(INSTANCE_MODE="full")
        assert is_search_enabled(env) is True

    def test_false_for_admin(self):
        """Search is disabled in admin mode."""
        env = MockEnv(INSTANCE_MODE="admin")
        assert is_search_enabled(env) is False

    def test_false_for_lite(self):
        """Search is disabled in lite mode."""
        env = MockEnv(INSTANCE_MODE="lite")
        assert is_search_enabled(env) is False


class TestGetEnv:
    """Tests for the _get_env() helper function."""

    def test_returns_env_value_when_present(self):
        """Returns the environment variable value when set."""
        env = MockEnv(PLANET_NAME="My Planet")
        result = _get_env(env, "PLANET_NAME")
        assert result == "My Planet"

    def test_returns_explicit_default_when_env_missing(self):
        """Returns the explicit default when env var is not set."""
        env = MockEnv()
        result = _get_env(env, "NONEXISTENT_KEY", "my_default")
        assert result == "my_default"

    def test_returns_defaults_dict_value_when_no_explicit_default(self):
        """Returns the DEFAULTS dict value when env var is not set and no explicit default."""
        env = MockEnv()
        result = _get_env(env, "INSTANCE_MODE")
        assert result == DEFAULTS["INSTANCE_MODE"]

    def test_returns_empty_string_when_no_default_found(self):
        """Returns empty string when key is not in env, no explicit default, and not in DEFAULTS."""
        env = MockEnv()
        result = _get_env(env, "COMPLETELY_UNKNOWN_KEY")
        assert result == ""

    def test_converts_value_to_string(self):
        """Non-string env values are converted to strings."""
        env = MockEnv(SOME_INT=42)
        result = _get_env(env, "SOME_INT")
        assert result == "42"

    def test_env_value_takes_precedence_over_default(self):
        """Env value is preferred over explicit default."""
        env = MockEnv(PLANET_NAME="From Env")
        result = _get_env(env, "PLANET_NAME", "From Default")
        assert result == "From Env"
