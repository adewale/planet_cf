# tests/unit/test_content_processor.py
"""Tests for the entry content processor."""

from src.content_processor import (
    SUMMARY_MAX_LENGTH,
    EntryContentProcessor,
    ProcessedEntry,
    process_entry,
)


class TestProcessedEntry:
    """Tests for ProcessedEntry dataclass."""

    def test_entry_properties(self):
        """ProcessedEntry has correct properties."""
        entry = ProcessedEntry(
            guid="entry-1",
            url="https://example.com/post",
            title="Test Post",
            content="<p>Content</p>",
            summary="Summary text",
            author="John Doe",
            published_at="2026-01-15T12:00:00",
        )

        assert entry.guid == "entry-1"
        assert entry.url == "https://example.com/post"
        assert entry.title == "Test Post"
        assert entry.content == "<p>Content</p>"
        assert entry.summary == "Summary text"
        assert entry.author == "John Doe"
        assert entry.published_at == "2026-01-15T12:00:00"

    def test_optional_fields_can_be_none(self):
        """Optional fields can be None."""
        entry = ProcessedEntry(
            guid="entry-1",
            url=None,
            title="Test",
            content="Content",
            summary="",
            author=None,
            published_at=None,
        )

        assert entry.url is None
        assert entry.author is None
        assert entry.published_at is None


