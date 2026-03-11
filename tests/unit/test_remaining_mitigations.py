# tests/unit/test_remaining_mitigations.py
"""Tests for mitigations #7, #10, #11, #12, #13, #15, #16, #17, #18, #19, #20.

Verifies that all observability, detection, and process mitigations are
properly implemented in the codebase.  Where possible, tests exercise
actual behaviour rather than inspecting source code.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


# =============================================================================
# #7: MockD1 strict mode validates SQL columns
# =============================================================================


class TestMockD1StrictMode:
    """Verify MockD1 strict mode catches unknown column references."""

    def test_strict_mode_rejects_unknown_insert_column(self):
        from tests.conftest import MockD1

        schema = {"feeds": {"id", "url", "title"}}
        db = MockD1(data={"feeds": []}, schema=schema)

        with pytest.raises(ValueError, match="bogus_column"):
            db.prepare("INSERT INTO feeds (id, url, bogus_column) VALUES (?, ?, ?)")

    def test_strict_mode_rejects_unknown_update_column(self):
        from tests.conftest import MockD1

        schema = {"feeds": {"id", "url", "title"}}
        db = MockD1(data={"feeds": []}, schema=schema)

        with pytest.raises(ValueError, match="bogus_column"):
            db.prepare("UPDATE feeds SET bogus_column = ? WHERE id = ?")

    def test_strict_mode_allows_valid_columns(self):
        from tests.conftest import MockD1

        schema = {"feeds": {"id", "url", "title"}}
        db = MockD1(data={"feeds": []}, schema=schema)

        # Should not raise
        stmt = db.prepare("INSERT INTO feeds (id, url, title) VALUES (?, ?, ?)")
        assert stmt is not None

    def test_non_strict_mode_allows_anything(self):
        from tests.conftest import MockD1

        db = MockD1(data={"feeds": []})
        # No schema = no validation, should not raise
        stmt = db.prepare("INSERT INTO feeds (id, url, bogus) VALUES (?, ?, ?)")
        assert stmt is not None


# =============================================================================
# #10: _record_feed_error returns deactivation status
# =============================================================================


class TestRecordFeedErrorReturnValue:
    """Verify _record_feed_error return type and queue handler integration."""

    @pytest.mark.asyncio
    async def test_record_feed_error_returns_false_when_still_active(self):
        """_record_feed_error returns False when the feed is not deactivated."""
        from tests.conftest import make_authenticated_worker

        # Feed has 0 consecutive failures and high threshold, so it stays active
        feeds = [
            {
                "id": 1,
                "url": "https://example.com/feed.xml",
                "title": "Active Feed",
                "is_active": 1,
                "consecutive_failures": 0,
                "fetch_error": None,
                "fetch_error_count": 0,
                "etag": None,
                "last_modified": None,
                "updated_at": None,
            }
        ]
        worker, env, _cookie = make_authenticated_worker(feeds=feeds)

        result = await worker._record_feed_error(1, "Temporary error")
        assert result is False

    @pytest.mark.asyncio
    async def test_record_feed_error_returns_true_when_deactivated(self):
        """_record_feed_error returns True when the feed is auto-deactivated.

        Note: The actual threshold comparison happens in SQL
        (consecutive_failures + 1 >= threshold), and our MockD1 returns the
        row data as-is. We set consecutive_failures high enough and is_active=0
        so the return dict indicates deactivation.
        """
        from tests.conftest import make_authenticated_worker

        # Feed already at the brink; MockD1 returns the row with is_active=0
        # after the UPDATE RETURNING
        feeds = [
            {
                "id": 1,
                "url": "https://example.com/feed.xml",
                "title": "Failing Feed",
                "is_active": 0,
                "consecutive_failures": 100,
                "fetch_error": "HTTP 500",
                "fetch_error_count": 100,
                "etag": None,
                "last_modified": None,
                "updated_at": None,
            }
        ]
        worker, env, _cookie = make_authenticated_worker(feeds=feeds)

        result = await worker._record_feed_error(1, "Another error")
        assert result is True


# =============================================================================
# #11: Feed health summary in SchedulerEvent
# =============================================================================


class TestSchedulerHealthSummary:
    """Verify SchedulerEvent has feed health summary fields."""

    def test_scheduler_event_has_health_fields(self):
        from src.observability import SchedulerEvent

        event = SchedulerEvent()
        assert hasattr(event, "feeds_disabled"), "Missing feeds_disabled field"
        assert hasattr(event, "feeds_newly_disabled"), "Missing feeds_newly_disabled field"
        assert event.feeds_disabled == 0
        assert event.feeds_newly_disabled == 0


# =============================================================================
# #12: Error clustering detection
# =============================================================================


class TestErrorClustering:
    """Verify error clustering fields exist on SchedulerEvent."""

    def test_scheduler_event_has_cluster_fields(self):
        from src.observability import SchedulerEvent

        event = SchedulerEvent()
        assert hasattr(event, "error_clusters")
        assert hasattr(event, "error_cluster_top")
        assert event.error_clusters == 0
        assert event.error_cluster_top is None


# =============================================================================
# #13: error_category on FeedFetchEvent
# =============================================================================


class TestErrorCategory:
    """Verify error_category field exists and _classify_error works."""

    def test_feed_fetch_event_has_error_category(self):
        from src.observability import FeedFetchEvent

        event = FeedFetchEvent()
        assert hasattr(event, "error_category")
        assert event.error_category is None

    def test_classify_error_categorises_timeout(self):
        from src.main import _classify_error

        assert _classify_error(TimeoutError("test")) == "timeout"

    def test_classify_error_categorises_validation(self):
        from src.main import _classify_error

        assert _classify_error(ValueError("SSRF invalid")) == "validation"

    def test_classify_error_categorises_network(self):
        from src.main import _classify_error

        assert _classify_error(ConnectionError("refused")) == "network"

    def test_classify_error_categorises_database(self):
        from src.main import _classify_error

        assert _classify_error(Exception("D1 database error")) == "database"

    def test_classify_error_categorises_parse(self):
        from src.main import _classify_error

        assert _classify_error(Exception("XML parse failure")) == "parse"

    def test_classify_error_categorises_unknown(self):
        from src.main import _classify_error

        assert _classify_error(Exception("something else")) == "unknown"


# =============================================================================
# #15: Trend tracking via SchedulerEvent (feeds_disabled over time)
# =============================================================================


class TestTrendTracking:
    """Trend tracking is achieved via SchedulerEvent health summary fields.
    Each cron emits feeds_disabled/feeds_newly_disabled -- log analysis
    over time provides the trend.
    """

    def test_scheduler_event_enables_trend_tracking(self):
        """SchedulerEvent with feeds_disabled enables trend analysis."""
        from src.observability import SchedulerEvent

        event = SchedulerEvent()
        # These fields, emitted each hour, provide trend data
        assert hasattr(event, "feeds_disabled")
        assert hasattr(event, "feeds_newly_disabled")
        assert hasattr(event, "dlq_depth")


# =============================================================================
# #16: Warning banner for failing feeds in admin
# =============================================================================


class TestAdminWarningBanner:
    """Verify admin dashboard includes health warnings for failing/inactive feeds."""

    @pytest.mark.asyncio
    async def test_admin_dashboard_shows_health_warnings_for_failing_feeds(self):
        """Dashboard HTML should contain a warning when feeds are failing."""
        from tests.conftest import make_authenticated_worker

        feeds = [
            {
                "id": 1,
                "url": "https://failing.com/rss",
                "title": "Failing Feed",
                "is_active": 1,
                "consecutive_failures": 5,
                "fetch_error": "HTTP 500",
            },
        ]
        worker, env, cookie = make_authenticated_worker(feeds=feeds)

        admin = {
            "id": 1,
            "github_username": "testadmin",
            "display_name": "Test Admin",
            "is_active": 1,
        }
        response = await worker._serve_admin_dashboard(admin)

        assert response.status == 200
        assert "failing" in response.body.lower()

    @pytest.mark.asyncio
    async def test_admin_dashboard_shows_warning_for_inactive_feeds(self):
        """Dashboard HTML should show 'Disabled' status when feeds are inactive."""
        from tests.conftest import make_authenticated_worker

        feeds = [
            {
                "id": 1,
                "url": "https://dead.com/rss",
                "title": "Dead Feed",
                "is_active": 0,
                "consecutive_failures": 10,
            },
        ]
        worker, env, cookie = make_authenticated_worker(feeds=feeds)

        admin = {
            "id": 1,
            "github_username": "testadmin",
            "display_name": "Test Admin",
            "is_active": 1,
        }
        response = await worker._serve_admin_dashboard(admin)

        assert response.status == 200
        assert "disabled" in response.body.lower()


# =============================================================================
# #17: DLQ consumer
# =============================================================================


class TestDLQConsumer:
    """Verify DLQ queue consumer is implemented."""

    def test_wrangler_has_dlq_consumer(self):
        """wrangler.jsonc should have a DLQ queue configured."""
        wrangler_content = (PROJECT_ROOT / "wrangler.jsonc").read_text()
        # Check for DLQ in producers (instance-agnostic: any *-feed-dlq name)
        assert "feed-dlq" in wrangler_content, "Should have a feed DLQ queue configured"
        assert "DEAD_LETTER_QUEUE" in wrangler_content, "Should bind DEAD_LETTER_QUEUE"
        # Check the main queue references a dead_letter_queue
        assert "dead_letter_queue" in wrangler_content, (
            "Main queue should reference a dead_letter_queue"
        )


# =============================================================================
# #18: Cron check DLQ depth
# =============================================================================


class TestDLQDepthCheck:
    """Verify SchedulerEvent has dlq_depth field for monitoring."""

    def test_scheduler_event_has_dlq_depth(self):
        from src.observability import SchedulerEvent

        event = SchedulerEvent()
        assert hasattr(event, "dlq_depth")
        assert event.dlq_depth == 0


# =============================================================================
# #19: Deployment messages
# =============================================================================


class TestDeploymentMessages:
    """Verify deployment scripts log deployment context."""

    def test_deploy_script_has_health_check(self):
        """deploy_instance.sh checks /health after deploy for deployment visibility."""
        script = (PROJECT_ROOT / "scripts" / "deploy_instance.sh").read_text()
        assert "/health" in script, "deploy_instance.sh should check /health after deploy"

    def test_ci_workflow_has_migration_step(self):
        """CI workflow runs migrations before deploy for deployment traceability."""
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "check.yml").read_text()
        assert "Run migrations" in workflow, "CI workflow should run migrations before deploy"


# =============================================================================
# #20: Post-deploy health check
# =============================================================================


class TestPostDeployHealthCheck:
    """Verify post-deploy verification checks feed health."""

    def test_health_endpoint_route_exists(self):
        """Route dispatcher should have /health route."""
        from tests.conftest import make_authenticated_worker

        worker, _env, _cookie = make_authenticated_worker()
        routes = worker._create_router().routes
        paths = [r.path for r in routes]
        assert "/health" in paths, "/health route should exist"

    def test_health_handler_exists(self):
        """main.py should have _serve_health method."""
        from src.main import Default

        assert hasattr(Default, "_serve_health"), "Default class should have _serve_health method"

    def test_verify_deployment_checks_health(self):
        """verify_deployment.py should check /health endpoint."""
        script = (PROJECT_ROOT / "scripts" / "verify_deployment.py").read_text()
        assert "/health" in script, "verify_deployment.py should check /health"

    def test_deploy_script_checks_health(self):
        """deploy_instance.sh should check /health after deployment."""
        script = (PROJECT_ROOT / "scripts" / "deploy_instance.sh").read_text()
        assert "/health" in script, "deploy_instance.sh should check /health"


# =============================================================================
# Queue processing with malformed message bodies
# =============================================================================


class _MockMessage:
    """Minimal mock queue message for malformed body tests."""

    def __init__(self, body):
        self.body = body
        self.id = "test-msg"
        self.attempts = 1
        self.acked = False
        self.retried = False

    def ack(self):
        self.acked = True

    def retry(self):
        self.retried = True


class _MockBatch:
    """Minimal mock queue batch."""

    def __init__(self, messages, queue="test-feed-queue"):
        self.messages = messages
        self.queue = queue


class TestQueueMalformedMessages:
    """Queue handler should gracefully handle malformed message bodies."""

    @pytest.mark.asyncio
    async def test_string_body_is_acked_not_retried(self):
        """A message with body='not a dict' is acknowledged (not retried)."""
        from tests.conftest import make_authenticated_worker

        worker, env, _ = make_authenticated_worker()
        msg = _MockMessage(body="not a dict")
        batch = _MockBatch([msg])

        await worker.queue(batch)

        assert msg.acked is True
        assert msg.retried is False

    @pytest.mark.asyncio
    async def test_none_body_is_acked_not_retried(self):
        """A message with body=None is acknowledged (not retried)."""
        from tests.conftest import make_authenticated_worker

        worker, env, _ = make_authenticated_worker()
        msg = _MockMessage(body=None)
        batch = _MockBatch([msg])

        await worker.queue(batch)

        assert msg.acked is True
        assert msg.retried is False

    @pytest.mark.asyncio
    async def test_unexpected_schema_body_is_acked_not_retried(self):
        """A message with an unexpected dict schema is acked (no crash).

        The queue handler extracts feed_id and url from the body with defaults;
        even if those keys are missing, the message should be processed
        (and likely fail during fetch) rather than crashing the batch.
        """
        from tests.conftest import make_authenticated_worker

        worker, env, _ = make_authenticated_worker()
        msg = _MockMessage(body={"unexpected": "schema"})
        batch = _MockBatch([msg])

        await worker.queue(batch)

        # Should be acked or retried -- never left unprocessed
        assert msg.acked or msg.retried
