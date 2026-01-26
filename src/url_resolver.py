# src/url_resolver.py
"""URL resolution for relative URLs in HTML content.

This module converts relative URLs in feed content to absolute URLs using
the feed's base URL. This enables proper display of images, links, and other
resources when content is aggregated from multiple sources.

Inspired by:
- Planet Venus: Configuration-driven URL resolution with base URI handling
- Rogue Planet: Comprehensive real-world scenario coverage
"""

import re
from urllib.parse import urljoin, urlparse


class URLResolver:
    """Resolves relative URLs in HTML content to absolute URLs.

    Handles various HTML attributes (src, href, srcset, poster, data) and
    different URL patterns (absolute paths, relative paths, parent traversal).

    Example:
        resolver = URLResolver()
        resolved = resolver.resolve(
            '<img src="/images/photo.jpg">',
            "https://example.com/blog/"
        )
        # Result: '<img src="https://example.com/images/photo.jpg">'
    """

    # URL schemes that should not be modified
    PRESERVED_SCHEMES = (
        "http://",
        "https://",
        "//",  # Protocol-relative
        "data:",
        "mailto:",
        "tel:",
        "javascript:",
        "#",  # Fragment-only
    )

    # HTML attributes that contain single URLs
    URL_ATTRIBUTES = ("src", "href", "poster", "data")

    # HTML attributes that contain multiple URLs (srcset)
    SRCSET_ATTRIBUTES = ("srcset",)

    def resolve(self, content: str, base_url: str) -> str:
        """Resolve all relative URLs in HTML content to absolute URLs.

        Args:
            content: HTML content that may contain relative URLs.
            base_url: The base URL to resolve relative URLs against.

        Returns:
            HTML content with relative URLs converted to absolute URLs.
        """
        if not content:
            return ""

        # Parse base URL once for efficiency
        parsed_base = urlparse(base_url)
        base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"

        # Get the directory path (remove filename if present)
        base_path = parsed_base.path
        if base_path and not base_path.endswith("/"):
            # Remove the filename portion
            base_path = base_path.rsplit("/", 1)[0] + "/"
        elif not base_path:
            base_path = "/"

        # Construct the base URL for resolution (without query/fragment)
        resolution_base = f"{base_origin}{base_path}"

        # Process HTML comments to preserve them (store and replace with placeholders)
        comments = []
        comment_pattern = re.compile(r"<!--.*?-->", re.DOTALL)

        def save_comment(match: re.Match[str]) -> str:
            comments.append(match.group(0))
            return f"\x00COMMENT{len(comments) - 1}\x00"

        content = comment_pattern.sub(save_comment, content)

        # Resolve single URL attributes (src, href, poster, data)
        content = self._resolve_url_attributes(content, base_origin, resolution_base)

        # Resolve srcset attributes
        content = self._resolve_srcset_attributes(content, base_origin, resolution_base)

        # Restore HTML comments
        for i, comment in enumerate(comments):
            content = content.replace(f"\x00COMMENT{i}\x00", comment)

        return content

    def _resolve_url_attributes(
        self, content: str, base_origin: str, resolution_base: str
    ) -> str:
        """Resolve URLs in src, href, poster, and data attributes."""
        # Pattern matches: attr="value", attr='value', or attr=value (unquoted)
        # Case insensitive for attribute names
        attr_pattern = "|".join(re.escape(attr) for attr in self.URL_ATTRIBUTES)
        pattern = re.compile(
            rf'({attr_pattern})\s*=\s*(["\'])([^"\']*)\2',
            re.IGNORECASE,
        )

        def resolve_match(match: re.Match[str]) -> str:
            attr = match.group(1)
            quote = match.group(2)
            url = match.group(3)

            resolved = self._resolve_url(url, base_origin, resolution_base)
            return f'{attr}={quote}{resolved}{quote}'

        content = pattern.sub(resolve_match, content)

        # Handle unquoted attribute values (less common but valid)
        unquoted_pattern = re.compile(
            rf'({attr_pattern})\s*=\s*([^\s>"\']+)',
            re.IGNORECASE,
        )

        def resolve_unquoted(match: re.Match[str]) -> str:
            attr = match.group(1)
            url = match.group(2)
            resolved = self._resolve_url(url, base_origin, resolution_base)
            return f'{attr}={resolved}'

        content = unquoted_pattern.sub(resolve_unquoted, content)

        return content

    def _resolve_srcset_attributes(
        self, content: str, base_origin: str, resolution_base: str
    ) -> str:
        """Resolve URLs in srcset attributes.

        srcset contains comma-separated entries, each with a URL and optional
        width (e.g., "480w") or pixel density (e.g., "2x") descriptor.
        """
        pattern = re.compile(
            r'(srcset)\s*=\s*(["\'])([^"\']*)\2',
            re.IGNORECASE,
        )

        def resolve_srcset_match(match: re.Match[str]) -> str:
            attr = match.group(1)
            quote = match.group(2)
            srcset_value = match.group(3)

            resolved_entries = []
            # Split by comma, preserving descriptors
            entries = srcset_value.split(",")

            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue

                # Split URL from descriptor (width like "480w" or density like "2x")
                parts = entry.split()
                if parts:
                    url = parts[0]
                    descriptor = " ".join(parts[1:]) if len(parts) > 1 else ""
                    resolved_url = self._resolve_url(url, base_origin, resolution_base)
                    if descriptor:
                        resolved_entries.append(f"{resolved_url} {descriptor}")
                    else:
                        resolved_entries.append(resolved_url)

            resolved_value = ", ".join(resolved_entries)
            return f'{attr}={quote}{resolved_value}{quote}'

        return pattern.sub(resolve_srcset_match, content)

    def _resolve_url(self, url: str, base_origin: str, resolution_base: str) -> str:
        """Resolve a single URL to an absolute URL.

        Args:
            url: The URL to resolve (may be relative or absolute).
            base_origin: The origin (scheme://host:port) of the base URL.
            resolution_base: The full base URL for resolution.

        Returns:
            The resolved absolute URL, or the original URL if it should be preserved.
        """
        # Strip whitespace (including newlines)
        url = url.strip()

        # Handle null bytes safely
        url = url.replace("\x00", "")

        # Empty URLs should be preserved
        if not url:
            return url

        # Check if URL should be preserved as-is
        url_lower = url.lower()
        for scheme in self.PRESERVED_SCHEMES:
            if url_lower.startswith(scheme.lower()):
                return url

        # Resolve relative URL
        if url.startswith("/"):
            # Absolute path from origin
            return f"{base_origin}{url}"
        else:
            # Relative path - use urljoin for proper resolution
            # urljoin handles ./, ../, and complex paths correctly
            resolved = urljoin(resolution_base, url)
            return resolved


def resolve_relative_urls(content: str, base_url: str) -> str:
    """Module-level convenience function for URL resolution.

    Args:
        content: HTML content that may contain relative URLs.
        base_url: The base URL to resolve relative URLs against.

    Returns:
        HTML content with relative URLs converted to absolute URLs.

    Example:
        resolved = resolve_relative_urls(
            '<img src="/images/photo.jpg">',
            "https://example.com/blog/"
        )
    """
    resolver = URLResolver()
    return resolver.resolve(content, base_url)