class TestEntryContentProcessorGUID:
    """Tests for GUID generation."""

    def test_guid_from_id_field(self):
        """Uses entry id field as GUID."""
        entry = {"id": "unique-id-123", "link": "https://example.com", "title": "Test"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.generate_guid() == "unique-id-123"

    def test_guid_from_link_when_no_id(self):
        """Falls back to link when id is missing."""
        entry = {"link": "https://example.com/post/1", "title": "Test"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.generate_guid() == "https://example.com/post/1"

    def test_guid_from_title_when_no_id_or_link(self):
        """Falls back to title when id and link are missing."""
        entry = {"title": "My Post Title"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.generate_guid() == "My Post Title"

    def test_guid_generated_when_all_empty(self):
        """Generates hash-based GUID when all fields are empty."""
        entry = {"id": "", "link": "", "title": ""}
        processor = EntryContentProcessor(entry, feed_id=42)

        guid = processor.generate_guid()
        assert guid.startswith("generated:")
        assert len(guid) > 10

    def test_guid_generated_when_whitespace_only(self):
        """Generates hash-based GUID when fields are whitespace only."""
        entry = {"id": "   ", "link": None, "title": None}
        processor = EntryContentProcessor(entry, feed_id=1)

        guid = processor.generate_guid()
        assert guid.startswith("generated:")

    def test_guid_generation_is_deterministic(self):
        """Generated GUID is deterministic for same inputs."""
        entry = {"title": "Same Title", "link": "Same Link"}
        processor1 = EntryContentProcessor(entry, feed_id=1)
        processor2 = EntryContentProcessor(entry, feed_id=1)

        assert processor1.generate_guid() == processor2.generate_guid()

    def test_guid_generation_differs_by_feed(self):
        """Generated hash-based GUID differs by feed_id."""
        # Use empty values so hash-based GUID is generated
        entry = {"id": "", "title": "", "link": ""}
        processor1 = EntryContentProcessor(entry, feed_id=1)
        processor2 = EntryContentProcessor(entry, feed_id=2)

        guid1 = processor1.generate_guid()
        guid2 = processor2.generate_guid()

        assert guid1.startswith("generated:")
        assert guid2.startswith("generated:")
        assert guid1 != guid2


class TestEntryContentProcessorContent:
    """Tests for content extraction."""

    def test_extracts_from_content_array(self):
        """Extracts content from content[0].value."""
        entry = {
            "content": [{"value": "<p>Full content here</p>", "type": "text/html"}],
            "summary": "Short summary",
        }
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.extract_content() == "<p>Full content here</p>"

    def test_extracts_string_from_content_array(self):
        """Handles string content in content array."""
        entry = {"content": ["Plain text content"], "summary": "Summary"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.extract_content() == "Plain text content"

    def test_falls_back_to_summary(self):
        """Falls back to summary when content is missing."""
        entry = {"summary": "This is the summary text"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.extract_content() == "This is the summary text"

    def test_returns_empty_when_no_content(self):
        """Returns empty string when no content fields."""
        entry = {"title": "No Content"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.extract_content() == ""

    def test_handles_empty_content_array(self):
        """Handles empty content array gracefully."""
        entry = {"content": [], "summary": "Fallback"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.extract_content() == "Fallback"

    def test_handles_none_content(self):
        """Handles None content field."""
        entry = {"content": None, "summary": "Fallback"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.extract_content() == "Fallback"


class TestEntryContentProcessorDate:
    """Tests for date parsing."""

    def test_parses_published_parsed(self):
        """Parses published_parsed time tuple."""
        entry = {"published_parsed": (2026, 1, 15, 12, 30, 45, 0, 0, 0)}
        processor = EntryContentProcessor(entry, feed_id=1)

        result = processor.parse_published_date()
        assert result == "2026-01-15T12:30:45"

    def test_parses_updated_parsed_fallback(self):
        """Falls back to updated_parsed when published_parsed missing."""
        entry = {"updated_parsed": (2026, 2, 20, 8, 0, 0, 0, 0, 0)}
        processor = EntryContentProcessor(entry, feed_id=1)

        result = processor.parse_published_date()
        assert result == "2026-02-20T08:00:00"

    def test_prefers_published_over_updated(self):
        """Prefers published_parsed over updated_parsed."""
        entry = {
            "published_parsed": (2026, 1, 1, 0, 0, 0, 0, 0, 0),
            "updated_parsed": (2026, 12, 31, 23, 59, 59, 0, 0, 0),
        }
        processor = EntryContentProcessor(entry, feed_id=1)

        result = processor.parse_published_date()
        assert result == "2026-01-01T00:00:00"

    def test_returns_none_when_no_dates(self):
        """Returns None when no date fields present."""
        entry = {"title": "No Date"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.parse_published_date() is None

    def test_handles_short_time_tuple(self):
        """Handles time tuple with fewer than 6 elements."""
        entry = {"published_parsed": (2026, 1, 15)}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.parse_published_date() is None

    def test_handles_list_time_tuple(self):
        """Handles time as list instead of tuple."""
        entry = {"published_parsed": [2026, 3, 10, 15, 0, 0]}
        processor = EntryContentProcessor(entry, feed_id=1)

        result = processor.parse_published_date()
        assert result == "2026-03-10T15:00:00"


class TestEntryContentProcessorSummary:
    """Tests for summary truncation."""

    def test_short_summary_unchanged(self):
        """Short summary is returned unchanged."""
        entry = {"summary": "Short summary"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.truncate_summary() == "Short summary"

    def test_long_summary_truncated(self):
        """Long summary is truncated with ellipsis."""
        long_summary = "A" * 600
        entry = {"summary": long_summary}
        processor = EntryContentProcessor(entry, feed_id=1)

        result = processor.truncate_summary()
        assert len(result) == SUMMARY_MAX_LENGTH
        assert result.endswith("...")

    def test_custom_max_length(self):
        """Custom max length is respected."""
        entry = {"summary": "A" * 200}
        processor = EntryContentProcessor(entry, feed_id=1)

        result = processor.truncate_summary(max_length=100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_missing_summary(self):
        """Returns empty string when summary missing."""
        entry = {"title": "No Summary"}
        processor = EntryContentProcessor(entry, feed_id=1)

        assert processor.truncate_summary() == ""


class TestEntryContentProcessorProcess:
    """Tests for full entry processing."""

    def test_process_returns_all_fields(self):
        """process() returns ProcessedEntry with all fields."""
        entry = {
            "id": "entry-123",
            "link": "https://example.com/post",
            "title": "Test Post",
            "content": [{"value": "<p>Content</p>"}],
            "summary": "Summary text",
            "author": "Author Name",
            "published_parsed": (2026, 1, 15, 12, 0, 0),
        }
        processor = EntryContentProcessor(entry, feed_id=1)

        result = processor.process()

        assert isinstance(result, ProcessedEntry)
        assert result.guid == "entry-123"
        assert result.url == "https://example.com/post"
        assert result.title == "Test Post"
        assert result.content == "<p>Content</p>"
        assert result.summary == "Summary text"
        assert result.author == "Author Name"
        assert result.published_at == "2026-01-15T12:00:00"

    def test_process_handles_minimal_entry(self):
        """process() handles entry with minimal fields."""
        entry = {"title": "Minimal"}
        processor = EntryContentProcessor(entry, feed_id=1)

        result = processor.process()

        assert result.title == "Minimal"
        assert result.content == ""
        assert result.published_at is None


class TestProcessEntryFunction:
    """Tests for convenience function."""

    def test_process_entry_function(self):
        """process_entry() convenience function works."""
        entry = {
            "id": "test-id",
            "title": "Test",
            "content": [{"value": "Content"}],
        }

        result = process_entry(entry, feed_id=1)

        assert isinstance(result, ProcessedEntry)
        assert result.guid == "test-id"
        assert result.content == "Content"
