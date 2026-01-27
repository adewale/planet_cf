"""
Unit tests for Boris Tane's feed (https://boristane.com/rss.xml).

These tests verify that the feed entries are correctly parsed and displayed.
Boris's feed uses Markdown in content:encoded, which we preserve as-is.
"""

import feedparser
import pytest

from src.models import BleachSanitizer
from tests.fixtures.boristane_feed import BORISTANE_FEED_ENTRIES


class TestBoristaneFeedParsing:
    """Test that feedparser correctly parses Boris's RSS feed."""

    @pytest.fixture
    def feed_xml(self):
        """Generate RSS XML from fixture data."""
        items = []
        for entry in BORISTANE_FEED_ENTRIES:
            item = f"""<item>
                <title>{entry["title"]}</title>
                <link>{entry["link"]}</link>
                <guid isPermaLink="true">{entry["guid"]}</guid>
                <description>{entry["description"]}</description>
                <pubDate>{entry["pubDate"]}</pubDate>
                <content:encoded><![CDATA[{entry["content_encoded"]}]]></content:encoded>
                <author>{entry["author"]}</author>
            </item>"""
            items.append(item)

        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
            <channel>
                <title>Boris Tane</title>
                <description>I'm Boris Tane, and I build software</description>
                <link>https://boristane.com/</link>
                {"".join(items)}
            </channel>
        </rss>"""

    def test_parses_all_entries(self, feed_xml):
        """All entries are parsed from the feed."""
        feed_data = feedparser.parse(feed_xml)
        assert len(feed_data.entries) == len(BORISTANE_FEED_ENTRIES)

    def test_extracts_feed_title(self, feed_xml):
        """Feed title is correctly extracted."""
        feed_data = feedparser.parse(feed_xml)
        assert feed_data.feed.get("title") == "Boris Tane"

    def test_extracts_entry_titles(self, feed_xml):
        """Entry titles are correctly extracted."""
        feed_data = feedparser.parse(feed_xml)
        expected_titles = [e["title"] for e in BORISTANE_FEED_ENTRIES]
        actual_titles = [e.get("title") for e in feed_data.entries]
        assert actual_titles == expected_titles

    def test_extracts_content_encoded(self, feed_xml):
        """content:encoded is extracted as content."""
        feed_data = feedparser.parse(feed_xml)
        for i, entry in enumerate(feed_data.entries):
            # feedparser puts content:encoded in entry.content
            content = entry.content[0].value if entry.get("content") else entry.get("summary", "")
            expected = BORISTANE_FEED_ENTRIES[i]["content_encoded"]
            # Check that at least the first 100 chars match (content may have minor differences)
            assert expected[:100] in content or content[:100] in expected[:200]

    def test_extracts_publication_dates(self, feed_xml):
        """Publication dates are correctly extracted."""
        feed_data = feedparser.parse(feed_xml)
        for entry in feed_data.entries:
            assert (
                entry.get("published_parsed") is not None or entry.get("updated_parsed") is not None
            )


class TestBoristaneContentSanitization:
    """Test that Boris's Markdown content is preserved through sanitization."""

    @pytest.fixture
    def sanitizer(self):
        return BleachSanitizer()

    def test_preserves_markdown_links(self, sanitizer):
        """Markdown link syntax [text](url) is preserved."""
        content = "External link to [loggingsucks.com](https://loggingsucks.com)"
        result = sanitizer.clean(content)
        assert "[loggingsucks.com]" in result
        assert "(https://loggingsucks.com)" in result

    def test_preserves_markdown_headers(self, sanitizer):
        """Markdown header syntax ## is preserved."""
        content = "## The Problem: State in Serverless\n\nSome text here."
        result = sanitizer.clean(content)
        assert "## The Problem" in result

    def test_preserves_markdown_code_blocks(self, sanitizer):
        """Markdown code block syntax ``` is preserved."""
        content = "```typescript\nconst x = 1;\n```"
        result = sanitizer.clean(content)
        assert "```typescript" in result
        assert "const x = 1;" in result

    def test_preserves_markdown_lists(self, sanitizer):
        """Markdown list syntax is preserved."""
        content = "- Item one\n- Item two\n- Item three"
        result = sanitizer.clean(content)
        assert "- Item one" in result
        assert "- Item two" in result

    def test_preserves_markdown_blockquotes(self, sanitizer):
        """Markdown blockquote syntax > is preserved (may be HTML-encoded)."""
        content = "> This is a quote\n> spanning multiple lines"
        result = sanitizer.clean(content)
        # The > may be HTML-encoded as &gt; by the sanitizer
        assert "> This is a quote" in result or "&gt; This is a quote" in result

    def test_preserves_mermaid_diagrams(self, sanitizer):
        """Mermaid diagram code blocks are preserved."""
        content = """```mermaid
graph TB
    User[User Requests] --> Worker[Worker]
```"""
        result = sanitizer.clean(content)
        assert "```mermaid" in result
        assert "graph TB" in result

    @pytest.mark.parametrize(
        "entry_index,expected_substring",
        [
            (0, "[loggingsucks.com](https://loggingsucks.com)"),  # Logging Sucks
            (1, "## The Problem: State in Serverless"),  # Durable Objects
            (1, "```mermaid"),  # Durable Objects has mermaid
            (2, "## The Multi-Tenancy Problem"),  # Graph Databases
            (3, "## What is context?"),  # Context Engineering
        ],
    )
    def test_preserves_actual_entry_content(self, sanitizer, entry_index, expected_substring):
        """Actual entry content from Boris's feed is preserved."""
        if entry_index < len(BORISTANE_FEED_ENTRIES):
            content = BORISTANE_FEED_ENTRIES[entry_index]["content_encoded"]
            result = sanitizer.clean(content)
            assert expected_substring in result


