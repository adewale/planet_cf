# tests/unit/test_observability.py
"""Tests for the observability module."""

import json

from freezegun import freeze_time

from src.observability import (
    FeedFetchEvent,
    GenerationEvent,
    PageServeEvent,
    Timer,
    emit_event,
    generate_request_id,
    should_sample,
)


class TestGenerateRequestId:
    def test_generates_hex_string(self):
        request_id = generate_request_id()
        assert isinstance(request_id, str)
        assert len(request_id) == 16  # 8 bytes = 16 hex chars
        int(request_id, 16)  # Should be valid hex

    def test_generates_unique_ids(self):
        ids = [generate_request_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique


class TestFeedFetchEvent:
    @freeze_time("2026-01-01 12:00:00")
    def test_creates_event_with_defaults(self):
        event = FeedFetchEvent(feed_id=1, feed_url="https://example.com/feed")

        assert event.event_type == "feed_fetch"
        assert event.feed_id == 1
        assert event.feed_url == "https://example.com/feed"
        assert event.feed_domain == "example.com"
        assert event.timestamp == "2026-01-01T12:00:00Z"
        assert event.outcome == "success"
        assert len(event.request_id) == 16

    def test_extracts_domain_from_url(self):
        event = FeedFetchEvent(feed_url="https://blog.example.com/rss")
        assert event.feed_domain == "blog.example.com"

    def test_handles_invalid_url(self):
        event = FeedFetchEvent(feed_url="not-a-valid-url")
        assert event.feed_domain == ""

    def test_preserves_custom_request_id(self):
        event = FeedFetchEvent(
            feed_id=1,
            feed_url="https://example.com/feed",
            request_id="custom123456789a",
        )
        assert event.request_id == "custom123456789a"

    def test_records_error_state(self):
        event = FeedFetchEvent(
            feed_id=1,
            feed_url="https://example.com/feed",
            outcome="error",
            error_type="TimeoutError",
            error_message="Connection timed out",
            error_retriable=True,
        )

        assert event.outcome == "error"
        assert event.error_type == "TimeoutError"
        assert event.error_message == "Connection timed out"
        assert event.error_retriable is True


class TestGenerationEvent:
    @freeze_time("2026-01-01 12:00:00")
    def test_creates_event_with_defaults(self):
        event = GenerationEvent(feeds_active=10, entries_total=100)

        assert event.event_type == "html_generation"
        assert event.feeds_active == 10
        assert event.entries_total == 100
        assert event.timestamp == "2026-01-01T12:00:00Z"
        assert event.trigger == "http"

    def test_records_timing_breakdown(self):
        event = GenerationEvent(
            wall_time_ms=500,
            d1_query_time_ms=300,
            template_render_time_ms=150,
        )

        assert event.wall_time_ms == 500
        assert event.d1_query_time_ms == 300
        assert event.template_render_time_ms == 150


class TestPageServeEvent:
    @freeze_time("2026-01-01 12:00:00")
    def test_creates_event_with_defaults(self):
        event = PageServeEvent(
            method="GET",
            path="/",
            status_code=200,
        )

        assert event.event_type == "page_serve"
        assert event.method == "GET"
        assert event.path == "/"
        assert event.status_code == 200
        assert event.timestamp == "2026-01-01T12:00:00Z"

    def test_records_cache_status(self):
        event = PageServeEvent(
            method="GET",
            path="/feed.atom",
            cache_status="hit",
        )
        assert event.cache_status == "hit"


class TestShouldSample:
    def test_always_keeps_errors(self):
        event = {"event_type": "feed_fetch", "outcome": "error", "wall_time_ms": 100}
        assert should_sample(event) is True

    def test_always_keeps_slow_feed_fetches(self):
        event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 15000}
        assert should_sample(event) is True

    def test_always_keeps_slow_generation(self):
        event = {"event_type": "html_generation", "outcome": "success", "wall_time_ms": 35000}
        assert should_sample(event) is True

    def test_always_keeps_slow_page_serve(self):
        event = {"event_type": "page_serve", "outcome": "success", "wall_time_ms": 1500}
        assert should_sample(event) is True

    def test_always_keeps_debug_feeds(self):
        event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 100, "feed_id": 42}
        assert should_sample(event, debug_feed_ids=["42"]) is True
        assert should_sample(event, debug_feed_ids=["99"]) is not True  # Not in debug list

    def test_samples_fast_successful_operations(self):
        event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 100}

        # Run many times to test sampling
        results = [should_sample(event, sample_rate=0.5) for _ in range(1000)]

        # Should be roughly 50% with sample_rate=0.5
        hit_rate = sum(results) / len(results)
        assert 0.4 < hit_rate < 0.6

    def test_respects_custom_sample_rate(self):
        event = {"event_type": "page_serve", "outcome": "success", "wall_time_ms": 100}

        # 100% sample rate
        assert should_sample(event, sample_rate=1.0) is True

        # 0% sample rate
        results = [should_sample(event, sample_rate=0.0) for _ in range(100)]
        assert all(r is False for r in results)


class TestEmitEvent:
    def test_emits_dataclass_event(self, capsys):
        event = FeedFetchEvent(feed_id=1, feed_url="https://example.com/feed")

        emitted = emit_event(event, force=True)

        assert emitted is True
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["event_type"] == "feed_fetch"
        assert output["feed_id"] == 1

    def test_emits_dict_event(self, capsys):
        event = {"event_type": "test", "key": "value"}

        emitted = emit_event(event, force=True)

        assert emitted is True
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())
        assert output["event_type"] == "test"
        assert output["key"] == "value"

    def test_respects_sampling(self):
        event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 100}

        # With 0% sample rate, should never emit
        results = [emit_event(event, sample_rate=0.0) for _ in range(100)]
        assert all(r is False for r in results)

    def test_force_bypasses_sampling(self, capsys):
        event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 100}

        emitted = emit_event(event, sample_rate=0.0, force=True)

        assert emitted is True
        captured = capsys.readouterr()
        assert "feed_fetch" in captured.out


class TestTimer:
    def test_measures_elapsed_time(self):
        import time

        with Timer() as t:
            time.sleep(0.01)  # 10ms

        assert t.elapsed_ms >= 10
        assert t.elapsed_ms < 100  # Should not take 100ms

    def test_elapsed_during_execution(self):
        import time

        with Timer() as t:
            time.sleep(0.01)
            mid_elapsed = t.elapsed()
            time.sleep(0.01)

        assert mid_elapsed >= 10
        assert t.elapsed_ms >= 20
        assert t.elapsed_ms > mid_elapsed
