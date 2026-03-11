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


class TestFeedProvidedIdentifiers:
    """The feed is responsible for providing permanent entry identifiers.

    Per RFC 4287 (Atom) and RSS 2.0, the entry's identifier (atom:id or
    <guid>) is a permanent, opaque string chosen by the feed publisher.
    The aggregator MUST use it verbatim — never rewrite, normalise, or
    second-guess it.  These tests enforce that contract across the
    identifier formats commonly seen in real-world Atom and RSS feeds.

    feedparser normalises both atom:id and RSS <guid> into entry["id"].
    """

    # -----------------------------------------------------------------
    # Atom feeds — atom:id (RFC 4287 §4.2.6)
    # -----------------------------------------------------------------

    def test_atom_tag_uri(self):
        """Atom tag URI (RFC 4151) is used verbatim.

        Tag URIs are the recommended way to mint permanent Atom IDs:
          <id>tag:example.com,2025:post-42</id>
        """
        entry = {
            "id": "tag:example.com,2025:post-42",
            "link": "https://example.com/posts/42",
            "title": "Post 42",
        }
        processor = EntryContentProcessor(entry, feed_id=1)
        assert processor.generate_guid() == "tag:example.com,2025:post-42"

    def test_atom_urn_uuid(self):
        """Atom URN:UUID identifier is used verbatim.

        Some generators mint UUIDs:
          <id>urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a</id>
        """
        entry = {
            "id": "urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a",
            "link": "https://example.com/entry",
            "title": "UUID Entry",
        }
        processor = EntryContentProcessor(entry, feed_id=1)
        assert processor.generate_guid() == "urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a"

    def test_atom_http_id_distinct_from_link(self):
        """Atom HTTP-based ID that differs from the link is used verbatim.

        Some feeds mint a permanent URL as the ID that is different from
        the current permalink (e.g. a versioned URL or a resolver):
          <id>https://example.com/entries/42</id>
          <link href="https://example.com/posts/my-title" />
        """
        entry = {
            "id": "https://example.com/entries/42",
            "link": "https://example.com/posts/my-title",
            "title": "My Title",
        }
        processor = EntryContentProcessor(entry, feed_id=1)
        assert processor.generate_guid() == "https://example.com/entries/42"

    def test_atom_id_not_normalised(self):
        """Atom IDs are compared character-by-character (RFC 4287 §4.2.6.1).

        The aggregator must not normalise case, trailing slashes, or
        percent-encoding.  Two IDs that look "equivalent" as URLs are
        still distinct identifiers.
        """
        entry_a = {
            "id": "https://Example.COM/Post/42",
            "link": "https://example.com/post/42",
            "title": "Post",
        }
        entry_b = {
            "id": "https://example.com/post/42",
            "link": "https://example.com/post/42",
            "title": "Post",
        }
        guid_a = EntryContentProcessor(entry_a, feed_id=1).generate_guid()
        guid_b = EntryContentProcessor(entry_b, feed_id=1).generate_guid()

        assert guid_a == "https://Example.COM/Post/42"
        assert guid_b == "https://example.com/post/42"
        assert guid_a != guid_b

    # -----------------------------------------------------------------
    # RSS feeds — <guid> (RSS 2.0 spec)
    # -----------------------------------------------------------------

    def test_rss_guid_ispermalink_true(self):
        """RSS <guid isPermaLink="true"> is used verbatim.

        feedparser maps <guid> to entry["id"].  When isPermaLink="true"
        (the default), the GUID doubles as a browsable URL, but it is
        still an opaque identifier from the aggregator's perspective.
        """
        # feedparser sets id == link when guid isPermaLink="true"
        entry = {
            "id": "https://example.com/2025/hello-world",
            "link": "https://example.com/2025/hello-world",
            "title": "Hello World",
        }
        processor = EntryContentProcessor(entry, feed_id=1)
        assert processor.generate_guid() == "https://example.com/2025/hello-world"

    def test_rss_guid_ispermalink_false(self):
        """RSS <guid isPermaLink="false"> is used verbatim.

        Non-permalink GUIDs are arbitrary opaque strings:
          <guid isPermaLink="false">post-20250115-abc</guid>
        """
        entry = {
            "id": "post-20250115-abc",
            "link": "https://example.com/hello",
            "title": "Hello",
        }
        processor = EntryContentProcessor(entry, feed_id=1)
        assert processor.generate_guid() == "post-20250115-abc"

    def test_rss_guid_numeric(self):
        """RSS numeric GUID (e.g. database row ID) is used verbatim."""
        entry = {
            "id": "98765",
            "link": "https://example.com/article/98765",
            "title": "Article",
        }
        processor = EntryContentProcessor(entry, feed_id=1)
        assert processor.generate_guid() == "98765"

    # -----------------------------------------------------------------
    # Feeds that omit an explicit identifier
    # -----------------------------------------------------------------

    def test_missing_id_falls_back_to_link(self):
        """When the feed provides no id, the link is the next best thing.

        Many RSS feeds omit <guid> entirely.  feedparser then leaves
        entry["id"] unset, and the link is the most specific fallback.
        """
        entry = {
            "link": "https://example.com/no-guid",
            "title": "No GUID",
        }
        processor = EntryContentProcessor(entry, feed_id=1)
        assert processor.generate_guid() == "https://example.com/no-guid"

    def test_missing_id_and_link_falls_back_to_title(self):
        """When neither id nor link exist, title is the last textual fallback."""
        entry = {"title": "Only a Title"}
        processor = EntryContentProcessor(entry, feed_id=1)
        assert processor.generate_guid() == "Only a Title"

    def test_completely_empty_entry_gets_generated_guid(self):
        """Entries with no usable fields get a deterministic generated GUID."""
        entry = {"id": "", "link": "", "title": ""}
        processor = EntryContentProcessor(entry, feed_id=1)
        guid = processor.generate_guid()

        assert guid.startswith("generated:")

    # -----------------------------------------------------------------
    # The aggregator never rewrites a feed-provided identifier
    # -----------------------------------------------------------------

    def test_id_never_replaced_by_hash(self):
        """A non-empty id is never replaced with a generated hash.

        The aggregator must not invent its own identifier when the feed
        has already provided one — even if the id happens to equal the
        link (permalink-as-GUID pattern).
        """
        entry = {
            "id": "https://example.com/post/slug",
            "link": "https://example.com/post/slug",
            "title": "Slug Post",
        }
        processor = EntryContentProcessor(entry, feed_id=1)
        guid = processor.generate_guid()

        assert not guid.startswith("generated:")
        assert guid == "https://example.com/post/slug"

    def test_id_preserved_across_repeated_processing(self):
        """Processing the same entry twice yields the same feed-provided id."""
        entry = {
            "id": "tag:blog.example.com,2026:entry-7",
            "link": "https://blog.example.com/entry-7",
            "title": "Entry 7",
        }
        guid1 = EntryContentProcessor(entry, feed_id=1).generate_guid()
        guid2 = EntryContentProcessor(entry, feed_id=1).generate_guid()

        assert guid1 == guid2 == "tag:blog.example.com,2026:entry-7"


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
