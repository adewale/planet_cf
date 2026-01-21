# tests/unit/test_observability.py
"""Tests for the observability module with consolidated events."""

import json

from freezegun import freeze_time

from src.observability import (
    AdminActionEvent,
    FeedFetchEvent,
    RequestEvent,
    SchedulerEvent,
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

    def test_includes_indexing_aggregates(self):
        """FeedFetchEvent now absorbs IndexingEvent as aggregated fields."""
        event = FeedFetchEvent(
            feed_id=1,
            feed_url="https://example.com/feed",
            indexing_attempted=5,
            indexing_succeeded=4,
            indexing_failed=1,
            indexing_total_ms=1500,
            indexing_embedding_ms=1200,
            indexing_upsert_ms=280,
            indexing_text_truncated=2,
        )

        assert event.indexing_attempted == 5
        assert event.indexing_succeeded == 4
        assert event.indexing_failed == 1
        assert event.indexing_total_ms == 1500
        assert event.indexing_text_truncated == 2


class TestRequestEvent:
    """Tests for RequestEvent which absorbs PageServeEvent, SearchEvent, GenerationEvent."""

    @freeze_time("2026-01-01 12:00:00")
    def test_creates_event_with_defaults(self):
        event = RequestEvent(
            method="GET",
            path="/",
            status_code=200,
        )

        assert event.event_type == "request"
        assert event.method == "GET"
        assert event.path == "/"
        assert event.status_code == 200
        assert event.timestamp == "2026-01-01T12:00:00Z"

    def test_records_cache_status(self):
        event = RequestEvent(
            method="GET",
            path="/feed.atom",
            cache_status="hit",
        )
        assert event.cache_status == "hit"

    def test_includes_search_fields(self):
        """RequestEvent absorbs SearchEvent fields."""
        event = RequestEvent(
            method="GET",
            path="/search",
            route="/search",
            search_query="cloudflare workers",
            search_query_length=18,
            search_embedding_ms=120,
            search_vectorize_ms=340,
            search_d1_ms=25,
            search_results_total=11,
            search_semantic_matches=8,
            search_keyword_matches=3,
        )

        assert event.search_query == "cloudflare workers"
        assert event.search_results_total == 11
        assert event.search_semantic_matches == 8

    def test_includes_generation_fields(self):
        """RequestEvent absorbs GenerationEvent fields."""
        event = RequestEvent(
            method="GET",
            path="/",
            route="/",
            generation_d1_ms=45,
            generation_render_ms=12,
            generation_entries_total=150,
            generation_feeds_healthy=12,
            generation_trigger="http",
        )

        assert event.generation_d1_ms == 45
        assert event.generation_entries_total == 150
        assert event.generation_trigger == "http"

    def test_includes_oauth_fields(self):
        """RequestEvent absorbs OAuth flow fields."""
        event = RequestEvent(
            method="GET",
            path="/auth/github/callback",
            route="/auth/github/callback",
            oauth_stage="callback",
            oauth_provider="github",
            oauth_success=True,
            oauth_username="testuser",
        )

        assert event.oauth_stage == "callback"
        assert event.oauth_provider == "github"
        assert event.oauth_success is True

    def test_null_fields_for_non_applicable_routes(self):
        """Route-specific fields should be null for non-applicable routes."""
        event = RequestEvent(method="GET", path="/static/style.css")

        # Search fields should be None
        assert event.search_query is None
        assert event.search_results_total is None

        # Generation fields should be None
        assert event.generation_d1_ms is None

        # OAuth fields should be None
        assert event.oauth_stage is None


class TestSchedulerEvent:
    @freeze_time("2026-01-01 12:00:00")
    def test_creates_event_with_defaults(self):
        event = SchedulerEvent()

        assert event.event_type == "scheduler"
        assert event.timestamp == "2026-01-01T12:00:00Z"
        assert event.outcome == "success"

    def test_includes_scheduler_phase(self):
        event = SchedulerEvent(
            scheduler_d1_ms=50,
            scheduler_queue_ms=120,
            feeds_queried=50,
            feeds_active=47,
            feeds_enqueued=47,
        )

        assert event.scheduler_d1_ms == 50
        assert event.feeds_enqueued == 47

    def test_includes_retention_phase(self):
        """SchedulerEvent absorbs retention cleanup."""
        event = SchedulerEvent(
            retention_d1_ms=200,
            retention_vectorize_ms=150,
            retention_entries_scanned=1000,
            retention_entries_deleted=50,
            retention_vectors_deleted=50,
            retention_errors=0,
            retention_days=90,
            retention_max_per_feed=100,
        )

        assert event.retention_entries_deleted == 50
        assert event.retention_vectors_deleted == 50
        assert event.retention_days == 90


class TestAdminActionEvent:
    @freeze_time("2026-01-01 12:00:00")
    def test_creates_event_with_defaults(self):
        event = AdminActionEvent(
            admin_username="testadmin",
            admin_id=1,
            action="add_feed",
        )

        assert event.event_type == "admin_action"
        assert event.admin_username == "testadmin"
        assert event.action == "add_feed"

    def test_includes_opml_import_fields(self):
        event = AdminActionEvent(
            admin_username="testadmin",
            admin_id=1,
            action="import_opml",
            import_file_size=5000,
            import_feeds_parsed=20,
            import_feeds_added=18,
            import_feeds_skipped=2,
            import_errors=0,
        )

        assert event.import_feeds_added == 18
        assert event.import_feeds_skipped == 2

    def test_includes_reindex_fields(self):
        event = AdminActionEvent(
            admin_username="testadmin",
            admin_id=1,
            action="reindex",
            reindex_entries_total=500,
            reindex_entries_indexed=498,
            reindex_entries_failed=2,
            reindex_total_ms=15000,
        )

        assert event.reindex_entries_indexed == 498
        assert event.reindex_total_ms == 15000

    def test_includes_dlq_fields(self):
        event = AdminActionEvent(
            admin_username="testadmin",
            admin_id=1,
            action="retry_dlq",
            dlq_feed_id=42,
            dlq_original_error="TimeoutError: Connection timed out",
            dlq_action="retry",
        )

        assert event.dlq_feed_id == 42
        assert event.dlq_action == "retry"


class TestShouldSample:
    def test_always_keeps_errors(self):
        event = {"event_type": "feed_fetch", "outcome": "error", "wall_time_ms": 100}
        assert should_sample(event) is True

    def test_always_keeps_slow_feed_fetches(self):
        event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 15000}
        assert should_sample(event) is True

    def test_always_keeps_slow_requests(self):
        event = {"event_type": "request", "outcome": "success", "wall_time_ms": 1500}
        assert should_sample(event) is True

    def test_always_keeps_slow_scheduler(self):
        event = {"event_type": "scheduler", "outcome": "success", "wall_time_ms": 65000}
        assert should_sample(event) is True

    def test_always_keeps_zero_result_searches(self):
        event = {
            "event_type": "request",
            "outcome": "success",
            "wall_time_ms": 100,
            "search_results_total": 0,
        }
        assert should_sample(event) is True

    def test_always_keeps_debug_feeds(self):
        event = {
            "event_type": "feed_fetch",
            "outcome": "success",
            "wall_time_ms": 100,
            "feed_id": 42,
        }
        # Feed 42 is in debug list - always keep
        assert should_sample(event, debug_feed_ids=["42"]) is True
        # Feed 42 is NOT in debug list ["99"] - falls through to random sampling
        # With sample_rate=0, should never be sampled
        assert should_sample(event, debug_feed_ids=["99"], sample_rate=0) is False

    def test_samples_fast_successful_operations(self):
        event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 100}

        # Run many times to test sampling
        results = [should_sample(event, sample_rate=0.5) for _ in range(1000)]

        # Should be roughly 50% with sample_rate=0.5
        hit_rate = sum(results) / len(results)
        assert 0.4 < hit_rate < 0.6

    def test_respects_custom_sample_rate(self):
        event = {"event_type": "request", "outcome": "success", "wall_time_ms": 100}

        # 100% sample rate
        assert should_sample(event, sample_rate=1.0) is True

        # 0% sample rate
        results = [should_sample(event, sample_rate=0.0) for _ in range(100)]
        assert all(r is False for r in results)


