# tests/unit/test_instance_config.py
"""Tests for instance_config module."""

from src.instance_config import DEFAULTS, _get_env, is_lite_mode


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
