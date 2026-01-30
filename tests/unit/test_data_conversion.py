# tests/unit/test_data_conversion.py
"""Tests for data conversion integrity between SQL queries and row factories.

These tests ensure that fields returned from SQL queries are preserved through
the conversion functions in src/wrappers.py and reach templates correctly.

This file was created after discovering a bug where `is_healthy` was computed
in SQL but dropped in `feed_row_from_js()`, causing all feeds to appear unhealthy.
"""

from src.wrappers import (
    admin_row_from_js,
    audit_row_from_js,
    audit_rows_from_d1,
    entry_row_from_js,
    entry_rows_from_d1,
    feed_row_from_js,
    feed_rows_from_d1,
)

# =============================================================================
# Feed Conversion Tests - SQL Fields Preservation
# =============================================================================


class TestFeedRowPreservesIsHealthy:
    """Tests specifically for the is_healthy field bug fix."""

    def test_preserves_is_healthy_when_true(self):
        """feed_row_from_js preserves is_healthy=1 from SQL CASE expression."""
        # Simulates SQL: CASE WHEN consecutive_failures < 3 THEN 1 ELSE 0 END as is_healthy
        row = {
            "id": 1,
            "url": "https://example.com/feed.xml",
            "title": "Example Feed",
            "consecutive_failures": 0,
            "is_healthy": 1,  # Computed in SQL
        }
        result = feed_row_from_js(row)
        assert "is_healthy" in result, "is_healthy field must be preserved"
        assert result["is_healthy"] == 1

    def test_preserves_is_healthy_when_false(self):
        """feed_row_from_js preserves is_healthy=0 for unhealthy feeds."""
        row = {
            "id": 2,
            "url": "https://failing.com/feed.xml",
            "title": "Failing Feed",
            "consecutive_failures": 5,
            "is_healthy": 0,  # Computed in SQL
        }
        result = feed_row_from_js(row)
        assert "is_healthy" in result
        assert result["is_healthy"] == 0

    def test_is_healthy_none_when_not_in_sql_result(self):
        """is_healthy is None when query doesn't compute it (e.g., SELECT *)."""
        row = {
            "id": 3,
            "url": "https://example.com/feed.xml",
            # is_healthy not computed in this query (e.g., admin dashboard uses SELECT *)
        }
        result = feed_row_from_js(row)
        assert "is_healthy" in result
        assert result["is_healthy"] is None


class TestFeedRowPreservesAllIndexPageFields:
    """Tests that all fields from index page SQL query are preserved."""

    def test_preserves_index_page_sql_fields(self):
        """Preserves all fields from: SELECT id, title, site_url, url, last_success_at, is_healthy."""
        # These are the exact fields from the index page SQL query
        row = {
            "id": 42,
            "title": "My Blog",
            "site_url": "https://myblog.com",
            "url": "https://myblog.com/feed.xml",
            "last_success_at": "2025-01-17T12:00:00Z",
            "is_healthy": 1,
        }
        result = feed_row_from_js(row)

        # Verify all index page fields are present
        assert result["id"] == 42
        assert result["title"] == "My Blog"
        assert result["site_url"] == "https://myblog.com"
        assert result["url"] == "https://myblog.com/feed.xml"
        assert result["last_success_at"] == "2025-01-17T12:00:00Z"
        assert result["is_healthy"] == 1


