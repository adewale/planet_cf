# tests/unit/test_config_validation.py
"""Tests for config validation: binding/mode mismatch detection.

These tests verify that _validate_config() correctly detects and warns about
misconfigured instances — e.g., full mode without AI/SEARCH_INDEX bindings,
or lite mode with unnecessary bindings.

This would have caught the planet-python bug where queue processing logged
AttributeError on every entry because AI binding was None.
"""

from unittest.mock import patch

import pytest

from tests.conftest import MockAI, MockD1, MockEnv, MockQueue, MockVectorize


def _make_worker(*, instance_mode=None, ai=None, search_index=None):
    """Create a Default worker with specified config for validation testing."""
    from src.main import Default

    env = MockEnv(
        DB=MockD1(),
        FEED_QUEUE=MockQueue(),
        DEAD_LETTER_QUEUE=MockQueue(),
        SEARCH_INDEX=search_index,
        AI=ai,
    )
    if instance_mode is not None:
        env.INSTANCE_MODE = instance_mode

    worker = Default()
    worker.env = env
    return worker


class TestValidateConfig:
    """Tests for Default._validate_config()."""

    def test_full_mode_missing_ai_logs_warning(self):
        """Full mode without AI binding should log a config_warning."""
        worker = _make_worker(instance_mode="full", ai=None, search_index=MockVectorize())

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()

        mock_log.assert_called_once()
        args, kwargs = mock_log.call_args
        assert args[0] == "config_warning"
        assert "AI" in kwargs["message"]
        assert "missing bindings" in kwargs["message"]

    def test_full_mode_missing_search_index_logs_warning(self):
        """Full mode without SEARCH_INDEX binding should log a config_warning."""
        worker = _make_worker(instance_mode="full", ai=MockAI(), search_index=None)

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()

        mock_log.assert_called_once()
        args, kwargs = mock_log.call_args
        assert args[0] == "config_warning"
        assert "SEARCH_INDEX" in kwargs["message"]

    def test_full_mode_missing_both_bindings_logs_warning(self):
        """Full mode without both AI and SEARCH_INDEX should list both in warning."""
        worker = _make_worker(instance_mode="full", ai=None, search_index=None)

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()

        mock_log.assert_called_once()
        args, kwargs = mock_log.call_args
        assert "AI" in kwargs["message"]
        assert "SEARCH_INDEX" in kwargs["message"]

    def test_default_mode_missing_bindings_logs_warning(self):
        """When INSTANCE_MODE is not set (defaults to full), missing bindings should warn."""
        worker = _make_worker(ai=None, search_index=None)

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()

        mock_log.assert_called_once()
        args, kwargs = mock_log.call_args
        assert args[0] == "config_warning"

    def test_lite_mode_no_bindings_no_warning(self):
        """Lite mode without bindings is the expected config — no warning."""
        worker = _make_worker(instance_mode="lite", ai=None, search_index=None)

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()

        mock_log.assert_not_called()

    def test_full_mode_with_all_bindings_no_warning(self):
        """Full mode with all bindings is the expected config — no warning."""
        worker = _make_worker(instance_mode="full", ai=MockAI(), search_index=MockVectorize())

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()

        mock_log.assert_not_called()

    def test_lite_mode_with_bindings_logs_info(self):
        """Lite mode with AI and SEARCH_INDEX bindings should log info about unused cost."""
        worker = _make_worker(instance_mode="lite", ai=MockAI(), search_index=MockVectorize())

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()

        mock_log.assert_called_once()
        args, kwargs = mock_log.call_args
        assert args[0] == "config_warning"
        assert kwargs["severity"] == "info"
        assert "unused" in kwargs["message"].lower()

    def test_runs_only_once(self):
        """_validate_config should only log on first call, not on subsequent calls."""
        worker = _make_worker(instance_mode="full", ai=None, search_index=None)

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()
            worker._validate_config()
            worker._validate_config()

        assert mock_log.call_count == 1


class TestDatabaseInitNoise:
    """Tests that database init doesn't produce noisy logs in steady state."""

    @pytest.mark.asyncio
    async def test_already_initialized_does_not_log(self):
        """When DB is already initialized, _ensure_database_initialized should not log."""
        # Use a DB that has the feeds table (simulates already-initialized)
        worker = _make_worker(instance_mode="lite", ai=None, search_index=None)
        worker.env.DB = MockD1(
            {
                "feeds": [
                    {
                        "id": 1,
                        "url": "https://example.com/feed.xml",
                        "title": "Test",
                        "is_active": 1,
                        "site_url": "https://example.com",
                        "consecutive_failures": 0,
                        "last_success_at": "2026-01-01",
                    }
                ]
            }
        )

        with patch("src.main.log_op") as mock_log_op, patch("src.main.log_error") as mock_log_err:
            await worker._ensure_database_initialized()

        # The already_initialized path should be silent
        for call in mock_log_op.call_args_list:
            args, kwargs = call
            if args[0] == "database_auto_init":
                assert kwargs.get("status") != "already_initialized", (
                    "database_auto_init with status=already_initialized should not be logged"
                )
        # No errors should be logged for a healthy DB
        mock_log_err.assert_not_called()


