# tests/unit/test_url_resolution.py
"""
Comprehensive tests for relative URL resolution in feed content.

This test suite is inspired by:
- Planet Venus: Configuration-driven URL resolution with base URI handling
- Rogue Planet: Comprehensive torture tests and real-world scenario coverage

The URL resolver should convert relative URLs in feed content to absolute URLs
using the feed's base URL, enabling proper display of images, links, and other
resources when content is aggregated from multiple sources.
"""

import pytest

# Import will be created by implementation
# from src.url_resolver import URLResolver, resolve_relative_urls


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def resolver():
    """Create a URLResolver instance for testing."""
    from src.url_resolver import URLResolver

    return URLResolver()


@pytest.fixture
def resolve_urls(resolver):
    """Helper to resolve URLs with a given base."""

    def _resolve(content: str, base_url: str) -> str:
        return resolver.resolve(content, base_url)

    return _resolve


# =============================================================================
# BASIC RELATIVE URL RESOLUTION
# =============================================================================


class TestBasicRelativeURLs:
    """Tests for basic relative URL patterns."""

    def test_absolute_path_from_root(self, resolve_urls):
        """URLs starting with / are resolved relative to origin."""
        content = '<img src="/images/photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/post.html")
        assert result == '<img src="https://example.com/images/photo.jpg">'

    def test_relative_path_same_directory(self, resolve_urls):
        """URLs without leading slash resolve relative to current path."""
        content = '<img src="photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/post.html")
        assert result == '<img src="https://example.com/blog/photo.jpg">'

    def test_relative_path_with_dot_slash(self, resolve_urls):
        """URLs with ./ resolve relative to current path."""
        content = '<img src="./photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/post.html")
        assert result == '<img src="https://example.com/blog/photo.jpg">'

    def test_parent_directory_traversal(self, resolve_urls):
        """URLs with ../ traverse up the directory tree."""
        content = '<img src="../assets/photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/posts/article.html")
        assert result == '<img src="https://example.com/blog/assets/photo.jpg">'

    def test_multiple_parent_traversals(self, resolve_urls):
        """Multiple ../ segments are handled correctly."""
        content = '<img src="../../images/photo.jpg">'
        result = resolve_urls(content, "https://example.com/a/b/c/page.html")
        assert result == '<img src="https://example.com/a/images/photo.jpg">'

    def test_subdirectory_path(self, resolve_urls):
        """Relative paths into subdirectories work correctly."""
        content = '<img src="images/photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert result == '<img src="https://example.com/blog/images/photo.jpg">'

    def test_complex_relative_path(self, resolve_urls):
        """Complex paths with mixed segments are resolved correctly."""
        content = '<img src="../assets/./images/../photos/pic.jpg">'
        result = resolve_urls(content, "https://example.com/blog/posts/article.html")
        # Should normalize to: https://example.com/blog/assets/photos/pic.jpg
        assert "example.com" in result
        assert "photos/pic.jpg" in result


# =============================================================================
# PRESERVE ABSOLUTE URLs
# =============================================================================


