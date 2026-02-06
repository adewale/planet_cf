# tests/unit/test_models.py
"""Unit tests for domain model types."""

import json
import time

import pytest
from freezegun import freeze_time

from src.models import (
    BleachSanitizer,
    Err,
    FeedId,
    FeedJob,
    FetchError,
    Ok,
    ParsedEntry,
    Result,
    Session,
)


class TestFeedJob:
    """Tests for FeedJob dataclass."""

    def test_create_with_required_fields(self):
        """FeedJob can be created with only required fields."""
        job = FeedJob(feed_id=FeedId(1), feed_url="https://example.com/feed.xml")
        assert job.feed_id == 1
        assert job.feed_url == "https://example.com/feed.xml"
        assert job.etag is None
        assert job.last_modified is None

    def test_create_with_optional_fields(self):
        """FeedJob can include optional caching headers."""
        job = FeedJob(
            feed_id=FeedId(1),
            feed_url="https://example.com/feed.xml",
            etag='"abc123"',
            last_modified="Sat, 01 Jan 2026 00:00:00 GMT",
        )
        assert job.etag == '"abc123"'
        assert job.last_modified == "Sat, 01 Jan 2026 00:00:00 GMT"

    def test_to_dict_roundtrip(self):
        """FeedJob survives serialization roundtrip."""
        original = FeedJob(feed_id=FeedId(42), feed_url="https://test.com/rss")
        as_dict = original.to_dict()
        restored = FeedJob.from_dict(as_dict)
        assert restored == original

    def test_to_dict_with_all_fields(self):
        """FeedJob.to_dict includes all fields."""
        job = FeedJob(
            feed_id=FeedId(1),
            feed_url="https://example.com/feed.xml",
            etag='"abc"',
            last_modified="date",
        )
        d = job.to_dict()
        assert d["feed_id"] == 1
        assert d["feed_url"] == "https://example.com/feed.xml"
        assert d["etag"] == '"abc"'
        assert d["last_modified"] == "date"

    def test_immutable(self):
        """FeedJob is immutable (frozen dataclass)."""
        job = FeedJob(feed_id=FeedId(1), feed_url="https://example.com/feed.xml")
        with pytest.raises(AttributeError):
            job.feed_url = "https://other.com/feed.xml"


class TestSession:
    """Tests for Session dataclass."""

    @freeze_time("2026-01-01 12:00:00")
    def test_not_expired(self):
        """Session with future exp is not expired."""
        session = Session(
            github_username="testuser",
            github_id=123,
            avatar_url=None,
            exp=int(time.time()) + 3600,  # 1 hour from now
        )
        assert not session.is_expired()

    @freeze_time("2026-01-01 12:00:00")
    def test_expired(self):
        """Session with past exp is expired."""
        session = Session(
            github_username="testuser",
            github_id=123,
            avatar_url=None,
            exp=int(time.time()) - 1,  # 1 second ago
        )
        assert session.is_expired()

    def test_json_roundtrip(self):
        """Session survives JSON roundtrip."""
        original = Session(
            github_username="testuser",
            github_id=123,
            avatar_url="https://github.com/testuser.png",
            exp=1234567890,
        )
        as_json = original.to_json()
        restored = Session.from_json(as_json)
        assert restored == original

    def test_to_json_format(self):
        """Session.to_json produces valid JSON."""
        session = Session(
            github_username="test",
            github_id=1,
            avatar_url=None,
            exp=12345,
        )
        as_json = session.to_json()
        parsed = json.loads(as_json)
        assert parsed["github_username"] == "test"
        assert parsed["github_id"] == 1
        assert parsed["avatar_url"] is None
        assert parsed["exp"] == 12345


class TestParsedEntry:
    """Tests for ParsedEntry dataclass."""

    def test_from_feedparser_minimal(self):
        """ParsedEntry handles minimal feedparser output."""
        raw = {
            "id": "entry-1",
            "link": "https://example.com/post",
            "title": "Test Post",
            "summary": "A test post",
        }
        entry = ParsedEntry.from_feedparser(raw, "https://example.com")
        assert entry.guid == "entry-1"
        assert entry.url == "https://example.com/post"
        assert entry.title == "Test Post"
        assert entry.content == "A test post"  # Falls back to summary

    def test_from_feedparser_with_content(self):
        """ParsedEntry prefers content over summary."""
        raw = {
            "id": "entry-1",
            "link": "https://example.com/post",
            "title": "Test Post",
            "content": [{"value": "<p>Full content</p>"}],
            "summary": "Short summary",
        }
        entry = ParsedEntry.from_feedparser(raw, "https://example.com")
        assert entry.content == "<p>Full content</p>"

    def test_from_feedparser_with_published_date(self):
        """ParsedEntry parses published_parsed time tuple."""
        raw = {
            "id": "entry-1",
            "link": "https://example.com/post",
            "title": "Test Post",
            "summary": "Test",
            "published_parsed": (2026, 1, 15, 10, 30, 0, 0, 0, 0),
        }
        entry = ParsedEntry.from_feedparser(raw, "https://example.com")
        assert entry.published_at.year == 2026
        assert entry.published_at.month == 1
        assert entry.published_at.day == 15

    def test_from_feedparser_uses_updated_if_no_published(self):
        """ParsedEntry falls back to updated_parsed."""
        raw = {
            "id": "entry-1",
            "link": "https://example.com/post",
            "title": "Test Post",
            "summary": "Test",
            "updated_parsed": (2026, 2, 20, 8, 0, 0, 0, 0, 0),
        }
        entry = ParsedEntry.from_feedparser(raw, "https://example.com")
        assert entry.published_at.year == 2026
        assert entry.published_at.month == 2
        assert entry.published_at.day == 20

    def test_from_feedparser_missing_guid_uses_link(self):
        """ParsedEntry uses link as guid when id missing."""
        raw = {
            "link": "https://example.com/post",
            "title": "Test Post",
            "summary": "Test",
        }
        entry = ParsedEntry.from_feedparser(raw, "https://example.com")
        assert entry.guid == "https://example.com/post"

    def test_from_feedparser_uses_description(self):
        """ParsedEntry uses description when no summary/content."""
        raw = {
            "id": "entry-1",
            "link": "https://example.com/post",
            "title": "Test Post",
            "description": "Description text",
        }
        entry = ParsedEntry.from_feedparser(raw, "https://example.com")
        assert entry.content == "Description text"

    def test_from_feedparser_default_title(self):
        """ParsedEntry uses 'Untitled' when title missing."""
        raw = {
            "id": "entry-1",
            "link": "https://example.com/post",
            "summary": "Test",
        }
        entry = ParsedEntry.from_feedparser(raw, "https://example.com")
        assert entry.title == "Untitled"