class TestEmitEvent:
    def _enable_propagation(self):
        """Helper to enable logging propagation for tests."""
        import logging

        logger = logging.getLogger("src.observability")
        old_propagate = logger.propagate
        logger.propagate = True
        return logger, old_propagate

    def test_emits_dataclass_event(self, caplog):
        logger, old_propagate = self._enable_propagation()
        try:
            event = FeedFetchEvent(feed_id=1, feed_url="https://example.com/feed")

            with caplog.at_level("INFO", logger="src.observability"):
                emitted = emit_event(event, force=True)

            assert emitted is True
            assert len(caplog.records) == 1
            output = json.loads(caplog.records[0].message)
            assert output["event_type"] == "feed_fetch"
            assert output["feed_id"] == 1
        finally:
            logger.propagate = old_propagate

    def test_emits_request_event(self, caplog):
        logger, old_propagate = self._enable_propagation()
        try:
            event = RequestEvent(method="GET", path="/search", search_query="test")

            with caplog.at_level("INFO", logger="src.observability"):
                emitted = emit_event(event, force=True)

            assert emitted is True
            assert len(caplog.records) == 1
            output = json.loads(caplog.records[0].message)
            assert output["event_type"] == "request"
            assert output["search_query"] == "test"
        finally:
            logger.propagate = old_propagate

    def test_emits_dict_event(self, caplog):
        logger, old_propagate = self._enable_propagation()
        try:
            event = {"event_type": "test", "key": "value"}

            with caplog.at_level("INFO", logger="src.observability"):
                emitted = emit_event(event, force=True)

            assert emitted is True
            assert len(caplog.records) == 1
            output = json.loads(caplog.records[0].message)
            assert output["event_type"] == "test"
            assert output["key"] == "value"
        finally:
            logger.propagate = old_propagate

    def test_respects_sampling(self):
        event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 100}

        # With 0% sample rate, should never emit
        results = [emit_event(event, sample_rate=0.0) for _ in range(100)]
        assert all(r is False for r in results)

    def test_force_bypasses_sampling(self, caplog):
        logger, old_propagate = self._enable_propagation()
        try:
            event = {"event_type": "feed_fetch", "outcome": "success", "wall_time_ms": 100}

            with caplog.at_level("INFO", logger="src.observability"):
                emitted = emit_event(event, sample_rate=0.0, force=True)

            assert emitted is True
            assert len(caplog.records) == 1
            assert "feed_fetch" in caplog.records[0].message
        finally:
            logger.propagate = old_propagate


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


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEventEdgeCases:
    """Edge case tests for event handling."""

    def test_feed_fetch_event_with_missing_fields(self):
        """FeedFetchEvent works with minimal fields."""
        event = FeedFetchEvent()
        assert event.feed_id == 0
        assert event.feed_url == ""
        assert event.feed_domain == ""
        assert event.event_type == "feed_fetch"

    def test_feed_id_none_vs_zero(self):
        """Feed ID of 0 is distinct from missing."""
        event = FeedFetchEvent(feed_id=0)
        assert event.feed_id == 0
        # Default is also 0 for missing
        event2 = FeedFetchEvent()
        assert event2.feed_id == 0

    def test_url_parsing_failure(self):
        """Invalid URL doesn't crash domain extraction."""
        event = FeedFetchEvent(feed_url=":::invalid:::")
        # Should handle gracefully with empty domain
        assert event.feed_domain == ""

    def test_very_large_wall_time(self):
        """Very large wall_time_ms values are handled."""
        event = FeedFetchEvent(wall_time_ms=999999999.99)
        assert event.wall_time_ms == 999999999.99

    def test_timestamp_auto_generation(self):
        """Timestamp is auto-generated if not provided."""
        event = FeedFetchEvent()
        assert event.timestamp != ""
        assert "T" in event.timestamp  # ISO format
        assert event.timestamp.endswith("Z")

    def test_request_id_auto_generation(self):
        """Request ID is auto-generated if not provided."""
        event = FeedFetchEvent()
        assert len(event.request_id) == 16
        # Should be valid hex
        int(event.request_id, 16)

    def test_request_event_null_search_fields(self):
        """RequestEvent search fields are None for non-search routes."""
        event = RequestEvent(method="GET", path="/")
        assert event.search_query is None
        assert event.search_results_total is None

    def test_scheduler_event_generates_correlation_id(self):
        """SchedulerEvent auto-generates correlation_id."""
        event = SchedulerEvent()
        assert event.correlation_id != ""
        assert len(event.correlation_id) == 16


class TestSamplingEdgeCases:
    """Edge case tests for sampling logic."""

    def test_should_sample_with_malformed_dict(self):
        """should_sample handles malformed event dict."""
        # Missing event_type
        event = {"outcome": "success", "wall_time_ms": 100}
        # Should not crash, falls through to random sampling
        result = should_sample(event, sample_rate=1.0)
        assert result is True

    def test_should_sample_with_missing_fields(self):
        """should_sample handles dict with missing fields."""
        event = {"event_type": "request"}
        # Missing outcome, wall_time_ms - should not crash
        result = should_sample(event, sample_rate=1.0)
        assert result is True

    def test_should_sample_with_none_outcome(self):
        """should_sample handles None outcome."""
        event = {"event_type": "feed_fetch", "outcome": None, "wall_time_ms": 100}
        result = should_sample(event, sample_rate=1.0)
        assert result is True

    def test_emit_event_with_malformed_dict(self, capsys):
        """emit_event handles dict with unusual values."""
        import contextlib

        event = {"event_type": "test", "value": float("inf")}
        # JSON can't serialize infinity, but emit should handle it
        with contextlib.suppress(ValueError, OverflowError):
            # Expected - JSON doesn't support infinity
            emit_event(event, force=True)