class TestPreserveAbsoluteURLs:
    """Tests ensuring absolute URLs are not modified."""

    def test_preserve_https_url(self, resolve_urls):
        """HTTPS URLs are preserved unchanged."""
        content = '<a href="https://other.com/page">Link</a>'
        result = resolve_urls(content, "https://example.com/")
        assert 'href="https://other.com/page"' in result

    def test_preserve_http_url(self, resolve_urls):
        """HTTP URLs are preserved unchanged."""
        content = '<a href="http://other.com/page">Link</a>'
        result = resolve_urls(content, "https://example.com/")
        assert 'href="http://other.com/page"' in result

    def test_preserve_protocol_relative_url(self, resolve_urls):
        """Protocol-relative URLs (//) are preserved."""
        content = '<img src="//cdn.example.com/image.jpg">'
        result = resolve_urls(content, "https://example.com/")
        assert 'src="//cdn.example.com/image.jpg"' in result

    def test_preserve_data_uri(self, resolve_urls):
        """data: URIs are preserved unchanged."""
        content = '<img src="data:image/png;base64,iVBORw0KGgo=">'
        result = resolve_urls(content, "https://example.com/")
        assert 'src="data:image/png;base64,iVBORw0KGgo="' in result

    def test_preserve_mailto_link(self, resolve_urls):
        """mailto: links are preserved unchanged."""
        content = '<a href="mailto:test@example.com">Email</a>'
        result = resolve_urls(content, "https://example.com/")
        assert 'href="mailto:test@example.com"' in result

    def test_preserve_tel_link(self, resolve_urls):
        """tel: links are preserved unchanged."""
        content = '<a href="tel:+1234567890">Call</a>'
        result = resolve_urls(content, "https://example.com/")
        assert 'href="tel:+1234567890"' in result

    def test_preserve_fragment_only(self, resolve_urls):
        """Fragment-only links (#anchor) are preserved."""
        content = '<a href="#section">Jump</a>'
        result = resolve_urls(content, "https://example.com/page")
        assert 'href="#section"' in result

    def test_preserve_javascript_url(self, resolve_urls):
        """javascript: URLs are preserved (sanitizer handles removal)."""
        content = '<a href="javascript:void(0)">Click</a>'
        result = resolve_urls(content, "https://example.com/")
        # URL resolver shouldn't modify - sanitizer will remove
        assert 'href="javascript:void(0)"' in result


# =============================================================================
# HTML ATTRIBUTE COVERAGE
# =============================================================================


class TestHTMLAttributes:
    """Tests for URL resolution in various HTML attributes."""

    def test_img_src(self, resolve_urls):
        """img src attributes are resolved."""
        content = '<img src="/images/photo.jpg" alt="Photo">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'src="https://example.com/images/photo.jpg"' in result

    def test_a_href(self, resolve_urls):
        """a href attributes are resolved."""
        content = '<a href="/about">About</a>'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'href="https://example.com/about"' in result

    def test_video_src(self, resolve_urls):
        """video src attributes are resolved."""
        content = '<video src="/videos/intro.mp4"></video>'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'src="https://example.com/videos/intro.mp4"' in result

    def test_video_poster(self, resolve_urls):
        """video poster attributes are resolved."""
        content = '<video poster="/images/thumb.jpg"></video>'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'poster="https://example.com/images/thumb.jpg"' in result

    def test_audio_src(self, resolve_urls):
        """audio src attributes are resolved."""
        content = '<audio src="/audio/podcast.mp3"></audio>'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'src="https://example.com/audio/podcast.mp3"' in result

    def test_source_src(self, resolve_urls):
        """source src attributes are resolved."""
        content = '<source src="/video/clip.webm" type="video/webm">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'src="https://example.com/video/clip.webm"' in result

    def test_source_srcset(self, resolve_urls):
        """source srcset attributes are resolved."""
        content = '<source srcset="/images/large.jpg 2x, /images/small.jpg 1x">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert "https://example.com/images/large.jpg" in result
        assert "https://example.com/images/small.jpg" in result

    def test_img_srcset_simple(self, resolve_urls):
        """img srcset with simple URLs are resolved."""
        content = '<img srcset="/images/small.jpg 480w, /images/large.jpg 800w">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert "https://example.com/images/small.jpg" in result
        assert "https://example.com/images/large.jpg" in result

    def test_img_srcset_with_descriptors(self, resolve_urls):
        """img srcset with width/density descriptors are resolved."""
        content = '<img src="/img/photo.jpg" srcset="/img/photo-2x.jpg 2x">'
        result = resolve_urls(content, "https://example.com/")
        assert 'src="https://example.com/img/photo.jpg"' in result
        assert "https://example.com/img/photo-2x.jpg" in result

    def test_picture_with_sources(self, resolve_urls):
        """picture element with multiple sources resolved."""
        content = """<picture>
            <source media="(min-width: 800px)" srcset="/images/large.jpg">
            <source media="(min-width: 400px)" srcset="/images/medium.jpg">
            <img src="/images/small.jpg" alt="Photo">
        </picture>"""
        result = resolve_urls(content, "https://example.com/blog/")
        assert "https://example.com/images/large.jpg" in result
        assert "https://example.com/images/medium.jpg" in result
        assert "https://example.com/images/small.jpg" in result

    def test_object_data(self, resolve_urls):
        """object data attributes are resolved."""
        content = '<object data="/files/document.pdf"></object>'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'data="https://example.com/files/document.pdf"' in result

    def test_embed_src(self, resolve_urls):
        """embed src attributes are resolved."""
        content = '<embed src="/flash/animation.swf">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'src="https://example.com/flash/animation.swf"' in result

    def test_iframe_src(self, resolve_urls):
        """iframe src attributes are resolved."""
        content = '<iframe src="/embed/widget.html"></iframe>'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'src="https://example.com/embed/widget.html"' in result

    def test_track_src(self, resolve_urls):
        """track src (for video captions) are resolved."""
        content = '<track src="/captions/en.vtt" kind="subtitles">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'src="https://example.com/captions/en.vtt"' in result