class TestResult:
    """Tests for Result type (Ok/Err)."""

    def test_ok_value(self):
        """Ok wraps a success value."""
        result: Result[int, str] = Ok(42)
        match result:
            case Ok(value):
                assert value == 42
            case Err(_):
                pytest.fail("Expected Ok")

    def test_err_value(self):
        """Err wraps an error value."""
        result: Result[int, FetchError] = Err(FetchError.TIMEOUT)
        match result:
            case Ok(_):
                pytest.fail("Expected Err")
            case Err(error):
                assert error == FetchError.TIMEOUT

    def test_ok_equality(self):
        """Ok values are equal if their contents are equal."""
        assert Ok(42) == Ok(42)
        assert Ok("test") == Ok("test")
        assert Ok(42) != Ok(43)

    def test_err_equality(self):
        """Err values are equal if their errors are equal."""
        assert Err(FetchError.TIMEOUT) == Err(FetchError.TIMEOUT)
        assert Err(FetchError.TIMEOUT) != Err(FetchError.NOT_FOUND)


class TestFetchError:
    """Tests for FetchError enum."""

    def test_is_permanent_for_permanent_errors(self):
        """is_permanent returns True for permanent errors."""
        assert FetchError.GONE.is_permanent()
        assert FetchError.NOT_FOUND.is_permanent()
        assert FetchError.INVALID_URL.is_permanent()

    def test_is_permanent_for_transient_errors(self):
        """is_permanent returns False for transient errors."""
        assert not FetchError.TIMEOUT.is_permanent()
        assert not FetchError.RATE_LIMITED.is_permanent()
        assert not FetchError.SERVER_ERROR.is_permanent()

    def test_is_transient_for_transient_errors(self):
        """is_transient returns True for transient errors."""
        assert FetchError.TIMEOUT.is_transient()
        assert FetchError.CONNECTION_ERROR.is_transient()
        assert FetchError.RATE_LIMITED.is_transient()
        assert FetchError.SERVER_ERROR.is_transient()

    def test_is_transient_for_permanent_errors(self):
        """is_transient returns False for permanent errors."""
        assert not FetchError.GONE.is_transient()
        assert not FetchError.NOT_FOUND.is_transient()
        assert not FetchError.INVALID_URL.is_transient()

    def test_parse_error_is_neither(self):
        """PARSE_ERROR is neither permanent nor transient."""
        assert not FetchError.PARSE_ERROR.is_permanent()
        assert not FetchError.PARSE_ERROR.is_transient()


class TestBleachSanitizer:
    """Tests for BleachSanitizer HTML sanitization."""

    def setup_method(self):
        """Create a sanitizer instance for each test."""
        self.sanitizer = BleachSanitizer()

    def test_strips_href_with_javascript_in_url_path(self):
        """Links with javascript: in the URL path have their href removed."""
        html = '<a href="https://example.com/path/javascript:void(0);">click</a>'
        result = self.sanitizer.clean(html)
        assert "javascript:" not in result
        assert "click" in result
        assert "href" not in result

    def test_strips_href_with_javascript_as_protocol(self):
        """Links with javascript: as protocol have their href removed."""
        html = '<a href="javascript:void(0)">click</a>'
        result = self.sanitizer.clean(html)
        assert "javascript:" not in result
        assert "click" in result

    def test_preserves_normal_https_links(self):
        """Normal https links are preserved unchanged."""
        html = '<a href="https://example.com/page">click</a>'
        result = self.sanitizer.clean(html)
        assert 'href="https://example.com/page"' in result
        assert "click" in result

    def test_strips_javascript_href_case_insensitive(self):
        """javascript: detection is case-insensitive."""
        html = '<a href="https://example.com/JavaScript:void(0);">click</a>'
        result = self.sanitizer.clean(html)
        assert "JavaScript:" not in result
        assert "javascript:" not in result.lower()
        assert "click" in result
        assert "href" not in result

    def test_preserves_link_text_after_stripping(self):
        """Link text is preserved when href is stripped."""
        html = '<a href="https://example.com/javascript:alert(1)">important text</a>'
        result = self.sanitizer.clean(html)
        assert "important text" in result
        assert "<a" in result
        assert "</a>" in result
