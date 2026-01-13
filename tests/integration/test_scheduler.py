# tests/integration/test_scheduler.py
"""Integration tests for the scheduler (cron) functionality."""

import pytest

from tests.conftest import MockD1


@pytest.mark.asyncio
async def test_scheduler_enqueues_active_feeds(mock_env_with_feeds):
    """Scheduler should enqueue one message per active feed."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    result = await worker._run_scheduler()

    assert result["enqueued"] == 2
    assert len(mock_env_with_feeds.FEED_QUEUE.messages) == 2

    # Verify message structure
    msg = mock_env_with_feeds.FEED_QUEUE.messages[0]
    assert "feed_id" in msg
    assert "url" in msg
    assert "scheduled_at" in msg


@pytest.mark.asyncio
async def test_scheduler_skips_inactive_feeds(mock_env):
    """Scheduler should not enqueue inactive feeds."""
    mock_env.DB = MockD1({
        "feeds": [
            {"id": 1, "url": "https://active.com/feed", "is_active": 1, "etag": None, "last_modified": None},
            {"id": 2, "url": "https://inactive.com/feed", "is_active": 0, "etag": None, "last_modified": None},
        ]
    })

    from src.main import PlanetCF
    worker = PlanetCF()
    worker.env = mock_env

    result = await worker._run_scheduler()

    # Only active feeds should be enqueued
    assert result["enqueued"] == 1
    assert len(mock_env.FEED_QUEUE.messages) == 1
    assert mock_env.FEED_QUEUE.messages[0]["url"] == "https://active.com/feed"


@pytest.mark.asyncio
async def test_scheduler_with_no_feeds(mock_env):
    """Scheduler handles empty feeds table gracefully."""
    mock_env.DB = MockD1({"feeds": []})

    from src.main import PlanetCF
    worker = PlanetCF()
    worker.env = mock_env

    result = await worker._run_scheduler()

    assert result["enqueued"] == 0
    assert len(mock_env.FEED_QUEUE.messages) == 0


@pytest.mark.asyncio
async def test_scheduler_includes_cache_headers(mock_env):
    """Scheduler includes etag and last_modified in messages."""
    mock_env.DB = MockD1({
        "feeds": [
            {
                "id": 1,
                "url": "https://example.com/feed",
                "is_active": 1,
                "etag": '"abc123"',
                "last_modified": "Sat, 01 Jan 2026 00:00:00 GMT",
            },
        ]
    })

    from src.main import PlanetCF
    worker = PlanetCF()
    worker.env = mock_env

    await worker._run_scheduler()

    msg = mock_env.FEED_QUEUE.messages[0]
    assert msg["etag"] == '"abc123"'
    assert msg["last_modified"] == "Sat, 01 Jan 2026 00:00:00 GMT"


@pytest.mark.asyncio
async def test_scheduler_message_contains_feed_id(mock_env_with_feeds):
    """Each message contains the correct feed_id."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    await worker._run_scheduler()

    feed_ids = {msg["feed_id"] for msg in mock_env_with_feeds.FEED_QUEUE.messages}
    assert feed_ids == {1, 2}