class TestFeedRowPreservesAllAdminDashboardFields:
    """Tests that all fields from admin dashboard SQL query (SELECT *) are preserved."""

    def test_preserves_admin_dashboard_sql_fields(self):
        """Preserves all feed table columns from SELECT * query."""
        row = {
            "id": 1,
            "url": "https://example.com/feed.xml",
            "title": "Example Feed",
            "site_url": "https://example.com",
            "is_active": 1,
            "consecutive_failures": 0,
            "etag": '"abc123"',
            "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT",
            "last_success_at": "2025-01-17T12:00:00Z",
            "last_error_at": None,
            "last_error_message": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-17T12:00:00Z",
            "author_name": "John Doe",
            "author_email": "john@example.com",
        }
        result = feed_row_from_js(row)

        # Verify all admin dashboard fields are present
        assert result["id"] == 1
        assert result["url"] == "https://example.com/feed.xml"
        assert result["title"] == "Example Feed"
        assert result["site_url"] == "https://example.com"
        assert result["is_active"] == 1
        assert result["consecutive_failures"] == 0
        assert result["etag"] == '"abc123"'
        assert result["last_modified"] == "Wed, 01 Jan 2025 00:00:00 GMT"
        assert result["last_success_at"] == "2025-01-17T12:00:00Z"
        assert result["last_error_at"] is None
        assert result["last_error_message"] is None
        assert result["created_at"] == "2025-01-01T00:00:00Z"
        assert result["updated_at"] == "2025-01-17T12:00:00Z"
        assert result["author_name"] == "John Doe"
        assert result["author_email"] == "john@example.com"


class TestFeedRowsFromD1PreservesFields:
    """Tests that feed_rows_from_d1 preserves all fields through batch conversion."""

    def test_preserves_is_healthy_in_batch(self):
        """feed_rows_from_d1 preserves is_healthy for all feeds in batch."""
        results = [
            {"id": 1, "url": "https://a.com/feed.xml", "is_healthy": 1},
            {"id": 2, "url": "https://b.com/feed.xml", "is_healthy": 0},
            {"id": 3, "url": "https://c.com/feed.xml", "is_healthy": 1},
        ]
        rows = feed_rows_from_d1(results)

        assert len(rows) == 3
        assert rows[0]["is_healthy"] == 1
        assert rows[1]["is_healthy"] == 0
        assert rows[2]["is_healthy"] == 1


# =============================================================================
# Entry Conversion Tests - SQL Fields Preservation
# =============================================================================


class TestEntryRowPreservesAllIndexPageFields:
    """Tests that all fields from index page entry SQL query are preserved."""

    def test_preserves_joined_feed_fields(self):
        """Preserves feed_title and feed_site_url from JOIN."""
        row = {
            "id": 100,
            "feed_id": 42,
            "guid": "unique-guid",
            "url": "https://example.com/post/1",
            "title": "Post Title",
            "author": "Author Name",
            "content": "<p>Content</p>",
            "summary": "Summary",
            "published_at": "2025-01-17T10:00:00Z",
            "created_at": "2025-01-17T10:05:00Z",
            "first_seen": "2025-01-17T10:05:00Z",
            # Joined from feeds table
            "feed_title": "Example Feed",
            "feed_site_url": "https://example.com",
            # Row number columns from window functions (internal, not used in templates)
            "rn_per_day": 1,
            "rn_total": 5,
        }
        result = entry_row_from_js(row)

        # Core entry fields
        assert result["id"] == 100
        assert result["feed_id"] == 42
        assert result["guid"] == "unique-guid"
        assert result["url"] == "https://example.com/post/1"
        assert result["title"] == "Post Title"
        assert result["author"] == "Author Name"
        assert result["content"] == "<p>Content</p>"
        assert result["summary"] == "Summary"
        assert result["published_at"] == "2025-01-17T10:00:00Z"
        assert result["first_seen"] == "2025-01-17T10:05:00Z"

        # Joined feed fields (required for template display_author logic)
        assert result["feed_title"] == "Example Feed"
        assert result["feed_site_url"] == "https://example.com"