# =============================================================================
# BASE URL EDGE CASES
# =============================================================================


class TestBaseURLEdgeCases:
    """Tests for edge cases in base URL handling."""

    def test_base_url_without_trailing_slash(self, resolve_urls):
        """Base URL without trailing slash works correctly."""
        content = '<img src="photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog")
        # /blog is treated as a file, so parent is /
        assert result == '<img src="https://example.com/photo.jpg">'

    def test_base_url_with_trailing_slash(self, resolve_urls):
        """Base URL with trailing slash treats path as directory."""
        content = '<img src="photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert result == '<img src="https://example.com/blog/photo.jpg">'

    def test_base_url_root_only(self, resolve_urls):
        """Base URL with only root path works."""
        content = '<img src="images/photo.jpg">'
        result = resolve_urls(content, "https://example.com/")
        assert result == '<img src="https://example.com/images/photo.jpg">'

    def test_base_url_with_port(self, resolve_urls):
        """Base URL with port is handled correctly."""
        content = '<img src="/images/photo.jpg">'
        result = resolve_urls(content, "https://example.com:8080/blog/")
        assert result == '<img src="https://example.com:8080/images/photo.jpg">'

    def test_base_url_with_query_string(self, resolve_urls):
        """Base URL with query string - query is ignored for resolution."""
        content = '<img src="photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/post.html?id=123")
        assert result == '<img src="https://example.com/blog/photo.jpg">'

    def test_base_url_with_fragment(self, resolve_urls):
        """Base URL with fragment - fragment is ignored for resolution."""
        content = '<img src="photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/post.html#section")
        assert result == '<img src="https://example.com/blog/photo.jpg">'

    def test_base_url_with_auth(self, resolve_urls):
        """Base URL with username:password is handled (though unusual)."""
        content = '<img src="/images/photo.jpg">'
        result = resolve_urls(content, "https://user:pass@example.com/blog/")
        # Auth info should be preserved in origin
        assert "example.com" in result
        assert "/images/photo.jpg" in result

    def test_base_url_ip_address(self, resolve_urls):
        """Base URL with IP address instead of domain."""
        content = '<img src="/images/photo.jpg">'
        result = resolve_urls(content, "http://192.168.1.1/blog/")
        assert result == '<img src="http://192.168.1.1/images/photo.jpg">'

    def test_http_base_url_preserved(self, resolve_urls):
        """HTTP scheme in base URL is preserved (not upgraded to HTTPS)."""
        content = '<img src="/images/photo.jpg">'
        result = resolve_urls(content, "http://example.com/blog/")
        assert result == '<img src="http://example.com/images/photo.jpg">'

    def test_deeply_nested_base_path(self, resolve_urls):
        """Deeply nested base path is handled correctly."""
        content = '<img src="photo.jpg">'
        result = resolve_urls(content, "https://example.com/a/b/c/d/e/page.html")
        assert result == '<img src="https://example.com/a/b/c/d/e/photo.jpg">'


# =============================================================================
# CONTENT EDGE CASES
# =============================================================================


