# src/types.py
"""Type definitions for Planet CF."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Literal, NewType, NotRequired, Protocol, Self, TypedDict

# =============================================================================
# Semantic Type Aliases
# =============================================================================

# Semantic IDs - prevent mixing up feed_id and entry_id
FeedId = NewType("FeedId", int)
EntryId = NewType("EntryId", int)
AdminId = NewType("AdminId", int)

# Constrained string types
AuditAction = Literal[
    "add_feed",
    "remove_feed",
    "update_feed",
    "import_opml",
    "export_opml",
    "manual_refresh",
]

FeedStatus = Literal["active", "paused", "failing"]
ContentType = Literal["html", "atom", "rss", "opml"]


# =============================================================================
# Domain Models
# =============================================================================


@dataclass(frozen=True, slots=True)
class FeedJob:
    """Message sent to the feed queue. Immutable."""

    feed_id: FeedId
    feed_url: str
    etag: str | None = None
    last_modified: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create a FeedJob from a dictionary."""
        return cls(
            feed_id=FeedId(data["feed_id"]),
            feed_url=data["feed_url"],
            etag=data.get("etag"),
            last_modified=data.get("last_modified"),
        )


@dataclass(frozen=True, slots=True)
class Session:
    """Admin session stored in signed cookie. Immutable."""

    github_username: str
    github_id: int
    avatar_url: str | None
    exp: int  # Unix timestamp

    def is_expired(self) -> bool:
        """Check if the session has expired."""
        import time

        return self.exp < time.time()

    def to_json(self) -> str:
        """Serialize session to JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> Self:
        """Deserialize session from JSON string."""
        return cls(**json.loads(data))


@dataclass(frozen=True, slots=True)
class ParsedEntry:
    """Normalized entry from feedparser. Handles the many edge cases."""

    guid: str
    url: str
    title: str
    content: str
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None

    @classmethod
    def from_feedparser(cls, entry: dict, feed_link: str) -> Self:
        """Normalize feedparser's inconsistent output."""
        # GUID: try id, then link, then generate from title
        guid = entry.get("id") or entry.get("link") or hash(entry.get("title", ""))

        # URL: prefer link, fall back to id if it's a URL, then feed_link
        entry_id = entry.get("id", "")
        if entry.get("link"):
            url = entry["link"]
        elif entry_id.startswith("http"):
            url = entry_id
        else:
            url = feed_link

        # Content: try content[0].value, then summary, then description
        content = ""
        if entry.get("content"):
            content = entry["content"][0].get("value", "")
        elif entry.get("summary"):
            content = entry["summary"]
        elif entry.get("description"):
            content = entry["description"]

        # Published: feedparser provides parsed time tuple
        published_at = None
        if entry.get("published_parsed"):
            published_at = datetime(*entry["published_parsed"][:6])
        elif entry.get("updated_parsed"):
            published_at = datetime(*entry["updated_parsed"][:6])

        return cls(
            guid=str(guid),
            url=url,
            title=entry.get("title", "Untitled"),
            content=content,
            # Fall back to description for RSS feeds where summary may not be set
            summary=entry.get("summary") or entry.get("description"),
            author=entry.get("author"),
            published_at=published_at,
        )


# =============================================================================
# D1 Row Types
# =============================================================================


class FeedRow(TypedDict):
    """Row from the feeds table."""

    id: int
    url: str
    title: NotRequired[str | None]
    site_url: NotRequired[str | None]
    is_active: int  # SQLite boolean
    consecutive_failures: int
    etag: NotRequired[str | None]
    last_modified: NotRequired[str | None]
    last_success_at: NotRequired[str | None]
    last_error_at: NotRequired[str | None]
    last_error_message: NotRequired[str | None]
    created_at: str
    updated_at: str
    # Additional fields used in queries
    author_name: NotRequired[str | None]
    author_email: NotRequired[str | None]
    last_fetch_at: NotRequired[str | None]
    fetch_error: NotRequired[str | None]
    fetch_error_count: NotRequired[int | None]


class EntryRow(TypedDict):
    """Row from the entries table."""

    id: int
    feed_id: int
    guid: str
    url: str
    title: str
    author: NotRequired[str | None]
    content: str
    summary: NotRequired[str | None]
    published_at: str
    created_at: str
    first_seen: NotRequired[str | None]  # Added by migration 003
    # Joined fields (when querying with feeds)
    feed_title: NotRequired[str]
    feed_site_url: NotRequired[str]


class AdminRow(TypedDict):
    """Row from the admins table."""

    id: int
    github_username: str
    github_id: NotRequired[int | None]
    display_name: str
    is_active: int
    last_login_at: NotRequired[str | None]
    created_at: str


# =============================================================================
# Result Type for Error Handling
# =============================================================================


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """Success case of Result."""

    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    """Error case of Result."""

    error: E


# Result is either Ok or Err
type Result[T, E] = Ok[T] | Err[E]


