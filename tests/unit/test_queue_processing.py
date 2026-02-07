# tests/unit/test_queue_processing.py
"""Unit tests for queue() batch processing in src/main.py."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from src.main import Default

# =============================================================================
# Mock infrastructure for queue tests
# =============================================================================


class MockMessage:
    """Mock queue message."""

    def __init__(self, body: dict | None = None, msg_id: str = "msg-1", attempts: int = 1):
        self.body = body
        self.id = msg_id
        self.attempts = attempts
        self.acked = False
        self.retried = False

    def ack(self):
        self.acked = True

    def retry(self):
        self.retried = True


class MockBatch:
    """Mock queue batch."""

    def __init__(self, messages: list[MockMessage]):
        self.messages = messages

    def __len__(self):
        return len(self.messages)


@dataclass
class MockD1Result:
    """Mock D1 query result."""

    results: list[dict]
    success: bool = True


class MockD1Statement:
    """Mock D1 prepared statement."""

    def __init__(self):
        self.sql = ""
        self.bound_args: list = []

    def bind(self, *args) -> "MockD1Statement":
        self.bound_args = list(args)
        return self

    async def all(self) -> MockD1Result:
        return MockD1Result(results=[])

    async def first(self) -> dict | None:
        return None

    async def run(self) -> MockD1Result:
        return MockD1Result(results=[])


class MockD1ForQueue:
    """Mock D1 database for queue tests."""

    def __init__(self):
        self.statements: list[MockD1Statement] = []

    def prepare(self, sql: str) -> MockD1Statement:
        stmt = MockD1Statement()
        stmt.sql = sql
        self.statements.append(stmt)
        return stmt


class MockQueueEnv:
    """Mock environment for queue tests."""

    def __init__(self):
        self.DB = MockD1ForQueue()
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = None
        self.DEAD_LETTER_QUEUE = None
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"


# =============================================================================
# Queue Processing Tests
# =============================================================================


class TestQueueBatchProcessing:
    """Tests for Default.queue() batch processing."""

    @pytest.mark.asyncio
    async def test_single_valid_feed_processed(self):
        """Single valid feed in batch is processed and acknowledged."""
        env = MockQueueEnv()
        worker = Default()
        worker.env = env

        msg = MockMessage(
            body={
                "feed_id": 1,
                "url": "https://example.com/feed.xml",
                "etag": None,
                "last_modified": None,
                "correlation_id": "test-corr-1",
            }
        )
        batch = MockBatch([msg])

        # Mock _process_single_feed to return success
        with patch.object(
            worker,
            "_process_single_feed",
            new_callable=AsyncMock,
            return_value={"entries_added": 3, "entries_found": 5},
        ):
            await worker.queue(batch)

        assert msg.acked is True
        assert msg.retried is False

    @pytest.mark.asyncio
    async def test_feed_exception_records_error_doesnt_crash(self):
        """Feed that throws exception records error and retries, doesn't crash batch."""
        env = MockQueueEnv()
        worker = Default()
        worker.env = env

        msg1 = MockMessage(
            body={
                "feed_id": 1,
                "url": "https://failing.com/feed.xml",
                "correlation_id": "corr-1",
            },
            msg_id="msg-1",
        )
        msg2 = MockMessage(
            body={
                "feed_id": 2,
                "url": "https://ok.com/feed.xml",
                "correlation_id": "corr-2",
            },
            msg_id="msg-2",
        )
        batch = MockBatch([msg1, msg2])

        call_count = 0

        async def mock_process(job, event=None):
            nonlocal call_count
            call_count += 1
            if job["feed_id"] == 1:
                raise ValueError("Parse error")
            return {"entries_added": 1, "entries_found": 1}

        with (
            patch.object(worker, "_process_single_feed", side_effect=mock_process),
            patch.object(worker, "_record_feed_error", new_callable=AsyncMock),
        ):
            await worker.queue(batch)

        # First message failed -> retry
        assert msg1.retried is True
        assert msg1.acked is False
        # Second message succeeded -> ack
        assert msg2.acked is True
        assert msg2.retried is False
        # Both messages were processed
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_empty_batch_is_noop(self):
        """Empty batch processes without error."""
        env = MockQueueEnv()
        worker = Default()
        worker.env = env

        batch = MockBatch([])

        # Should complete without error
        await worker.queue(batch)

    @pytest.mark.asyncio
    async def test_invalid_message_body_acked(self):
        """Message with invalid body is acknowledged (not retried)."""
        env = MockQueueEnv()
        worker = Default()
        worker.env = env

        # None body
        msg = MockMessage(body=None)
        batch = MockBatch([msg])

        await worker.queue(batch)

        assert msg.acked is True
        assert msg.retried is False

    @pytest.mark.asyncio
    async def test_timeout_retries_message(self):
        """Feed that times out is retried."""
        env = MockQueueEnv()
        worker = Default()
        worker.env = env

        msg = MockMessage(
            body={
                "feed_id": 1,
                "url": "https://slow.com/feed.xml",
                "correlation_id": "corr-1",
            }
        )
        batch = MockBatch([msg])

        async def mock_slow_process(job, event=None):
            raise TimeoutError("Took too long")

        with (
            patch.object(worker, "_process_single_feed", side_effect=mock_slow_process),
            patch.object(worker, "_record_feed_error", new_callable=AsyncMock),
            patch("asyncio.wait_for", side_effect=TimeoutError("Timeout")),
        ):
            await worker.queue(batch)

        assert msg.retried is True
        assert msg.acked is False