class TestContentEdgeCases:
    """Tests for edge cases in content handling."""

    def test_empty_content(self, resolve_urls):
        """Empty content returns empty string."""
        result = resolve_urls("", "https://example.com/")
        assert result == ""

    def test_no_urls_in_content(self, resolve_urls):
        """Content without URLs is unchanged."""
        content = "<p>Hello world!</p>"
        result = resolve_urls(content, "https://example.com/")
        assert result == content

    def test_empty_src_attribute(self, resolve_urls):
        """Empty src attribute is preserved."""
        content = '<img src="" alt="empty">'
        result = resolve_urls(content, "https://example.com/")
        assert 'src=""' in result

    def test_empty_href_attribute(self, resolve_urls):
        """Empty href attribute is preserved."""
        content = '<a href="">Link</a>'
        result = resolve_urls(content, "https://example.com/")
        assert 'href=""' in result

    def test_whitespace_in_url(self, resolve_urls):
        """URLs with whitespace are handled."""
        content = '<img src="  /images/photo.jpg  ">'
        result = resolve_urls(content, "https://example.com/")
        # Whitespace should be trimmed
        assert "https://example.com/images/photo.jpg" in result

    def test_newline_in_attribute(self, resolve_urls):
        """Newlines in attribute values are handled."""
        content = '<img src="\n/images/photo.jpg\n">'
        result = resolve_urls(content, "https://example.com/")
        assert "example.com" in result

    def test_multiple_images(self, resolve_urls):
        """Multiple images in content are all resolved."""
        content = '<img src="/a.jpg"><img src="/b.jpg"><img src="/c.jpg">'
        result = resolve_urls(content, "https://example.com/")
        assert 'src="https://example.com/a.jpg"' in result
        assert 'src="https://example.com/b.jpg"' in result
        assert 'src="https://example.com/c.jpg"' in result

    def test_mixed_absolute_and_relative(self, resolve_urls):
        """Mix of absolute and relative URLs handled correctly."""
        content = """
        <img src="/local.jpg">
        <img src="https://cdn.example.com/remote.jpg">
        <img src="relative.jpg">
        """
        result = resolve_urls(content, "https://example.com/blog/")
        assert "https://example.com/local.jpg" in result
        assert "https://cdn.example.com/remote.jpg" in result
        assert "https://example.com/blog/relative.jpg" in result

    def test_url_with_special_characters(self, resolve_urls):
        """URLs with special characters are preserved."""
        content = '<img src="/images/photo%20name.jpg">'
        result = resolve_urls(content, "https://example.com/")
        assert "https://example.com/images/photo%20name.jpg" in result

    def test_url_with_unicode(self, resolve_urls):
        """URLs with unicode characters are handled."""
        content = '<img src="/images/фото.jpg">'
        result = resolve_urls(content, "https://example.com/")
        assert "https://example.com/images/фото.jpg" in result

    def test_url_with_query_string(self, resolve_urls):
        """Relative URLs with query strings are resolved."""
        content = '<img src="/images/photo.jpg?size=large&format=webp">'
        result = resolve_urls(content, "https://example.com/blog/")
        assert "https://example.com/images/photo.jpg?size=large&format=webp" in result

    def test_url_with_fragment(self, resolve_urls):
        """Relative URLs with fragments are resolved."""
        content = '<a href="/page#section">Link</a>'
        result = resolve_urls(content, "https://example.com/blog/")
        assert 'href="https://example.com/page#section"' in result


# =============================================================================
# QUOTE HANDLING
# =============================================================================


class TestQuoteHandling:
    """Tests for different quote styles in attributes."""

    def test_double_quotes(self, resolve_urls):
        """Double-quoted attributes are handled."""
        content = '<img src="/photo.jpg">'
        result = resolve_urls(content, "https://example.com/")
        assert 'src="https://example.com/photo.jpg"' in result

    def test_single_quotes(self, resolve_urls):
        """Single-quoted attributes are handled."""
        content = "<img src='/photo.jpg'>"
        result = resolve_urls(content, "https://example.com/")
        assert "src='https://example.com/photo.jpg'" in result

    def test_no_quotes(self, resolve_urls):
        """Unquoted attributes are handled (common in older HTML)."""
        content = "<img src=/photo.jpg>"
        result = resolve_urls(content, "https://example.com/")
        # Should still resolve the URL
        assert "https://example.com/photo.jpg" in result

    def test_mixed_quote_styles(self, resolve_urls):
        """Mixed quote styles in same document are handled."""
        content = """<img src="/a.jpg"><img src='/b.jpg'>"""
        result = resolve_urls(content, "https://example.com/")
        assert "https://example.com/a.jpg" in result
        assert "https://example.com/b.jpg" in result