class FetchError(Enum):
    """Possible errors when fetching a feed."""

    TIMEOUT = auto()
    CONNECTION_ERROR = auto()
    INVALID_URL = auto()
    NOT_FOUND = auto()
    GONE = auto()  # 410 - feed permanently removed
    PARSE_ERROR = auto()
    EMPTY_FEED = auto()
    RATE_LIMITED = auto()
    SERVER_ERROR = auto()

    def is_permanent(self) -> bool:
        """Return True if this error means we should stop retrying."""
        return self in (FetchError.INVALID_URL, FetchError.GONE, FetchError.NOT_FOUND)

    def is_transient(self) -> bool:
        """Return True if this error means we should retry later."""
        return self in (
            FetchError.TIMEOUT,
            FetchError.CONNECTION_ERROR,
            FetchError.RATE_LIMITED,
            FetchError.SERVER_ERROR,
        )


# =============================================================================
# Protocol for Testability
# =============================================================================


class ContentSanitizer(Protocol):
    """Protocol for HTML sanitization - enables testing with mocks."""

    def clean(self, html: str) -> str:
        """Sanitize HTML content and return safe HTML."""
        ...


class BleachSanitizer:
    """Production sanitizer using bleach for XSS prevention (CVE-2009-2937 mitigation)."""

    ALLOWED_TAGS = [
        "a",
        "abbr",
        "acronym",
        "b",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "figure",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "span",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    ]
    # Note: target and loading are added dynamically via callbacks
    # class is allowed on code-related elements for syntax highlighting (e.g., Expressive Code)
    ALLOWED_ATTRS = {
        "a": ["href", "title", "rel", "target"],
        "img": ["src", "alt", "title", "width", "height", "loading"],
        "abbr": ["title"],
        "acronym": ["title"],
        "code": ["class"],
        "div": ["class"],
        "figure": ["class"],
        "figcaption": ["class"],
        "pre": ["class", "data-language"],
        "span": ["class"],
    }
    ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

    def _link_callback(
        self, attrs: dict[tuple[str | None, str], str], new: bool = False
    ) -> dict[tuple[str | None, str], str]:
        """Add security attributes to links.

        Adds rel="noopener noreferrer" and target="_blank" to external links
        to prevent window.opener attacks and referrer leakage.
        """
        # Get the href attribute
        href_key = (None, "href")
        href = attrs.get(href_key, "")

        # Check if it's an external link (http/https, not same-origin)
        if href.startswith(("http://", "https://")):
            # Add target="_blank" for external links
            attrs[(None, "target")] = "_blank"
            # Add rel="noopener noreferrer" for security
            attrs[(None, "rel")] = "noopener noreferrer"

        return attrs

    def _img_callback(
        self, attrs: dict[tuple[str | None, str], str], new: bool = False
    ) -> dict[tuple[str | None, str], str]:
        """Add performance and accessibility attributes to images.

        Adds loading="lazy" for performance and ensures alt attribute exists.
        """
        # Add lazy loading for performance
        attrs[(None, "loading")] = "lazy"

        # Ensure alt attribute exists for accessibility (empty string if missing)
        alt_key = (None, "alt")
        if alt_key not in attrs:
            attrs[alt_key] = ""

        return attrs

    def clean(self, html: str) -> str:
        """Sanitize HTML content and return safe HTML."""
        import re

        import bleach

        # Pre-process: Remove script and style tags with their content
        # These tags' content should never appear in output, unlike other tags
        # where we might want to preserve text but strip the tag.
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Clean HTML with bleach
        cleaned = bleach.clean(
            html,
            tags=self.ALLOWED_TAGS,
            attributes=self.ALLOWED_ATTRS,
            protocols=self.ALLOWED_PROTOCOLS,
            strip=True,
        )

        # Post-process: Add security attributes to links and enhancements to images
        # Use regex since bleach callbacks don't work the way we need
        # Add rel="noopener noreferrer" and target="_blank" to external links
        cleaned = re.sub(
            r'<a\s+href="(https?://[^"]+)"([^>]*)>',
            r'<a href="\1" target="_blank" rel="noopener noreferrer"\2>',
            cleaned,
            flags=re.IGNORECASE,
        )

        # Add loading="lazy" to images and ensure alt exists
        def add_img_attrs(match: re.Match[str]) -> str:
            tag = match.group(0)
            # Add loading="lazy" if not present
            if "loading=" not in tag:
                tag = tag.replace("<img ", '<img loading="lazy" ')
            # Add alt="" if not present
            if "alt=" not in tag:
                tag = tag.replace("<img ", '<img alt="" ')
            return tag

        cleaned = re.sub(r"<img\s+[^>]*>", add_img_attrs, cleaned, flags=re.IGNORECASE)

        return cleaned


class NoOpSanitizer:
    """Test sanitizer that passes through unchanged."""

    def clean(self, html: str) -> str:
        """Return HTML unchanged (for testing)."""
        return html
