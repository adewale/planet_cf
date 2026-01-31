# src/content_processor.py
"""Entry content processor for extracting and processing feed entry content.

This module provides the EntryContentProcessor class that encapsulates
the content processing logic from feed entries:
- Extract content from feedparser entry (content array or summary)
- Parse published date from various formats
- Generate stable GUID
- Truncate summary to max length

Usage:
    processor = EntryContentProcessor(entry, feed_id=1)
    result = processor.process()

    # Access processed fields
    guid = result.guid
    content = result.content
    published_at = result.published_at
    summary = result.summary
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Constants
SUMMARY_MAX_LENGTH = 500


@dataclass
class ProcessedEntry:
    """Result of processing a feed entry.

    Attributes:
        guid: Stable unique identifier for the entry
        url: Entry URL (link)
        title: Entry title
        content: Extracted content (from content array or summary)
        summary: Truncated summary
        author: Entry author
        published_at: Parsed publication date (ISO format string or None)
    """

    guid: str
    url: str | None
    title: str
    content: str
    summary: str
    author: str | None
    published_at: str | None


class EntryContentProcessor:
    """Processor for feed entry content.

    Extracts and normalizes content from feedparser entries,
    handling the various formats feeds may use.

    Attributes:
        entry: The feedparser entry dict
        feed_id: ID of the feed this entry belongs to
    """

    def __init__(self, entry: dict[str, Any], feed_id: int):
        """Initialize the processor.

        Args:
            entry: Feedparser entry dict
            feed_id: ID of the feed this entry belongs to
        """
        self.entry = entry
        self.feed_id = feed_id

    def generate_guid(self) -> str:
        """Generate a stable GUID for the entry.

        Priority:
        1. Entry's id field
        2. Entry's link field
        3. Entry's title field
        4. Hash-based generated GUID

        Returns:
            Stable unique identifier string
        """
        # Try standard fields first
        guid = self.entry.get("id") or self.entry.get("link") or self.entry.get("title")

        # Ensure GUID is valid (not empty, whitespace-only, or None)
        if not guid or not str(guid).strip():
            # Generate hash-based GUID as fallback
            title = self.entry.get("title", "")
            link = self.entry.get("link", "")
            hash_input = f"{self.feed_id}:{title}:{link}".encode()
            content_hash = hashlib.sha256(hash_input).hexdigest()[:16]
            return f"generated:{content_hash}"

        return str(guid)

    def extract_content(self) -> str:
        """Extract content from the entry.

        Priority:
        1. content[0].value (Atom/RSS full content)
        2. summary field
        3. Empty string

        Returns:
            Extracted content string (may contain HTML)
        """
        # Check for content array (common in Atom feeds)
        entry_content = self.entry.get("content")
        if entry_content and isinstance(entry_content, list) and len(entry_content) > 0:
            first_content = entry_content[0]
            if isinstance(first_content, dict):
                return first_content.get("value", "")
            return str(first_content)

        # Fall back to summary
        if self.entry.get("summary"):
            return self.entry.get("summary", "")

        return ""

    def parse_published_date(self) -> str | None:
        """Parse the publication date from the entry.

        Handles feedparser's parsed time tuple format.
        Falls back to updated date if published is not available.

        Returns:
            ISO format date string, or None if not available
        """
        # Try published_parsed first
        pub_parsed = self.entry.get("published_parsed")
        if pub_parsed and isinstance(pub_parsed, (list, tuple)) and len(pub_parsed) >= 6:
            return datetime(*pub_parsed[:6]).isoformat()

        # Fall back to updated_parsed
        upd_parsed = self.entry.get("updated_parsed")
        if upd_parsed and isinstance(upd_parsed, (list, tuple)) and len(upd_parsed) >= 6:
            return datetime(*upd_parsed[:6]).isoformat()

        return None

    def truncate_summary(self, max_length: int = SUMMARY_MAX_LENGTH) -> str:
        """Get truncated summary from the entry.

        Args:
            max_length: Maximum length for summary

        Returns:
            Truncated summary with ellipsis if needed
        """
        raw_summary = self.entry.get("summary") or ""
        if len(raw_summary) > max_length:
            return raw_summary[: max_length - 3] + "..."
        return raw_summary

    def process(self) -> ProcessedEntry:
        """Process the entry and return all extracted fields.

        Returns:
            ProcessedEntry with all processed fields
        """
        return ProcessedEntry(
            guid=self.generate_guid(),
            url=self.entry.get("link"),
            title=self.entry.get("title", ""),
            content=self.extract_content(),
            summary=self.truncate_summary(),
            author=self.entry.get("author"),
            published_at=self.parse_published_date(),
        )


def process_entry(entry: dict[str, Any], feed_id: int) -> ProcessedEntry:
    """Convenience function to process a feed entry.

    Args:
        entry: Feedparser entry dict
        feed_id: ID of the feed this entry belongs to

    Returns:
        ProcessedEntry with all processed fields
    """
    processor = EntryContentProcessor(entry, feed_id)
    return processor.process()