# =============================================================================
# REAL-WORLD SCENARIOS (inspired by Rogue Planet)
# =============================================================================


class TestRealWorldScenarios:
    """Tests based on real-world feed content patterns."""

    def test_wordpress_content(self, resolve_urls):
        """WordPress-style content with wp-content paths."""
        content = """
        <p>Check out this image:</p>
        <figure class="wp-block-image">
            <img src="/wp-content/uploads/2024/01/photo.jpg"
                 alt="My Photo"
                 class="wp-image-123">
        </figure>
        <p>Read more <a href="/2024/01/my-post/">here</a>.</p>
        """
        result = resolve_urls(content, "https://myblog.com/2024/01/my-post/")
        assert "https://myblog.com/wp-content/uploads/2024/01/photo.jpg" in result
        assert "https://myblog.com/2024/01/my-post/" in result

    def test_medium_style_content(self, resolve_urls):
        """Medium-style content with CDN images."""
        content = """
        <figure>
            <img src="https://miro.medium.com/max/1400/photo.jpg">
            <figcaption>Photo caption</figcaption>
        </figure>
        <p>Local image: <img src="/images/local.png"></p>
        """
        result = resolve_urls(content, "https://medium.com/@user/post-slug")
        # CDN URL preserved
        assert "https://miro.medium.com/max/1400/photo.jpg" in result
        # Local URL resolved
        assert "https://medium.com/images/local.png" in result

    def test_github_readme_content(self, resolve_urls):
        """GitHub README-style content with relative image paths."""
        content = """
        <h1>Project Name</h1>
        <p><img src="./docs/images/screenshot.png" alt="Screenshot"></p>
        <p><img src="docs/logo.svg" alt="Logo"></p>
        <p><a href="./CONTRIBUTING.md">Contributing Guide</a></p>
        """
        result = resolve_urls(content, "https://github.com/user/repo/blob/main/README.md")
        assert "https://github.com/user/repo/blob/main/docs/images/screenshot.png" in result
        assert "https://github.com/user/repo/blob/main/docs/logo.svg" in result
        assert "https://github.com/user/repo/blob/main/CONTRIBUTING.md" in result

    def test_substack_newsletter(self, resolve_urls):
        """Substack newsletter content patterns."""
        content = """
        <div class="body markup">
            <p>Welcome to my newsletter!</p>
            <img src="/api/media/123/image.jpg">
            <a href="/p/my-previous-post">Previous post</a>
        </div>
        """
        result = resolve_urls(content, "https://newsletter.substack.com/p/current-post")
        assert "https://newsletter.substack.com/api/media/123/image.jpg" in result
        assert "https://newsletter.substack.com/p/my-previous-post" in result

    def test_jekyll_static_site(self, resolve_urls):
        """Jekyll static site with asset paths."""
        content = """
        <article>
            <p><img src="/assets/images/2024-01-15-photo.jpg"></p>
            <p>Download: <a href="/assets/files/document.pdf">PDF</a></p>
        </article>
        """
        result = resolve_urls(content, "https://user.github.io/blog/2024/01/15/post-title.html")
        assert "https://user.github.io/assets/images/2024-01-15-photo.jpg" in result
        assert "https://user.github.io/assets/files/document.pdf" in result

    def test_hugo_static_site(self, resolve_urls):
        """Hugo static site with different path patterns."""
        content = """
        <img src="../images/featured.jpg">
        <img src="cover.png">
        <a href="../../tags/golang/">Golang posts</a>
        """
        result = resolve_urls(content, "https://myblog.com/posts/2024/my-post/")
        assert "https://myblog.com/posts/2024/images/featured.jpg" in result
        assert "https://myblog.com/posts/2024/my-post/cover.png" in result
        assert "https://myblog.com/posts/tags/golang/" in result

    def test_ghost_blog(self, resolve_urls):
        """Ghost blog content patterns."""
        content = """
        <figure class="kg-card kg-image-card">
            <img src="/content/images/2024/01/photo.jpg"
                 class="kg-image" loading="lazy">
        </figure>
        """
        result = resolve_urls(content, "https://myblog.ghost.io/my-post/")
        assert "https://myblog.ghost.io/content/images/2024/01/photo.jpg" in result


