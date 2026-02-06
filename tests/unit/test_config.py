# tests/unit/test_config.py
"""Tests for config module."""

from src.config import (
    DEFAULT_EMBEDDING_MAX_CHARS,
    DEFAULT_FEED_AUTO_DEACTIVATE_THRESHOLD,
    DEFAULT_FEED_FAILURE_THRESHOLD,
    DEFAULT_MAX_ENTRIES_PER_FEED,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_SEARCH_SCORE_THRESHOLD,
    DEFAULT_SEARCH_TOP_K,
    FEED_TIMEOUT_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    get_config_value,
    get_embedding_max_chars,
    get_feed_auto_deactivate_threshold,
    get_feed_failure_threshold,
    get_feed_timeout,
    get_http_timeout,
    get_max_entries_per_feed,
    get_planet_config,
    get_retention_days,
    get_search_score_threshold,
    get_search_top_k,
)


class MockEnv:
    """Mock environment for config tests."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name):
        return None


class TestGetConfigValue:
    """Tests for get_config_value()."""

    def test_returns_env_value_as_int(self):
        """Returns environment value converted to int."""
        env = MockEnv(RETENTION_DAYS="30")
        result = get_config_value(env, "RETENTION_DAYS", 90)
        assert result == 30
        assert isinstance(result, int)

    def test_returns_default_when_env_absent(self):
        """Returns default when environment variable is not set."""
        env = MockEnv()
        result = get_config_value(env, "RETENTION_DAYS", 90)
        assert result == 90

    def test_returns_default_on_invalid_value(self):
        """Returns default when environment value is not a valid number."""
        env = MockEnv(RETENTION_DAYS="not_a_number")
        result = get_config_value(env, "RETENTION_DAYS", 90)
        assert result == 90

    def test_float_type_conversion(self):
        """Converts to float when value_type is float."""
        env = MockEnv(SEARCH_SCORE_THRESHOLD="0.5")
        result = get_config_value(env, "SEARCH_SCORE_THRESHOLD", 0.3, float)
        assert result == 0.5
        assert isinstance(result, float)

    def test_int_type_conversion(self):
        """Converts to int by default."""
        env = MockEnv(MAX_ENTRIES_PER_FEED="100")
        result = get_config_value(env, "MAX_ENTRIES_PER_FEED", 50)
        assert result == 100
        assert isinstance(result, int)

    def test_returns_default_for_empty_string(self):
        """Returns default when environment value is empty string (falsy)."""
        env = MockEnv(RETENTION_DAYS="")
        result = get_config_value(env, "RETENTION_DAYS", 90)
        assert result == 90


class TestConfigGetterDefaults:
    """Tests that config getters return correct defaults."""

    def test_get_retention_days_default(self):
        env = MockEnv()
        assert get_retention_days(env) == DEFAULT_RETENTION_DAYS

    def test_get_max_entries_per_feed_default(self):
        env = MockEnv()
        assert get_max_entries_per_feed(env) == DEFAULT_MAX_ENTRIES_PER_FEED

    def test_get_embedding_max_chars_default(self):
        env = MockEnv()
        assert get_embedding_max_chars(env) == DEFAULT_EMBEDDING_MAX_CHARS

    def test_get_search_score_threshold_default(self):
        env = MockEnv()
        result = get_search_score_threshold(env)
        assert result == DEFAULT_SEARCH_SCORE_THRESHOLD
        assert isinstance(result, float)

    def test_get_search_top_k_default(self):
        env = MockEnv()
        assert get_search_top_k(env) == DEFAULT_SEARCH_TOP_K

    def test_get_feed_auto_deactivate_threshold_default(self):
        env = MockEnv()
        assert get_feed_auto_deactivate_threshold(env) == DEFAULT_FEED_AUTO_DEACTIVATE_THRESHOLD

    def test_get_feed_failure_threshold_default(self):
        env = MockEnv()
        assert get_feed_failure_threshold(env) == DEFAULT_FEED_FAILURE_THRESHOLD

    def test_get_feed_timeout_default(self):
        env = MockEnv()
        assert get_feed_timeout(env) == FEED_TIMEOUT_SECONDS

    def test_get_http_timeout_default(self):
        env = MockEnv()
        assert get_http_timeout(env) == HTTP_TIMEOUT_SECONDS


class TestConfigGetterOverrides:
    """Tests that config getters properly read env overrides."""

    def test_get_retention_days_override(self):
        env = MockEnv(RETENTION_DAYS="30")
        assert get_retention_days(env) == 30

    def test_get_search_score_threshold_override(self):
        env = MockEnv(SEARCH_SCORE_THRESHOLD="0.7")
        result = get_search_score_threshold(env)
        assert result == 0.7
        assert isinstance(result, float)

    def test_get_max_entries_per_feed_override(self):
        env = MockEnv(RETENTION_MAX_ENTRIES_PER_FEED="200")
        assert get_max_entries_per_feed(env) == 200


class TestGetPlanetConfig:
    """Tests for get_planet_config()."""

    def test_returns_defaults_when_no_env(self):
        env = MockEnv()
        config = get_planet_config(env)
        assert config["name"] == "Planet CF"
        assert "Aggregated" in config["description"]
        assert config["link"] == "https://planetcf.com"

    def test_returns_env_values_when_set(self):
        env = MockEnv(
            PLANET_NAME="My Planet",
            PLANET_DESCRIPTION="My feeds",
            PLANET_URL="https://example.com",
        )
        config = get_planet_config(env)
        assert config["name"] == "My Planet"
        assert config["description"] == "My feeds"
        assert config["link"] == "https://example.com"
