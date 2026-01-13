# src/types.py
"""Type definitions for Planet CF."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from typing import Generic, Literal, NewType, NotRequired, Protocol, Self, TypedDict, TypeVar
import json

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
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
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
        import time

        return self.exp < time.time()

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> Self:
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

        # URL: prefer link, fall back to id if it's a URL
        url = entry.get("link") or (
            entry.get("id") if entry.get("id", "").startswith("http") else feed_link
        )

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
            summary=entry.get("summary"),
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
    last_etag: NotRequired[str | None]
    last_modified_header: NotRequired[str | None]
    last_success_at: NotRequired[str | None]
    last_error_at: NotRequired[str | None]
    last_error_message: NotRequired[str | None]
    created_at: str
    updated_at: str


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

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Success case of Result."""

    value: T


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
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
        """Should we stop retrying?"""
        return self in (FetchError.INVALID_URL, FetchError.GONE, FetchError.NOT_FOUND)

    def is_transient(self) -> bool:
        """Should we retry?"""
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

    def clean(self, html: str) -> str: ...


class BleachSanitizer:
    """Production sanitizer using bleach."""

    ALLOWED_TAGS = [
        "a",
        "abbr",
        "acronym",
        "b",
        "blockquote",
        "code",
        "em",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "strong",
        "ul",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "br",
        "hr",
        "img",
        "figure",
        "figcaption",
    ]
    ALLOWED_ATTRS = {
        "a": ["href", "title"],
        "img": ["src", "alt", "title"],
        "abbr": ["title"],
        "acronym": ["title"],
    }

    def clean(self, html: str) -> str:
        import bleach

        return bleach.clean(
            html,
            tags=self.ALLOWED_TAGS,
            attributes=self.ALLOWED_ATTRS,
            strip=True,
        )


class NoOpSanitizer:
    """Test sanitizer that passes through unchanged."""

    def clean(self, html: str) -> str:
        return html
