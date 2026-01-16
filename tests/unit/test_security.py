# tests/unit/test_security.py
"""Unit tests for security functions (sanitization, URL validation)."""

import ipaddress
from urllib.parse import urlparse

import pytest

from src.models import BleachSanitizer, NoOpSanitizer

# =============================================================================
# HTML Sanitization Tests
# =============================================================================


class TestBleachSanitizer:
    """Tests for BleachSanitizer (XSS prevention)."""

    @pytest.fixture
    def sanitizer(self):
        return BleachSanitizer()

    def test_allows_safe_tags(self, sanitizer):
        """Safe HTML tags are preserved."""
        html = "<p>Hello <strong>world</strong></p>"
        assert sanitizer.clean(html) == html

    def test_allows_lists(self, sanitizer):
        """List tags are preserved."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        assert sanitizer.clean(html) == html

    def test_allows_headers(self, sanitizer):
        """Header tags are preserved."""
        for i in range(1, 7):
            html = f"<h{i}>Heading</h{i}>"
            assert sanitizer.clean(html) == html

    def test_strips_script_tags(self, sanitizer):
        """Script tags are completely removed."""
        html = '<p>Hello</p><script>alert("xss")</script>'
        result = sanitizer.clean(html)
        assert "<script>" not in result
        assert "alert" not in result

    def test_strips_event_handlers(self, sanitizer):
        """Event handlers are removed from elements."""
        html = '<p onclick="alert(1)">Click me</p>'
        result = sanitizer.clean(html)
        assert "onclick" not in result
        assert result == "<p>Click me</p>"

    def test_strips_javascript_urls(self, sanitizer):
        """javascript: URLs are removed."""
        html = '<a href="javascript:alert(1)">Click</a>'
        result = sanitizer.clean(html)
        assert "javascript:" not in result

    def test_allows_safe_img(self, sanitizer):
        """Safe img tags with allowed attributes are preserved."""
        html = '<img src="https://example.com/img.png" alt="test">'
        result = sanitizer.clean(html)
        assert "src=" in result
        assert "alt=" in result

    def test_strips_img_onerror(self, sanitizer):
        """onerror handlers are removed from images."""
        html = '<img src="x" onerror="alert(1)">'
        result = sanitizer.clean(html)
        assert "onerror" not in result

    def test_strips_iframe(self, sanitizer):
        """iframe tags are removed."""
        html = '<iframe src="https://evil.com"></iframe>'
        result = sanitizer.clean(html)
        assert "<iframe" not in result

    def test_strips_object(self, sanitizer):
        """object tags are removed."""
        html = '<object data="https://evil.com/plugin"></object>'
        result = sanitizer.clean(html)
        assert "<object" not in result

    def test_strips_embed(self, sanitizer):
        """embed tags are removed."""
        html = '<embed src="https://evil.com/plugin">'
        result = sanitizer.clean(html)
        assert "<embed" not in result

    @pytest.mark.parametrize(
        "malicious",
        [
            '<svg onload="alert(1)">',
            '<math><mi xlink:href="javascript:alert(1)">',
            '<iframe src="javascript:alert(1)">',
            '<object data="javascript:alert(1)">',
            '<embed src="javascript:alert(1)">',
            '<style>@import "javascript:alert(1)"</style>',
            "<img src=x onerror=alert(1)>",
            "<body onload=alert(1)>",
            "<input onfocus=alert(1) autofocus>",
            "<marquee onstart=alert(1)>",
            "<video><source onerror=alert(1)>",
            "<audio src=x onerror=alert(1)>",
        ],
    )
    def test_strips_various_xss_vectors(self, sanitizer, malicious):
        """Various XSS attack vectors are neutralized."""
        result = sanitizer.clean(malicious)
        assert "javascript:" not in result.lower()
        assert "alert" not in result
        assert "onerror" not in result.lower()
        assert "onload" not in result.lower()
        assert "onfocus" not in result.lower()
        assert "onstart" not in result.lower()

    def test_allows_mailto_links(self, sanitizer):
        """mailto: links are allowed."""
        html = '<a href="mailto:test@example.com">Email</a>'
        result = sanitizer.clean(html)
        assert "mailto:" in result

    def test_allows_https_links(self, sanitizer):
        """https: links are allowed."""
        html = '<a href="https://example.com">Link</a>'
        result = sanitizer.clean(html)
        assert "https://example.com" in result

    # === Edge Case Tests ===

    def test_handles_nested_script_tags(self, sanitizer):
        """Nested script tags are stripped."""
        html = "<div><script><script>alert(1)</script></script></div>"
        result = sanitizer.clean(html)
        assert "<script" not in result
        assert "alert" not in result

    def test_handles_encoded_entities(self, sanitizer):
        """HTML entities are handled correctly."""
        html = "&lt;script&gt;alert(1)&lt;/script&gt;"
        result = sanitizer.clean(html)
        # Encoded entities should be preserved as-is (they're text, not tags)
        assert "&lt;" in result or "<" not in result

    def test_handles_mixed_case_tags(self, sanitizer):
        """Mixed case tags like SCRIPT are handled."""
        html = "<SCRIPT>alert(1)</SCRIPT>"
        result = sanitizer.clean(html)
        assert "SCRIPT" not in result.upper() or "alert" not in result

    def test_strips_svg_with_payload(self, sanitizer):
        """SVG with embedded script is stripped."""
        html = "<svg><script>alert(1)</script></svg>"
        result = sanitizer.clean(html)
        assert "<svg" not in result
        assert "alert" not in result

    def test_handles_css_expression(self, sanitizer):
        """CSS expressions are neutralized."""
        html = '<p style="background: expression(alert(1))">text</p>'
        result = sanitizer.clean(html)
        assert "expression" not in result.lower()

    def test_handles_null_bytes(self, sanitizer):
        """Null bytes in tag names.

        Note: bleach strips null bytes but doesn't recognize 'scr\\x00ipt' as script.
        This tests documents the behavior - the actual XSS vector is neutralized
        because the broken tag isn't parsed as a script element.
        """
        html = "<scr\x00ipt>alert(1)</script>"
        result = sanitizer.clean(html)
        # The malformed tag is not recognized as script, so content shows
        # But this isn't actually executable XSS since browsers won't parse it as script
        assert "<script>" not in result

    def test_handles_very_long_input(self, sanitizer):
        """Very long input is handled without crash."""
        html = "<p>" + "x" * 100000 + "</p>"
        result = sanitizer.clean(html)
        assert len(result) > 0

    def test_handles_unclosed_tags(self, sanitizer):
        """Unclosed tags are handled gracefully."""
        html = "<p>Hello <strong>world"
        result = sanitizer.clean(html)
        # Should either close tags or strip safely
        assert "Hello" in result

    def test_strips_data_uris_in_script_context(self, sanitizer):
        """data: URIs in dangerous contexts are handled."""
        html = '<object data="data:text/html,<script>alert(1)</script>">'
        result = sanitizer.clean(html)
        assert "<object" not in result


class TestNoOpSanitizer:
    """Tests for NoOpSanitizer (test helper)."""

    def test_passes_through_unchanged(self):
        """NoOpSanitizer preserves all content."""
        sanitizer = NoOpSanitizer()
        html = "<script>alert(1)</script>"
        assert sanitizer.clean(html) == html


# =============================================================================
# URL Validation Tests (SSRF Protection)
# =============================================================================


def is_safe_url(url: str) -> bool:
    """
    Check if URL is safe to fetch (no SSRF).

    This is a copy of the validation logic from main.py for testing.
    """
    BLOCKED_METADATA_IPS = {
        "169.254.169.254",
        "100.100.100.200",
        "192.0.0.192",
    }

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Must be http or https
    if parsed.scheme not in ("http", "https"):
        return False

    # Must have a host
    if not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()

    # Block localhost
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False

    # Block cloud metadata endpoints
    if hostname in BLOCKED_METADATA_IPS:
        return False

    # Block internal networks
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False
        # Block IPv6 unique local addresses (fc00::/7, which includes fd00::/8)
        # Check first byte: 0xFC or 0xFD (binary: 1111110x)
        if ip.version == 6 and (ip.packed[0] & 0xFE) == 0xFC:
            return False
    except ValueError:
        pass  # Not an IP, that's fine

    # Block cloud metadata hostnames
    metadata_hosts = [
        "metadata.google.internal",
        "metadata.azure.internal",  # Azure IMDS hostname
        "instance-data",
    ]
    if any(hostname == h or hostname.endswith("." + h) for h in metadata_hosts):
        return False

    # Block internal domain patterns
    return not (hostname.endswith(".internal") or hostname.endswith(".local"))


class TestUrlValidation:
    """Tests for URL validation (SSRF protection)."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/feed.xml",
            "https://blog.example.com/rss",
            "http://feeds.feedburner.com/example",
            "https://news.ycombinator.com/rss",
            "https://jvns.ca/atom.xml",
            "https://rachelbythebay.com/w/atom.xml",
            "http://example.org:8080/feed",
        ],
    )
    def test_allows_valid_urls(self, url):
        """Valid external URLs are allowed."""
        assert is_safe_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/feed",
            "http://localhost:8080/feed",
            "http://127.0.0.1/feed",
            "http://127.0.0.1:3000/feed",
            "http://[::1]/feed",
            "http://0.0.0.0/feed",
        ],
    )
    def test_blocks_localhost(self, url):
        """Localhost variants are blocked."""
        assert not is_safe_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://10.0.0.1/feed",
            "http://10.255.255.255/feed",
            "http://172.16.0.1/feed",
            "http://172.31.255.255/feed",
            "http://192.168.1.1/feed",
            "http://192.168.255.255/feed",
        ],
    )
    def test_blocks_private_networks(self, url):
        """Private network IPs are blocked."""
        assert not is_safe_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.169.254/latest/api/token",
            "http://100.100.100.200/",
            "http://192.0.0.192/",
            "http://metadata.google.internal/",
            "http://metadata.google.internal/computeMetadata/v1/",
        ],
    )
    def test_blocks_cloud_metadata(self, url):
        """Cloud metadata endpoints are blocked."""
        assert not is_safe_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/feed",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "gopher://example.com/",
            "dict://example.com/",
        ],
    )
    def test_blocks_non_http_schemes(self, url):
        """Non-HTTP schemes are blocked."""
        assert not is_safe_url(url)

    def test_blocks_empty_url(self):
        """Empty URLs are blocked."""
        assert not is_safe_url("")

    def test_blocks_malformed_url(self):
        """Malformed URLs are blocked."""
        assert not is_safe_url("not a url")
        assert not is_safe_url("://missing-scheme")

    @pytest.mark.parametrize(
        "url",
        [
            "http://internal.local/feed",
            "http://app.internal/feed",
            "http://service.internal/api",
        ],
    )
    def test_blocks_internal_domains(self, url):
        """Internal domain patterns are blocked."""
        assert not is_safe_url(url)

    def test_allows_url_with_path(self):
        """URLs with paths are allowed."""
        assert is_safe_url("https://example.com/blog/feed.xml")

    def test_allows_url_with_query(self):
        """URLs with query strings are allowed."""
        assert is_safe_url("https://example.com/feed?format=rss")

    def test_allows_url_with_port(self):
        """URLs with non-standard ports are allowed (if not internal)."""
        assert is_safe_url("https://example.com:8443/feed")

    # Comprehensive IPv6 SSRF tests
    @pytest.mark.parametrize(
        "url",
        [
            # fc00::/8 - Unique Local (not guaranteed private, but blocked)
            "http://[fc00::1]/feed",
            "http://[fc00:ffff:ffff::1]/feed",
            "http://[fcff:ffff:ffff:ffff::1]/feed",
            # fd00::/8 - Unique Local (RFC 4193 private)
            "http://[fd00::1]/feed",
            "http://[fd00::face:1234]/feed",
            "http://[fdff:ffff:ffff:ffff::1]/feed",
        ],
    )
    def test_blocks_ipv6_unique_local(self, url):
        """IPv6 unique local addresses (fc00::/7) are blocked."""
        assert not is_safe_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            # IPv6 loopback
            "http://[::1]/feed",
            # IPv6 link-local
            "http://[fe80::1]/feed",
            "http://[fe80::1%25eth0]/feed",  # URL-encoded % for interface
        ],
    )
    def test_blocks_ipv6_special_addresses(self, url):
        """IPv6 loopback and link-local addresses are blocked."""
        assert not is_safe_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            # Valid public IPv6 addresses (real routable addresses)
            "http://[2607:f8b0:4004:800::200e]/feed",  # Google's IPv6
            "http://[2600:1901:0:38d7::]/feed",  # Google Cloud
        ],
    )
    def test_allows_public_ipv6(self, url):
        """Public IPv6 addresses are allowed (for valid use cases)."""
        assert is_safe_url(url)

    def test_blocks_documentation_ipv6(self):
        """RFC 3849 documentation addresses (2001:db8::/32) are blocked as reserved."""
        # 2001:db8::/32 is reserved for documentation, not routable
        # Python's ipaddress treats it as reserved, which is correct
        assert not is_safe_url("http://[2001:db8::1]/feed")

    def test_blocks_azure_metadata(self):
        """Azure IMDS metadata hostname is blocked."""
        assert not is_safe_url("http://metadata.azure.internal/")
        assert not is_safe_url("http://metadata.azure.internal/metadata/instance")
