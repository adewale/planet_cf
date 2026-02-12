# tests/unit/test_remaining_mitigations.py
"""Tests for mitigations #7, #10, #11, #12, #13, #15, #16, #17, #18, #19, #20.

Verifies that all observability, detection, and process mitigations are
properly implemented in the codebase.
"""

import inspect
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


# =============================================================================
# #7: MockD1 strict mode validates SQL columns
# =============================================================================


class TestMockD1StrictMode:
    """Verify MockD1 strict mode catches unknown column references."""

    def test_strict_mode_rejects_unknown_insert_column(self):
        import pytest

        from tests.conftest import MockD1

        schema = {"feeds": {"id", "url", "title"}}
        db = MockD1(data={"feeds": []}, schema=schema)

        with pytest.raises(ValueError, match="bogus_column"):
            db.prepare("INSERT INTO feeds (id, url, bogus_column) VALUES (?, ?, ?)")

    def test_strict_mode_rejects_unknown_update_column(self):
        import pytest

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

    def test_strict_mode_validates_all_main_queries(self):
        """Extract SQL from main.py and validate via MockD1 strict mode."""
        from main import PlanetCF
        from tests.conftest import MockD1

        schema = PlanetCF._EXPECTED_COLUMNS
        db = MockD1(data={t: [] for t in schema}, schema=schema)

        # Extract all SQL strings from main.py source
        import main as main_module

        source = inspect.getsource(main_module)

        # Find INSERT INTO and UPDATE statements
        sql_patterns = re.findall(
            r"(?:INSERT\s+INTO|UPDATE)\s+\w+\s+.*?(?:VALUES|WHERE|SET)",
            source,
            re.IGNORECASE | re.DOTALL,
        )

        assert len(sql_patterns) > 0, "Should find SQL patterns in main.py"
        # Run each through strict validation
        for sql in sql_patterns:
            db._validate_sql_columns(sql)


# =============================================================================
# #10: _record_feed_error returns deactivation status
# =============================================================================


class TestRecordFeedErrorReturnValue:
    """Verify _record_feed_error returns bool indicating deactivation."""

    def test_record_feed_error_returns_bool(self):
        """_record_feed_error should return a bool, not None."""
        source = inspect.getsource(__import__("main").Default._record_feed_error)
        assert "-> bool" in source or "-> bool:" in source, (
            "_record_feed_error should have bool return type"
        )
        assert "return True" in source, "Should return True when feed is deactivated"
        assert "return False" in source, "Should return False when feed is not deactivated"

    def test_queue_handler_sets_feed_auto_deactivated(self):
        """Queue handler should set event.feed_auto_deactivated from _record_feed_error."""
        source = inspect.getsource(__import__("main").Default.queue)
        assert "feed_auto_deactivated" in source, (
            "Queue handler should set event.feed_auto_deactivated"
        )


# =============================================================================
# #11: Feed health summary in SchedulerEvent
# =============================================================================


class TestSchedulerHealthSummary:
    """Verify SchedulerEvent has feed health summary fields."""

    def test_scheduler_event_has_health_fields(self):
        from observability import SchedulerEvent

        event = SchedulerEvent()
        assert hasattr(event, "feeds_disabled"), "Missing feeds_disabled field"
        assert hasattr(event, "feeds_newly_disabled"), "Missing feeds_newly_disabled field"
        assert event.feeds_disabled == 0
        assert event.feeds_newly_disabled == 0

    def test_scheduler_populates_health_summary(self):
        """_run_scheduler should query and populate health summary fields."""
        source = inspect.getsource(__import__("main").Default._run_scheduler)
        assert "feeds_disabled" in source, "Scheduler should populate feeds_disabled"
        assert "feeds_newly_disabled" in source, "Scheduler should populate feeds_newly_disabled"


# =============================================================================
# #12: Error clustering detection
# =============================================================================


class TestErrorClustering:
    """Verify error clustering is detected in scheduler."""

    def test_scheduler_event_has_cluster_fields(self):
        from observability import SchedulerEvent

        event = SchedulerEvent()
        assert hasattr(event, "error_clusters")
        assert hasattr(event, "error_cluster_top")
        assert event.error_clusters == 0
        assert event.error_cluster_top is None

    def test_scheduler_queries_error_clusters(self):
        """_run_scheduler should GROUP BY fetch_error to find clusters."""
        source = inspect.getsource(__import__("main").Default._run_scheduler)
        assert "GROUP BY fetch_error" in source, "Should group errors to find clusters"
        assert "HAVING COUNT" in source, "Should filter for clusters with 2+ feeds"


# =============================================================================
# #13: error_category on FeedFetchEvent
# =============================================================================


class TestErrorCategory:
    """Verify error_category field exists and is populated."""

    def test_feed_fetch_event_has_error_category(self):
        from observability import FeedFetchEvent

        event = FeedFetchEvent()
        assert hasattr(event, "error_category")
        assert event.error_category is None

    def test_classify_error_function_exists(self):
        """_classify_error helper should classify exceptions."""
        from main import _classify_error

        assert _classify_error(TimeoutError("test")) == "timeout"
        assert _classify_error(ValueError("SSRF invalid")) == "validation"
        assert _classify_error(ConnectionError("refused")) == "network"
        assert _classify_error(Exception("D1 database error")) == "database"
        assert _classify_error(Exception("XML parse failure")) == "parse"
        assert _classify_error(Exception("something else")) == "unknown"

    def test_queue_handler_sets_error_category(self):
        """Queue handler should set event.error_category on errors."""
        source = inspect.getsource(__import__("main").Default.queue)
        assert "error_category" in source, "Queue handler should set error_category"
        # Check all three exception handlers set it
        assert source.count("error_category") >= 3, (
            "All exception handlers (Timeout, RateLimit, generic) should set error_category"
        )