class TestIndexEntryNoBindings:
    """Tests for _index_entry_for_search when bindings are missing."""

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_ai_missing(self):
        """Should return NotConfigured stats instead of raising AttributeError."""
        worker = _make_worker(instance_mode="lite", ai=None, search_index=MockVectorize())
        stats = await worker._index_entry_for_search(1, "Test", "content")

        assert stats["success"] is False
        assert stats["error_type"] == "NotConfigured"

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_search_index_missing(self):
        """Should return NotConfigured stats instead of raising AttributeError."""
        worker = _make_worker(instance_mode="lite", ai=MockAI(), search_index=None)
        stats = await worker._index_entry_for_search(1, "Test", "content")

        assert stats["success"] is False
        assert stats["error_type"] == "NotConfigured"

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_both_missing(self):
        """Should return NotConfigured stats when both bindings are None."""
        worker = _make_worker(instance_mode="lite", ai=None, search_index=None)
        stats = await worker._index_entry_for_search(1, "Test", "content")

        assert stats["success"] is False
        assert stats["error_type"] == "NotConfigured"
        assert "not available" in stats["error_message"].lower()

    @pytest.mark.asyncio
    async def test_succeeds_when_bindings_present(self):
        """Should succeed when both AI and SEARCH_INDEX are configured."""
        worker = _make_worker(instance_mode="full", ai=MockAI(), search_index=MockVectorize())
        stats = await worker._index_entry_for_search(1, "Test Title", "Test content")

        assert stats["success"] is True
        assert stats["embedding_ms"] >= 0

    @pytest.mark.asyncio
    async def test_empty_vector_returns_error_not_upsert(self):
        """When AI returns 0-dimension embedding, should return InvalidDimensions.

        Defense in depth: validates embedding dimensions before attempting
        the Vectorize upsert.
        """

        class EmptyVectorAI:
            async def run(self, model, inputs):
                return {"data": [[]]}  # 0-dimension embedding

        worker = _make_worker(
            instance_mode="full", ai=EmptyVectorAI(), search_index=MockVectorize()
        )
        stats = await worker._index_entry_for_search(1, "Test Title", "Test content")

        assert stats["success"] is False
        assert stats["error_type"] == "InvalidDimensions"
        assert "got 0" in stats["error_message"]

    @pytest.mark.asyncio
    async def test_memoryview_vector_accepted(self):
        """When AI returns memoryview (Float32Array via Pyodide), should succeed.

        Workers AI returns Float32Array for embeddings. Pyodide's .to_py()
        converts this to memoryview. The code must handle memoryview as a
        valid vector type, not mangle it through str() conversion.
        """
        import array

        class MemoryviewAI:
            async def run(self, model, inputs):
                # Simulate what SafeAI.run() returns after _to_py_safe converts
                # a JsProxy dict containing a Float32Array:
                # Float32Array → memoryview via .to_py()
                arr = array.array("f", [0.1] * 768)
                return {"data": [memoryview(arr)]}

        worker = _make_worker(instance_mode="full", ai=MemoryviewAI(), search_index=MockVectorize())
        stats = await worker._index_entry_for_search(1, "Test Title", "Test content")

        assert stats["success"] is True

    @pytest.mark.asyncio
    async def test_empty_memoryview_vector_rejected(self):
        """Empty memoryview should be caught by dimension validation.

        Defense in depth for typed arrays from other bindings (R2, KV).
        """
        import array

        class EmptyMemoryviewAI:
            async def run(self, model, inputs):
                arr = array.array("f", [])  # 0 dimensions
                return {"data": [memoryview(arr)]}

        worker = _make_worker(
            instance_mode="full", ai=EmptyMemoryviewAI(), search_index=MockVectorize()
        )
        stats = await worker._index_entry_for_search(1, "Test Title", "Test content")

        assert stats["success"] is False
        assert stats["error_type"] == "InvalidDimensions"
        assert "got 0" in stats["error_message"]

    @pytest.mark.asyncio
    async def test_wrong_dimension_memoryview_rejected(self):
        """Memoryview with wrong dimensions (not 768) should be caught."""
        import array

        class WrongDimAI:
            async def run(self, model, inputs):
                arr = array.array("f", [0.1] * 384)  # Wrong: 384 instead of 768
                return {"data": [memoryview(arr)]}

        worker = _make_worker(instance_mode="full", ai=WrongDimAI(), search_index=MockVectorize())
        stats = await worker._index_entry_for_search(1, "Test Title", "Test content")

        assert stats["success"] is False
        assert stats["error_type"] == "InvalidDimensions"
        assert "got 384" in stats["error_message"]
