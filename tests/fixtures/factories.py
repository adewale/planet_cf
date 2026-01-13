# tests/fixtures/factories.py
"""Factory functions for creating test data."""

import time
from typing import Any

from src.types import EntryRow, FeedId, FeedJob, FeedRow, Session


class FeedFactory:
    """Factory for creating test feed data."""
    _counter = 0

    @classmethod
    def create(cls, **overrides: Any) -> FeedRow:
        """Create a FeedRow with default values."""
        cls._counter += 1
        defaults: FeedRow = {
            "id": cls._counter,
            "url": f"https://feed{cls._counter}.example.com/rss",
            "title": f"Test Feed {cls._counter}",
            "site_url": f"https://feed{cls._counter}.example.com",
            "is_active": 1,
            "consecutive_failures": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        return {**defaults, **overrides}

    @classmethod
    def create_batch(cls, count: int, **overrides: Any) -> list[FeedRow]:
        """Create multiple FeedRows."""
        return [cls.create(**overrides) for _ in range(count)]

    @classmethod
    def reset(cls) -> None:
        """Reset the counter."""
        cls._counter = 0


class EntryFactory:
    """Factory for creating test entry data."""
    _counter = 0

    @classmethod
    def create(cls, feed_id: int = 1, **overrides: Any) -> EntryRow:
        """Create an EntryRow with default values."""
        cls._counter += 1
        defaults: EntryRow = {
            "id": cls._counter,
            "feed_id": feed_id,
            "guid": f"entry-{cls._counter}",
            "url": f"https://example.com/post/{cls._counter}",
            "title": f"Test Entry {cls._counter}",
            "content": "<p>Test content</p>",
            "published_at": "2026-01-01T12:00:00Z",
            "created_at": "2026-01-01T12:00:00Z",
        }
        return {**defaults, **overrides}

    @classmethod
    def create_batch(cls, count: int, feed_id: int = 1, **overrides: Any) -> list[EntryRow]:
        """Create multiple EntryRows."""
        return [cls.create(feed_id=feed_id, **overrides) for _ in range(count)]

    @classmethod
    def reset(cls) -> None:
        """Reset the counter."""
        cls._counter = 0


class FeedJobFactory:
    """Factory for creating test FeedJob data."""
    _counter = 0

    @classmethod
    def create(cls, **overrides: Any) -> FeedJob:
        """Create a FeedJob with default values."""
        cls._counter += 1
        defaults = {
            "feed_id": FeedId(cls._counter),
            "feed_url": f"https://feed{cls._counter}.example.com/rss",
            "etag": None,
            "last_modified": None,
        }
        merged = {**defaults, **overrides}
        return FeedJob(**merged)

    @classmethod
    def create_batch(cls, count: int, **overrides: Any) -> list[FeedJob]:
        """Create multiple FeedJobs."""
        return [cls.create(**overrides) for _ in range(count)]

    @classmethod
    def reset(cls) -> None:
        """Reset the counter."""
        cls._counter = 0


class SessionFactory:
    """Factory for creating test Session data."""

    @classmethod
    def create(cls, **overrides: Any) -> Session:
        """Create a Session with default values."""
        defaults = {
            "github_username": "testuser",
            "github_id": 12345,
            "avatar_url": "https://github.com/testuser.png",
            "exp": int(time.time()) + 3600,  # 1 hour from now
        }
        merged = {**defaults, **overrides}
        return Session(**merged)

    @classmethod
    def create_expired(cls, **overrides: Any) -> Session:
        """Create an expired Session."""
        overrides["exp"] = int(time.time()) - 1
        return cls.create(**overrides)

    @classmethod
    def create_long_lived(cls, days: int = 7, **overrides: Any) -> Session:
        """Create a long-lived Session."""
        overrides["exp"] = int(time.time()) + (days * 24 * 60 * 60)
        return cls.create(**overrides)