# =============================================================================
# #15: Trend tracking via SchedulerEvent (feeds_disabled over time)
# =============================================================================


class TestTrendTracking:
    """Trend tracking is achieved via SchedulerEvent health summary fields.
    Each cron emits feeds_disabled/feeds_newly_disabled — log analysis
    over time provides the trend.
    """

    def test_scheduler_event_enables_trend_tracking(self):
        """SchedulerEvent with feeds_disabled enables trend analysis."""
        from observability import SchedulerEvent

        event = SchedulerEvent()
        # These fields, emitted each hour, provide trend data
        assert hasattr(event, "feeds_disabled")
        assert hasattr(event, "feeds_newly_disabled")
        assert hasattr(event, "dlq_depth")


# =============================================================================
# #16: Warning banner for failing feeds in admin
# =============================================================================


class TestAdminWarningBanner:
    """Verify admin dashboard passes health warnings to template."""

    def test_admin_dashboard_computes_health_warnings(self):
        source = inspect.getsource(__import__("main").Default._serve_admin_dashboard)
        assert "health_warnings" in source, "Admin dashboard should compute health_warnings"
        assert "inactive" in source, "Should check for inactive feeds"
        assert "failing" in source, "Should check for failing feeds"


# =============================================================================
# #17: DLQ consumer
# =============================================================================


class TestDLQConsumer:
    """Verify DLQ queue consumer is implemented."""

    def test_queue_handler_detects_dlq_messages(self):
        """Queue handler should detect DLQ batch and handle differently."""
        source = inspect.getsource(__import__("main").Default.queue)
        assert "dlq" in source.lower(), "Queue handler should check for DLQ queue"
        assert "dlq_message_consumed" in source, "Should log DLQ message consumption"

    def test_wrangler_has_dlq_consumer(self):
        """wrangler.jsonc should have a consumer for the DLQ queue."""
        wrangler_content = (PROJECT_ROOT / "wrangler.jsonc").read_text()
        assert "planetcf-feed-dlq" in wrangler_content
        # Check it appears in consumers section (not just producers)
        # Find the consumers array and verify DLQ appears in it
        consumers_match = re.search(r'"consumers"\s*:\s*\[(.*?)\]', wrangler_content, re.DOTALL)
        assert consumers_match, "Should have consumers section"
        assert "feed-dlq" in consumers_match.group(1), "DLQ queue should be listed as a consumer"


# =============================================================================
# #18: Cron check DLQ depth
# =============================================================================


class TestDLQDepthCheck:
    """Verify scheduler checks DLQ depth (via feeds with high failures)."""

    def test_scheduler_event_has_dlq_depth(self):
        from observability import SchedulerEvent

        event = SchedulerEvent()
        assert hasattr(event, "dlq_depth")
        assert event.dlq_depth == 0

    def test_scheduler_queries_dlq_depth(self):
        source = inspect.getsource(__import__("main").Default._run_scheduler)
        assert "dlq_depth" in source, "Scheduler should populate dlq_depth"


# =============================================================================
# #19: Deployment messages
# =============================================================================


class TestDeploymentMessages:
    """Verify deployment scripts include version messages."""

    def test_deploy_script_uses_message_flag(self):
        script = (PROJECT_ROOT / "scripts" / "deploy_instance.sh").read_text()
        assert "--message" in script, (
            "deploy_instance.sh should use --message flag for wrangler deploy"
        )

    def test_ci_workflow_uses_message_flag(self):
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "check.yml").read_text()
        assert "--message" in workflow, "CI workflow should use --message flag for wrangler deploy"


# =============================================================================
# #20: Post-deploy health check
# =============================================================================


class TestPostDeployHealthCheck:
    """Verify post-deploy verification checks feed health."""

    def test_health_endpoint_route_exists(self):
        """Route dispatcher should have /health route."""
        from route_dispatcher import create_default_routes

        routes = create_default_routes()
        paths = [r.path for r in routes]
        assert "/health" in paths, "/health route should exist"

    def test_health_handler_exists(self):
        """main.py should have _serve_health method."""
        assert hasattr(__import__("main").Default, "_serve_health"), (
            "Default class should have _serve_health method"
        )

    def test_verify_deployment_checks_health(self):
        """verify_deployment.py should check /health endpoint."""
        script = (PROJECT_ROOT / "scripts" / "verify_deployment.py").read_text()
        assert "/health" in script, "verify_deployment.py should check /health"

    def test_deploy_script_checks_health(self):
        """deploy_instance.sh should check /health after deployment."""
        script = (PROJECT_ROOT / "scripts" / "deploy_instance.sh").read_text()
        assert "/health" in script, "deploy_instance.sh should check /health"