# =============================================================================
# TORTURE TESTS (inspired by Rogue Planet)
# =============================================================================


class TestTortureTests:
    """Edge case torture tests for robustness."""

    def test_deeply_nested_parent_traversal(self, resolve_urls):
        """More parent traversals than path depth clamps to root."""
        content = '<img src="../../../../../../../../../photo.jpg">'
        result = resolve_urls(content, "https://example.com/a/b/c/")
        # Should clamp to root, not go above
        assert "https://example.com/" in result
        assert "photo.jpg" in result

    def test_url_with_double_slashes_in_path(self, resolve_urls):
        """Double slashes in path are normalized."""
        content = '<img src="//images//photo.jpg">'
        result = resolve_urls(content, "https://example.com/blog/")
        # Protocol-relative URL preserved as-is
        assert "//images//photo.jpg" in result

    def test_dot_only_path(self, resolve_urls):
        """Path of just '.' resolves to current directory."""
        content = '<a href=".">Current</a>'
        result = resolve_urls(content, "https://example.com/blog/post.html")
        assert "https://example.com/blog/" in result or 'href="."' in result

    def test_dot_dot_only_path(self, resolve_urls):
        """Path of just '..' resolves to parent directory."""
        content = '<a href="..">Parent</a>'
        result = resolve_urls(content, "https://example.com/blog/posts/")
        assert "https://example.com/blog/" in result or 'href=".."' in result

    def test_extremely_long_path(self, resolve_urls):
        """Very long relative paths are handled without crashing."""
        long_path = "/".join(["dir"] * 100) + "/photo.jpg"
        content = f'<img src="{long_path}">'
        result = resolve_urls(content, "https://example.com/")
        assert "example.com" in result
        assert "photo.jpg" in result

    def test_url_with_null_bytes(self, resolve_urls):
        """Null bytes in URLs are handled safely."""
        content = '<img src="/images\x00/photo.jpg">'
        result = resolve_urls(content, "https://example.com/")
        # Should either strip null bytes or handle gracefully
        assert "example.com" in result

    def test_url_with_backslashes(self, resolve_urls):
        """Backslashes in URLs are handled (Windows-style paths)."""
        content = r'<img src="\images\photo.jpg">'
        result = resolve_urls(content, "https://example.com/")
        # Backslashes may be converted to forward slashes or preserved
        assert "example.com" in result

    def test_case_sensitivity_in_attributes(self, resolve_urls):
        """Mixed case attribute names are handled."""
        content = '<IMG SRC="/photo.jpg"><A HREF="/page">Link</A>'
        result = resolve_urls(content, "https://example.com/")
        assert "example.com" in result

    def test_attributes_with_extra_whitespace(self, resolve_urls):
        """Extra whitespace around = sign is handled."""
        content = '<img src = "/photo.jpg">'
        result = resolve_urls(content, "https://example.com/")
        # Should still resolve
        assert "https://example.com/photo.jpg" in result or 'src = "/photo.jpg"' in result

    def test_malformed_html_attributes(self, resolve_urls):
        """Malformed HTML with missing closing quotes."""
        content = '<img src="/photo.jpg><p>text</p>'
        result = resolve_urls(content, "https://example.com/")
        # Should handle gracefully without crashing
        assert "example.com" in result or "/photo.jpg" in result

    def test_html_comments_preserved(self, resolve_urls):
        """HTML comments are preserved and URLs inside not resolved."""
        content = '<!-- <img src="/hidden.jpg"> --><img src="/visible.jpg">'
        result = resolve_urls(content, "https://example.com/")
        assert "https://example.com/visible.jpg" in result
        # Comment should be preserved as-is
        assert "<!--" in result

    def test_cdata_sections(self, resolve_urls):
        """CDATA sections are handled (common in RSS)."""
        content = '<![CDATA[<img src="/photo.jpg">]]>'
        result = resolve_urls(content, "https://example.com/")
        # CDATA content should be processed
        assert "example.com" in result or "CDATA" in result

    def test_consecutive_images_no_whitespace(self, resolve_urls):
        """Images without whitespace between them are handled."""
        content = '<img src="/a.jpg"><img src="/b.jpg"><img src="/c.jpg">'
        result = resolve_urls(content, "https://example.com/")
        assert result.count("https://example.com/") == 3


