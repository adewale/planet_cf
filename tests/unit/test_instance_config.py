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
        # Return type is strictly bool, not truthy int
        assert type(is_lite_mode(env)) is bool
        # Unrelated env var should not affect result
        env2 = MockEnv(INSTANCE_MODE="lite", PLANET_NAME="Irrelevant")
        assert is_lite_mode(env2) is True

    def test_returns_false_for_full(self):
        """Full mode string returns False."""
        env = MockEnv(INSTANCE_MODE="full")
        assert is_lite_mode(env) is False
        assert type(is_lite_mode(env)) is bool
        # Ensure it's actually reading the INSTANCE_MODE var, not returning a constant
        env_lite = MockEnv(INSTANCE_MODE="lite")
        assert is_lite_mode(env_lite) is True

    def test_returns_false_for_default(self):
        """When INSTANCE_MODE is not set, defaults to full (False)."""
        env = MockEnv()
        assert is_lite_mode(env) is False
        # Verify the default in DEFAULTS dict matches the behavior
        assert DEFAULTS["INSTANCE_MODE"] == "full"
        # Setting it explicitly to "full" should give the same result as default
        env_explicit = MockEnv(INSTANCE_MODE="full")
        assert is_lite_mode(env_explicit) is False

    def test_case_insensitive_lite(self):
        """LITE (uppercase) returns True."""
        env = MockEnv(INSTANCE_MODE="LITE")
        assert is_lite_mode(env) is True
        # Also verify the underlying _get_env returns the raw value before lowering
        raw = _get_env(env, "INSTANCE_MODE")
        assert raw == "LITE"
        assert type(is_lite_mode(env)) is bool

    def test_case_insensitive_mixed(self):
        """Lite (mixed case) returns True."""
        env = MockEnv(INSTANCE_MODE="Lite")
        assert is_lite_mode(env) is True
        # Verify the raw value is preserved (lowering happens in is_lite_mode, not _get_env)
        raw = _get_env(env, "INSTANCE_MODE")
        assert raw == "Lite"
        assert type(is_lite_mode(env)) is bool

    def test_case_insensitive_full(self):
        """FULL (uppercase) returns False."""
        env = MockEnv(INSTANCE_MODE="FULL")
        assert is_lite_mode(env) is False
        # An arbitrary string that isn't "lite" should also be False
        env_other = MockEnv(INSTANCE_MODE="FULL")
        assert is_lite_mode(env_other) is False
        # Verify that _get_env preserves the original casing
        assert _get_env(env, "INSTANCE_MODE") == "FULL"


class TestGetEnv:
    """Tests for the _get_env() helper function."""

    def test_returns_env_value_when_present(self):
        """Returns the environment variable value when set."""
        env = MockEnv(PLANET_NAME="My Planet")
        result = _get_env(env, "PLANET_NAME")
        assert result == "My Planet"
        assert isinstance(result, str)
        # An unrelated env var should not be returned
        assert _get_env(env, "SOME_OTHER_KEY") != "My Planet"

    def test_returns_explicit_default_when_env_missing(self):
        """Returns the explicit default when env var is not set."""
        env = MockEnv()
        result = _get_env(env, "NONEXISTENT_KEY", "my_default")
        assert result == "my_default"
        assert isinstance(result, str)
        # Setting the env var should override the default
        env_with_val = MockEnv(NONEXISTENT_KEY="from_env")
        assert _get_env(env_with_val, "NONEXISTENT_KEY", "my_default") == "from_env"

    def test_returns_defaults_dict_value_when_no_explicit_default(self):
        """Returns the DEFAULTS dict value when env var is not set and no explicit default."""
        env = MockEnv()
        result = _get_env(env, "INSTANCE_MODE")
        assert result == DEFAULTS["INSTANCE_MODE"]
        assert result == "full"
        assert isinstance(result, str)

    def test_returns_empty_string_when_no_default_found(self):
        """Returns empty string when key is not in env, no explicit default, and not in DEFAULTS."""
        env = MockEnv()
        result = _get_env(env, "COMPLETELY_UNKNOWN_KEY")
        assert result == ""
        assert isinstance(result, str)
        # Ensure the key is genuinely absent from DEFAULTS
        assert "COMPLETELY_UNKNOWN_KEY" not in DEFAULTS

    def test_converts_value_to_string(self):
        """Non-string env values are converted to strings."""
        env = MockEnv(SOME_INT=42)
        result = _get_env(env, "SOME_INT")
        assert result == "42"
        assert isinstance(result, str)
        # Verify it's a string "42", not the int 42
        assert result != 42

    def test_env_value_takes_precedence_over_default(self):
        """Env value is preferred over explicit default."""
        env = MockEnv(PLANET_NAME="From Env")
        result = _get_env(env, "PLANET_NAME", "From Default")
        assert result == "From Env"
        assert result != "From Default"
        # Without the env var, the default wins
        env_empty = MockEnv()
        assert _get_env(env_empty, "PLANET_NAME", "From Default") == "From Default"