class TestEntryRowsFromD1PreservesFields:
    """Tests that entry_rows_from_d1 preserves all fields through batch conversion."""

    def test_preserves_joined_fields_in_batch(self):
        """entry_rows_from_d1 preserves feed_title and feed_site_url for all entries."""
        results = [
            {
                "id": 1,
                "feed_id": 1,
                "guid": "a",
                "url": "https://a.com",
                "title": "A",
                "feed_title": "Feed A",
                "feed_site_url": "https://feeda.com",
            },
            {
                "id": 2,
                "feed_id": 2,
                "guid": "b",
                "url": "https://b.com",
                "title": "B",
                "feed_title": "Feed B",
                "feed_site_url": "https://feedb.com",
            },
        ]
        rows = entry_rows_from_d1(results)

        assert len(rows) == 2
        assert rows[0]["feed_title"] == "Feed A"
        assert rows[0]["feed_site_url"] == "https://feeda.com"
        assert rows[1]["feed_title"] == "Feed B"
        assert rows[1]["feed_site_url"] == "https://feedb.com"


# =============================================================================
# Template-Required Fields Tests
# =============================================================================


class TestTemplateRequiredFeedFields:
    """Tests that fields required by templates are preserved in conversion."""

    def test_index_template_feed_fields(self):
        """index.html requires: url, site_url, title, is_healthy for each feed."""
        row = {
            "id": 1,
            "url": "https://example.com/feed.xml",
            "site_url": "https://example.com",
            "title": "Example Feed",
            "is_healthy": 1,
        }
        result = feed_row_from_js(row)

        # index.html line 50: class="{{ 'healthy' if feed.is_healthy else 'unhealthy' }}"
        assert "is_healthy" in result
        # index.html line 51: href="{{ feed.url }}"
        assert "url" in result
        # index.html line 52: href="{{ feed.site_url }}" ... {{ feed.title or 'Untitled' }}
        assert "site_url" in result
        assert "title" in result

    def test_admin_dashboard_feed_fields(self):
        """admin/dashboard.html requires: id, url, title, is_active, consecutive_failures."""
        row = {
            "id": 42,
            "url": "https://example.com/feed.xml",
            "title": "Example Feed",
            "is_active": 1,
            "consecutive_failures": 2,
        }
        result = feed_row_from_js(row)

        # dashboard.html line 109: data-feed-id="{{ feed.id }}"
        assert "id" in result
        # dashboard.html line 112: {{ feed.title or 'Untitled' }}
        assert "title" in result
        # dashboard.html line 119: {{ feed.url }}
        assert "url" in result
        # dashboard.html line 120-127: status based on is_active and consecutive_failures
        assert "is_active" in result
        assert "consecutive_failures" in result


class TestTemplateRequiredEntryFields:
    """Tests that fields required by templates are preserved in conversion."""

    def test_index_template_entry_fields(self):
        """index.html requires: url, title, published_at, content for entries."""
        row = {
            "id": 1,
            "feed_id": 1,
            "guid": "guid",
            "url": "https://example.com/post/1",
            "title": "Post Title",
            "author": "Author",
            "content": "<p>Content</p>",
            "published_at": "2025-01-17T10:00:00Z",
            "feed_title": "Example Feed",
            "feed_site_url": "https://example.com",
        }
        result = entry_row_from_js(row)

        # index.html line 27: href="{{ entry.url or '#' }}"
        assert "url" in result
        # index.html line 27: {{ entry.title or 'Untitled' }}
        assert "title" in result
        # index.html line 30: datetime="{{ entry.published_at }}"
        assert "published_at" in result
        # index.html line 32: {{ entry.content | safe }}
        assert "content" in result

    def test_search_template_entry_fields(self):
        """search.html requires: url, title for entry results."""
        row = {
            "id": 1,
            "feed_id": 1,
            "guid": "guid",
            "url": "https://example.com/post/1",
            "title": "Post Title",
        }
        result = entry_row_from_js(row)

        # search.html line 33: href="{{ entry.url or '#' }}"
        assert "url" in result
        # search.html line 33: {{ entry.title or 'Untitled' }}
        assert "title" in result


# =============================================================================
# Admin and Audit Conversion Tests
# =============================================================================