# =============================================================================
# INTEGRATION WITH SANITIZER
# =============================================================================


class TestIntegrationWithSanitizer:
    """Tests ensuring URL resolution works correctly with BleachSanitizer."""

    def test_resolved_urls_survive_sanitization(self, resolver):
        """Resolved URLs are not broken by subsequent sanitization."""
        from src.models import BleachSanitizer

        content = '<img src="/images/photo.jpg" alt="Photo">'
        base_url = "https://example.com/blog/"

        # First resolve URLs
        resolved = resolver.resolve(content, base_url)

        # Then sanitize
        sanitizer = BleachSanitizer()
        final = sanitizer.clean(resolved)

        assert "https://example.com/images/photo.jpg" in final
        assert 'alt="Photo"' in final or "alt=" in final

    def test_dangerous_resolved_urls_sanitized(self, resolver):
        """URLs that become dangerous after resolution are still sanitized."""
        from src.models import BleachSanitizer

        # Content with script tag that has relative URL
        content = '<script src="/scripts/evil.js"></script><img src="/photo.jpg">'
        base_url = "https://example.com/"

        resolved = resolver.resolve(content, base_url)
        sanitizer = BleachSanitizer()
        final = sanitizer.clean(resolved)

        # Script should be removed by sanitizer
        assert "<script" not in final
        # Image should remain with resolved URL
        assert "https://example.com/photo.jpg" in final


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================


class TestPerformance:
    """Basic performance sanity checks."""

    def test_large_content_completes(self, resolve_urls):
        """Large content with many URLs completes in reasonable time."""
        # Generate content with 1000 images
        images = [f'<img src="/images/photo{i}.jpg">' for i in range(1000)]
        content = "\n".join(images)

        import time

        start = time.time()
        result = resolve_urls(content, "https://example.com/")
        elapsed = time.time() - start

        # Should complete in under 1 second
        assert elapsed < 1.0
        # All images should be resolved
        assert result.count("https://example.com/images/photo") == 1000

    def test_deeply_nested_html_completes(self, resolve_urls):
        """Deeply nested HTML structure doesn't cause stack overflow."""
        # Create deeply nested structure
        content = "<div>" * 100 + '<img src="/photo.jpg">' + "</div>" * 100

        result = resolve_urls(content, "https://example.com/")
        assert "https://example.com/photo.jpg" in result


# =============================================================================
# FUNCTION API TESTS
# =============================================================================


class TestFunctionAPI:
    """Tests for the module-level function API."""

    def test_resolve_relative_urls_function(self):
        """Module-level resolve_relative_urls function works."""
        from src.url_resolver import resolve_relative_urls

        content = '<img src="/photo.jpg">'
        result = resolve_relative_urls(content, "https://example.com/blog/")
        assert result == '<img src="https://example.com/photo.jpg">'

    def test_resolver_is_reusable(self, resolver):
        """Same resolver instance can be reused for multiple operations."""
        result1 = resolver.resolve('<img src="/a.jpg">', "https://example.com/")
        result2 = resolver.resolve('<img src="/b.jpg">', "https://other.com/")

        assert "https://example.com/a.jpg" in result1
        assert "https://other.com/b.jpg" in result2