class TestBoristaneEntryCharacteristics:
    """Test specific characteristics of Boris's feed entries."""

    def test_logging_sucks_is_external_link(self):
        """'Logging Sucks' entry is just an external link."""
        entry = BORISTANE_FEED_ENTRIES[0]
        assert entry["title"] == "Logging Sucks"
        assert len(entry["content_encoded"]) < 100
        assert "loggingsucks.com" in entry["content_encoded"]

    def test_durable_objects_has_substantial_content(self):
        """'Durable Objects' entry has substantial content."""
        entry = BORISTANE_FEED_ENTRIES[1]
        assert entry["title"] == "What even are Cloudflare Durable Objects?"
        assert len(entry["content_encoded"]) > 30000

    def test_all_entries_have_author(self):
        """All entries have Boris Tane as author."""
        for entry in BORISTANE_FEED_ENTRIES:
            assert entry["author"] == "Boris Tane"

    def test_all_entries_have_guid(self):
        """All entries have a GUID (permalink)."""
        for entry in BORISTANE_FEED_ENTRIES:
            assert entry["guid"].startswith("https://boristane.com/")

    def test_entries_have_descriptions(self):
        """All entries have non-empty descriptions."""
        for entry in BORISTANE_FEED_ENTRIES:
            assert len(entry["description"]) > 0

    def test_content_contains_markdown_not_html(self):
        """Content uses Markdown syntax, not HTML tags for formatting."""
        # Check the Durable Objects entry (rich content)
        entry = BORISTANE_FEED_ENTRIES[1]
        content = entry["content_encoded"]

        # Should have Markdown syntax
        assert "##" in content  # Headers
        assert "```" in content  # Code blocks
        assert "[" in content and "](" in content  # Links

        # Should NOT have HTML formatting tags (except maybe embedded HTML)
        # The content is primarily Markdown
        assert content.count("<h2>") < content.count("## ")
        assert content.count("<pre>") < content.count("```")


class TestBoristaneRetentionFiltering:
    """Test which entries would be included under retention policy."""

    def test_entries_within_90_days(self):
        """Identify entries that would be within 90-day retention.

        As of Jan 27, 2026, only entries after Oct 29, 2025 qualify.
        """
        from datetime import datetime

        # Parse dates and check which are within retention
        within_retention = []
        cutoff = datetime(2025, 10, 29)

        for entry in BORISTANE_FEED_ENTRIES:
            # Parse "Sun, 21 Dec 2025 00:00:00 GMT" format
            pub_date_str = entry["pubDate"]
            try:
                pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z")
                if pub_date >= cutoff:
                    within_retention.append(entry["title"])
            except ValueError:
                pass

        # As of the test snapshot, should have 2 entries within retention
        assert "Logging Sucks" in within_retention
        assert "What even are Cloudflare Durable Objects?" in within_retention
        assert len(within_retention) == 2