class TestAdminRowPreservesAllFields:
    """Tests that admin_row_from_js preserves all fields."""

    def test_preserves_all_admin_fields(self):
        """Preserves all admin table columns."""
        row = {
            "id": 1,
            "github_username": "testuser",
            "github_id": 12345,
            "display_name": "Test User",
            "is_active": 1,
            "last_login_at": "2025-01-17T12:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
        }
        result = admin_row_from_js(row)

        assert result["id"] == 1
        assert result["github_username"] == "testuser"
        assert result["github_id"] == 12345
        assert result["display_name"] == "Test User"
        assert result["is_active"] == 1
        assert result["last_login_at"] == "2025-01-17T12:00:00Z"
        assert result["created_at"] == "2025-01-01T00:00:00Z"


class TestAuditRowPreservesAllFields:
    """Tests that audit_row_from_js preserves all fields."""

    def test_preserves_all_audit_fields(self):
        """Preserves all audit_log table columns plus joined admin_username."""
        row = {
            "id": 500,
            "admin_id": 1,
            "action": "add_feed",
            "target_type": "feed",
            "target_id": 42,
            "details": '{"url": "https://example.com"}',
            "created_at": "2025-01-17T12:00:00Z",
            # Joined field
            "admin_username": "testuser",
        }
        result = audit_row_from_js(row)

        assert result["id"] == 500
        assert result["admin_id"] == 1
        assert result["action"] == "add_feed"
        assert result["target_type"] == "feed"
        assert result["target_id"] == 42
        assert result["details"] == '{"url": "https://example.com"}'
        assert result["created_at"] == "2025-01-17T12:00:00Z"
        assert result["admin_username"] == "testuser"


class TestAuditRowsFromD1PreservesFields:
    """Tests that audit_rows_from_d1 preserves all fields through batch conversion."""

    def test_preserves_joined_fields_in_batch(self):
        """audit_rows_from_d1 preserves admin_username for all audit entries."""
        results = [
            {"id": 1, "admin_id": 1, "action": "add_feed", "admin_username": "user1"},
            {"id": 2, "admin_id": 2, "action": "remove_feed", "admin_username": "user2"},
        ]
        rows = audit_rows_from_d1(results)

        assert len(rows) == 2
        assert rows[0]["admin_username"] == "user1"
        assert rows[1]["admin_username"] == "user2"


# =============================================================================
# Edge Cases and Regression Tests
# =============================================================================


class TestFieldConversionEdgeCases:
    """Tests for edge cases in field conversion."""

    def test_feed_with_zero_is_healthy_is_falsy_but_present(self):
        """is_healthy=0 should be 0, not None (important for template conditionals)."""
        row = {"id": 1, "url": "https://x.com/feed.xml", "is_healthy": 0}
        result = feed_row_from_js(row)
        assert result["is_healthy"] == 0
        assert result["is_healthy"] is not None

    def test_empty_strings_handled_correctly(self):
        """Empty string fields should be preserved as-is or converted to None based on field type."""
        row = {
            "id": 1,
            "url": "https://example.com/feed.xml",
            "title": "",  # Empty title should become None after _safe_str
        }
        result = feed_row_from_js(row)
        # _safe_str converts empty string to None
        assert result["title"] is None

    def test_batch_conversion_preserves_order(self):
        """feed_rows_from_d1 preserves the order of rows."""
        results = [
            {"id": 1, "url": "https://first.com/feed.xml"},
            {"id": 2, "url": "https://second.com/feed.xml"},
            {"id": 3, "url": "https://third.com/feed.xml"},
        ]
        rows = feed_rows_from_d1(results)
        assert [r["id"] for r in rows] == [1, 2, 3]

    def test_none_results_return_empty_containers(self):
        """Conversion functions handle None input gracefully."""
        assert feed_row_from_js(None) == {}
        assert feed_rows_from_d1(None) == []
        assert entry_row_from_js(None) == {}
        assert entry_rows_from_d1(None) == []
        assert admin_row_from_js(None) is None
        assert audit_row_from_js(None) == {}
        assert audit_rows_from_d1(None) == []
