"""
Unit tests for RSS/Atom feed title extraction.

These tests verify that feedparser correctly extracts titles from various
feed formats and edge cases.
"""

import feedparser


class TestRSSFeedTitleExtraction:
    """Test title extraction from RSS 2.0 feeds."""

    def test_rss20_with_title(self):
        """RSS 2.0 feed with a standard title element."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>My Awesome Blog</title>
                <link>https://example.com</link>
                <description>A blog about things</description>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        assert title == "My Awesome Blog"

    def test_rss20_with_empty_title(self):
        """RSS 2.0 feed with an empty title element."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title></title>
                <link>https://example.com</link>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        # Empty string is still a value
        assert title == ""

    def test_rss20_without_title(self):
        """RSS 2.0 feed without a title element."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <link>https://example.com</link>
                <description>A blog without a title</description>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        # Returns None when missing
        assert title is None

    def test_rss20_with_cdata_title(self):
        """RSS 2.0 feed with CDATA-wrapped title."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title><![CDATA[My <Special> Blog]]></title>
                <link>https://example.com</link>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        # CDATA should be unwrapped, entities preserved
        assert "My" in title and "Blog" in title

    def test_rss20_with_html_entities_in_title(self):
        """RSS 2.0 feed with HTML entities in title."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>Tom &amp; Jerry's Blog</title>
                <link>https://example.com</link>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        # feedparser decodes HTML entities
        assert title == "Tom & Jerry's Blog"


class TestAtomFeedTitleExtraction:
    """Test title extraction from Atom feeds."""

    def test_atom10_with_title(self):
        """Atom 1.0 feed with a standard title element."""
        atom_content = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>My Atom Blog</title>
            <link href="https://example.com"/>
            <id>urn:uuid:60a76c80-d399-11d9-b93C-0003939e0af6</id>
        </feed>"""

        feed_data = feedparser.parse(atom_content)
        title = feed_data.feed.get("title")

        assert title == "My Atom Blog"

    def test_atom10_with_type_text(self):
        """Atom 1.0 feed with type='text' title."""
        atom_content = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title type="text">Plain Text Title</title>
            <link href="https://example.com"/>
            <id>urn:uuid:60a76c80-d399-11d9-b93C-0003939e0af6</id>
        </feed>"""

        feed_data = feedparser.parse(atom_content)
        title = feed_data.feed.get("title")

        assert title == "Plain Text Title"

    def test_atom10_with_type_html(self):
        """Atom 1.0 feed with type='html' title."""
        atom_content = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title type="html">&lt;b&gt;Bold Title&lt;/b&gt;</title>
            <link href="https://example.com"/>
            <id>urn:uuid:60a76c80-d399-11d9-b93C-0003939e0af6</id>
        </feed>"""

        feed_data = feedparser.parse(atom_content)
        title = feed_data.feed.get("title")

        # feedparser returns the decoded HTML
        assert "<b>Bold Title</b>" in title or "Bold Title" in title

    def test_atom10_without_title(self):
        """Atom 1.0 feed without a title element."""
        atom_content = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <link href="https://example.com"/>
            <id>urn:uuid:60a76c80-d399-11d9-b93C-0003939e0af6</id>
        </feed>"""

        feed_data = feedparser.parse(atom_content)
        title = feed_data.feed.get("title")

        assert title is None


class TestEdgeCases:
    """Test edge cases in feed title extraction."""

    def test_unicode_title(self):
        """Feed with unicode characters in title."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>日本語のブログ</title>
                <link>https://example.jp</link>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        assert title == "日本語のブログ"

    def test_emoji_title(self):
        """Feed with emoji in title."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>🚀 Rocket Blog 🔥</title>
                <link>https://example.com</link>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        assert "🚀" in title and "🔥" in title

    def test_very_long_title(self):
        """Feed with a very long title."""
        long_title = "A" * 1000
        rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>{long_title}</title>
                <link>https://example.com</link>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        assert len(title) == 1000

    def test_whitespace_only_title(self):
        """Feed with whitespace-only title."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>   </title>
                <link>https://example.com</link>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        # feedparser may strip or preserve whitespace
        assert title is not None

    def test_malformed_xml_still_extracts_title(self):
        """Feed with some XML errors but parseable title."""
        # feedparser is lenient and tries to extract what it can
        rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Lenient Parser Blog</title>
                <!-- missing closing tags -->"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")

        # feedparser's leniency may still extract the title
        # The exact behavior depends on feedparser version
        assert title == "Lenient Parser Blog" or title is None


class TestSiteURLExtraction:
    """Test site URL extraction alongside title."""

    def test_rss20_link_extraction(self):
        """Extract site URL from RSS 2.0 link element."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>My Blog</title>
                <link>https://example.com/blog</link>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)
        title = feed_data.feed.get("title")
        site_url = feed_data.feed.get("link")

        assert title == "My Blog"
        assert site_url == "https://example.com/blog"

    def test_atom10_link_extraction(self):
        """Extract site URL from Atom 1.0 link element."""
        atom_content = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>My Atom Blog</title>
            <link href="https://example.com/atom" rel="alternate"/>
            <id>urn:uuid:60a76c80-d399-11d9-b93C-0003939e0af6</id>
        </feed>"""

        feed_data = feedparser.parse(atom_content)
        title = feed_data.feed.get("title")
        site_url = feed_data.feed.get("link")

        assert title == "My Atom Blog"
        assert site_url == "https://example.com/atom"


class TestAuthorExtraction:
    """Test author extraction from feeds (Issue 1.1)."""

    def test_rss20_author_extraction(self):
        """Extract author from RSS 2.0 managingEditor or author element."""
        rss_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>My Blog</title>
                <link>https://example.com</link>
                <managingEditor>author@example.com (John Doe)</managingEditor>
            </channel>
        </rss>"""

        feed_data = feedparser.parse(rss_content)

        # feedparser normalizes author info
        author = feed_data.feed.get("author")
        assert author is not None or feed_data.feed.get("managingEditor") is not None

    def test_atom10_author_extraction(self):
        """Extract author from Atom 1.0 author element."""
        atom_content = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title>My Atom Blog</title>
            <link href="https://example.com"/>
            <id>urn:uuid:60a76c80-d399-11d9-b93C-0003939e0af6</id>
            <author>
                <name>Jane Doe</name>
                <email>jane@example.com</email>
            </author>
        </feed>"""

        feed_data = feedparser.parse(atom_content)

        # Check author_detail if available
        if hasattr(feed_data.feed, "author_detail"):
            assert feed_data.feed.author_detail.get("name") == "Jane Doe"
            assert feed_data.feed.author_detail.get("email") == "jane@example.com"
        else:
            # Fallback to author string
            author = feed_data.feed.get("author")
            assert author is not None
