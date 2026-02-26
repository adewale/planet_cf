# tests/unit/test_queue_dlq_and_errors.py
"""Tests for untested queue consumer paths in src/main.py.

Covers:
- Lines 780-791: DLQ consumer - log and ack permanently failed messages
- Lines 848-858: RateLimitError handling in queue consumer
- Lines 917-937: HTTP event population and rate-limit detection in _process_single_feed
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import Default, RateLimitError

# =============================================================================
# Mock Infrastructure
# =============================================================================


class MockMessage:
    """Mock queue message with ack/retry tracking."""

    def __init__(
        self,
        body: dict | str | None = None,
        message_id: str = "msg-1",
        attempts: int = 1,
    ):
        self.body = body
        self.id = message_id
        self.attempts = attempts
        self._acked = False
        self._retried = False

    def ack(self):
        self._acked = True

    def retry(self):
        self._retried = True


class MockBatch:
    """Mock queue batch with queue name attribute."""

    def __init__(self, messages: list[MockMessage], queue: str = "feed-queue"):
        self.messages = messages
        self.queue = queue

    def __len__(self):
        return len(self.messages)


class _MockD1Statement:
    """Minimal D1 statement for queue tests."""

    def bind(self, *args):
        return self

    async def all(self):
        from tests.conftest import MockD1Result

        return MockD1Result(results=[])

    async def first(self):
        return None

    async def run(self):
        from tests.conftest import MockD1Result

        return MockD1Result(results=[])


class _MockD1:
    """Minimal D1 database for queue tests."""

    def prepare(self, sql: str):
        return _MockD1Statement()


class _QueueEnv:
    """Mock environment for queue tests."""

    def __init__(self):
        self.DB = _MockD1()
        self.AI = None
        self.SEARCH_INDEX = None
        self.FEED_QUEUE = None
        self.DEAD_LETTER_QUEUE = None
        self.PLANET_NAME = "Test Planet"
        self.SESSION_SECRET = "test-secret-key-for-testing-only-32chars"  # pragma: allowlist secret
        self.GITHUB_CLIENT_ID = "test-client-id"
        self.GITHUB_CLIENT_SECRET = "test-client-secret"  # pragma: allowlist secret


def _make_worker():
    """Create a Default worker with queue test environment."""
    env = _QueueEnv()
    worker = Default()
    worker.env = env
    return worker, env


# =============================================================================
# Tests: DLQ Consumer Path (Lines 780-791)
# =============================================================================


class TestDLQConsumerPath:
    """Tests for the dead letter queue consumer branch in queue().

    When the batch queue name contains 'dlq', messages should be logged
    and acknowledged without any feed processing.
    """

    @pytest.mark.asyncio
    async def test_dlq_messages_acked_not_processed(self):
        """DLQ messages are acknowledged without calling _process_single_feed."""
        worker, _env = _make_worker()
        msg = MockMessage(body={"feed_id": 42, "url": "https://example.com/feed"})
        batch = MockBatch(messages=[msg], queue="feed-queue-dlq")

        with patch.object(worker, "_process_single_feed") as mock_process:
            await worker.queue(batch)

        assert msg._acked is True
        assert msg._retried is False
        mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_dlq_batch_acks_all_messages(self):
        """All messages in a DLQ batch are acknowledged."""
        worker, _env = _make_worker()
        messages = [
            MockMessage(body={"feed_id": i, "url": f"https://feed{i}.com/rss"}) for i in range(5)
        ]
        batch = MockBatch(messages=messages, queue="my-app-dlq")

        await worker.queue(batch)

        for m in messages:
            assert m._acked is True
            assert m._retried is False

    @pytest.mark.asyncio
    async def test_dlq_handles_non_dict_body_gracefully(self):
        """DLQ consumer handles messages with non-dict bodies (e.g., string)."""
        worker, _env = _make_worker()
        msg = MockMessage(body="corrupt-message-body")
        batch = MockBatch(messages=[msg], queue="feed-DLQ")

        # Should not raise
        await worker.queue(batch)

        assert msg._acked is True

    @pytest.mark.asyncio
    async def test_dlq_handles_empty_dict_body(self):
        """DLQ consumer handles messages with empty dict (missing feed_id/url)."""
        worker, _env = _make_worker()
        msg = MockMessage(body={})
        batch = MockBatch(messages=[msg], queue="dead-letter-dlq")

        await worker.queue(batch)

        assert msg._acked is True

    @pytest.mark.asyncio
    async def test_dlq_detection_case_insensitive(self):
        """DLQ detection checks queue name case-insensitively."""
        worker, _env = _make_worker()
        msg = MockMessage(body={"feed_id": 1, "url": "https://x.com/feed"})

        for queue_name in ["feed-DLQ", "MY_DLQ_QUEUE", "DLQ", "prefix-dlq-suffix"]:
            msg._acked = False
            msg._retried = False
            batch = MockBatch(messages=[msg], queue=queue_name)
            await worker.queue(batch)
            assert msg._acked is True, f"Failed for queue name: {queue_name}"

    @pytest.mark.asyncio
    async def test_dlq_returns_early_before_normal_processing(self):
        """DLQ path returns before the normal feed processing loop runs."""
        worker, _env = _make_worker()
        msg = MockMessage(body={"feed_id": 1, "url": "https://x.com/feed"})
        batch = MockBatch(messages=[msg], queue="feed-dlq")

        # If DLQ path doesn't return early, _process_single_feed would be called
        with patch.object(
            worker,
            "_process_single_feed",
            side_effect=AssertionError("Should not be called for DLQ"),
        ):
            await worker.queue(batch)

        assert msg._acked is True


# =============================================================================
# Tests: RateLimitError Handling in Queue Consumer (Lines 848-858)
# =============================================================================


class TestQueueRateLimitErrorHandling:
    """Tests for RateLimitError exception handling in the queue consumer.

    When _process_single_feed raises RateLimitError, the message should be
    retried (not acked), and _record_feed_error should NOT be called.
    """

    @pytest.mark.asyncio
    async def test_rate_limit_retries_message(self):
        """RateLimitError causes message retry, not ack."""
        worker, _env = _make_worker()
        msg = MockMessage(
            body={"feed_id": 1, "url": "https://example.com/feed"},
        )
        batch = MockBatch(messages=[msg], queue="feed-queue")

        with patch.object(
            worker,
            "_process_single_feed",
            side_effect=RateLimitError("Rate limited (HTTP 429)", "3600"),
        ):
            await worker.queue(batch)

        assert msg._retried is True
        assert msg._acked is False

    @pytest.mark.asyncio
    async def test_rate_limit_does_not_record_feed_error(self):
        """RateLimitError should NOT call _record_feed_error (not a real failure)."""
        worker, _env = _make_worker()
        msg = MockMessage(
            body={"feed_id": 1, "url": "https://example.com/feed"},
        )
        batch = MockBatch(messages=[msg], queue="feed-queue")

        with (
            patch.object(
                worker,
                "_process_single_feed",
                side_effect=RateLimitError("Rate limited (HTTP 429)", "3600"),
            ),
            patch.object(worker, "_record_feed_error", new_callable=AsyncMock) as mock_record,
        ):
            await worker.queue(batch)

        mock_record.assert_not_called()


# =============================================================================
# Tests: HTTP Response Handling in _process_single_feed (Lines 917-937)
# =============================================================================


class TestProcessSingleFeedHttpResponse:
    """Tests for HTTP response event population and rate limit detection.

    Covers the code that:
    1. Populates FeedFetchEvent with HTTP details (lines 917-923)
    2. Validates redirect URLs for SSRF (line 926-927)
    3. Raises RateLimitError on 429/503 (lines 931-937)
    """

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error_with_retry_after(self):
        """HTTP 429 with Retry-After header raises RateLimitError with retry_after set."""
        worker, _env = _make_worker()
        job = {"feed_id": 1, "url": "https://example.com/feed.xml"}

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.final_url = "https://example.com/feed.xml"
        mock_response.headers = {"retry-after": "600"}
        mock_response.text = ""

        with (
            patch("src.main.safe_http_fetch", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(RateLimitError) as exc_info,
        ):
            await worker._process_single_feed(job)

        assert "429" in str(exc_info.value)
        assert exc_info.value.retry_after == "600"

    @pytest.mark.asyncio
    async def test_503_raises_rate_limit_error_without_retry_after(self):
        """HTTP 503 without Retry-After header raises RateLimitError with retry_after=None."""
        worker, _env = _make_worker()
        job = {"feed_id": 1, "url": "https://example.com/feed.xml"}

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.final_url = "https://example.com/feed.xml"
        mock_response.headers = {}
        mock_response.text = ""

        with (
            patch("src.main.safe_http_fetch", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(RateLimitError) as exc_info,
        ):
            await worker._process_single_feed(job)

        assert "503" in str(exc_info.value)
        assert exc_info.value.retry_after is None

    @pytest.mark.asyncio
    async def test_event_populated_with_http_details(self):
        """FeedFetchEvent fields are populated from HTTP response metadata."""
        from src.observability import FeedFetchEvent

        worker, _env = _make_worker()
        job = {"feed_id": 1, "url": "https://example.com/feed.xml"}
        event = FeedFetchEvent(feed_id=1, feed_url="https://example.com/feed.xml")

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.final_url = "https://example.com/feed.xml"
        mock_response.headers = {"retry-after": "300", "etag": '"abc123"'}
        mock_response.text = ""

        with (
            patch("src.main.safe_http_fetch", new_callable=AsyncMock, return_value=mock_response),
            contextlib.suppress(RateLimitError),
        ):
            await worker._process_single_feed(job, event)

        # Event should be populated before the exception
        assert event.http_status == 429
        assert event.http_cached is False
        assert event.http_redirected is False
        assert event.etag_present is True

    @pytest.mark.asyncio
    async def test_event_records_redirect(self):
        """FeedFetchEvent records when the response was redirected."""
        from src.observability import FeedFetchEvent

        worker, _env = _make_worker()
        job = {"feed_id": 1, "url": "https://old.example.com/feed.xml"}
        event = FeedFetchEvent(feed_id=1, feed_url="https://old.example.com/feed.xml")

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.final_url = "https://new.example.com/feed.xml"
        mock_response.headers = {"retry-after": "60"}
        mock_response.text = ""

        with (
            patch("src.main.safe_http_fetch", new_callable=AsyncMock, return_value=mock_response),
            contextlib.suppress(RateLimitError),
        ):
            await worker._process_single_feed(job, event)

        assert event.http_redirected is True

    @pytest.mark.asyncio
    async def test_redirect_to_private_ip_raises_ssrf(self):
        """Redirect to private/metadata IP raises ValueError for SSRF protection."""
        worker, _env = _make_worker()
        job = {"feed_id": 1, "url": "https://example.com/feed.xml"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.final_url = "http://169.254.169.254/latest/meta-data/"
        mock_response.headers = {}
        mock_response.text = "<rss></rss>"

        with (
            patch("src.main.safe_http_fetch", new_callable=AsyncMock, return_value=mock_response),
            pytest.raises(ValueError, match="SSRF"),
        ):
            await worker._process_single_feed(job)
