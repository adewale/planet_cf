# tests/unit/test_video_content_stripping.py
"""Demonstrate that BleachSanitizer strips <video> and other media tags.

Reproduces the issue where a blog post with a <video> at the start
(e.g. https://zeke.sikelianos.com/ten-things-i-love-about-replicate/)
loses its video content when processed by Planet CF.

The root cause: BleachSanitizer.ALLOWED_TAGS does not include video,
source, audio, or iframe — so bleach strips them entirely (strip=True
removes the tags and keeps only inner text, but <video>/<source> have
no meaningful inner text).
"""

from models import BleachSanitizer

# Actual HTML structure from the Zeke blog post
BLOG_POST_HTML = """\
<video controls poster="/ten-things-i-love-about-replicate/thumbnail.jpg">
  <source src="https://assets.zeke.sikelianos.com/ten-things-i-love-about-replicate/ten-things-i-love-about-replicate.mp4" type="video/mp4">
</video>
<p>Replicate is a platform for running machine learning models in the cloud.</p>
<p>I've been working there for about three years now, and I want to share
some of the things I love about the product and the company, as well as
some areas where I think we can improve.</p>
"""

# Simulated content:encoded from an Atom/RSS feed that includes video
FEED_CONTENT_WITH_VIDEO = """\
<h2>My Review</h2>
<video controls poster="https://example.com/thumb.jpg">
  <source src="https://example.com/video.mp4" type="video/mp4">
  <source src="https://example.com/video.webm" type="video/webm">
  Your browser does not support the video tag.
</video>
<p>Here's what I think about this topic.</p>
<img src="https://example.com/photo.jpg" alt="A photo">
"""

# Content with audio tag
FEED_CONTENT_WITH_AUDIO = """\
<h2>Podcast Episode</h2>
<audio controls>
  <source src="https://example.com/episode.mp3" type="audio/mpeg">
</audio>
<p>Listen to this week's episode.</p>
"""

# Content with iframe embed (YouTube, etc.)
FEED_CONTENT_WITH_IFRAME = """\
<p>Watch this video:</p>
<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" width="560" height="315"
  frameborder="0" allowfullscreen></iframe>
<p>Pretty cool, right?</p>
"""


class TestVideoContentStripping:
    """Show that <video> tags are stripped by the sanitizer."""

    def test_video_tag_present_in_input_absent_in_output(self):
        """The actual Zeke blog post loses its video after sanitization."""
        sanitizer = BleachSanitizer()
        result = sanitizer.clean(BLOG_POST_HTML)

        # Input has video
        assert "<video" in BLOG_POST_HTML
        assert "<source" in BLOG_POST_HTML

        # Output loses video entirely
        assert "<video" not in result
        assert "<source" not in result

        # The poster image URL is also lost (it was an attribute on <video>)
        assert "thumbnail.jpg" not in result

        # The mp4 URL is also lost
        assert ".mp4" not in result

        # But paragraph text survives
        assert "Replicate is a platform" in result

    def test_video_with_fallback_text_only_keeps_text(self):
        """<video> fallback text leaks through as bare text, not as a player."""
        sanitizer = BleachSanitizer()
        result = sanitizer.clean(FEED_CONTENT_WITH_VIDEO)

        assert "<video" not in result
        assert "<source" not in result

        # The fallback text inside <video> leaks through as bare text
        assert "Your browser does not support" in result

        # Regular tags survive
        assert "<h2>" in result
        assert "<p>" in result
        assert "<img" in result

    def test_audio_tag_stripped(self):
        """<audio> tags are also stripped."""
        sanitizer = BleachSanitizer()
        result = sanitizer.clean(FEED_CONTENT_WITH_AUDIO)

        assert "<audio" in FEED_CONTENT_WITH_AUDIO
        assert "<audio" not in result
        assert "<source" not in result
        assert "episode.mp3" not in result

        # Text survives
        assert "Podcast Episode" in result

    def test_iframe_stripped(self):
        """<iframe> embeds (YouTube, etc.) are stripped."""
        sanitizer = BleachSanitizer()
        result = sanitizer.clean(FEED_CONTENT_WITH_IFRAME)

        assert "<iframe" in FEED_CONTENT_WITH_IFRAME
        assert "<iframe" not in result
        assert "youtube.com" not in result

        # Surrounding text survives
        assert "Watch this video" in result
        assert "Pretty cool" in result

    def test_allowed_tags_missing_media_elements(self):
        """Document which media tags are missing from ALLOWED_TAGS."""
        missing_media_tags = []
        media_tags = ["video", "source", "audio", "iframe", "picture", "track"]

        for tag in media_tags:
            if tag not in BleachSanitizer.ALLOWED_TAGS:
                missing_media_tags.append(tag)

        # All media tags are currently missing
        assert missing_media_tags == ["video", "source", "audio", "iframe", "picture", "track"]

    def test_side_by_side_comparison(self):
        """Show the before/after for the Zeke blog post content."""
        sanitizer = BleachSanitizer()
        result = sanitizer.clean(BLOG_POST_HTML)

        # Count how many HTML tags survive
        import re

        input_tags = set(re.findall(r"<(\w+)", BLOG_POST_HTML))
        output_tags = set(re.findall(r"<(\w+)", result))

        # Input has: video, source, p
        assert "video" in input_tags
        assert "source" in input_tags
        assert "p" in input_tags

        # Output only has: p
        assert "video" not in output_tags
        assert "source" not in output_tags
        assert "p" in output_tags

        # The entire first element of the post (the video) is gone
        # Only the paragraph text remains
        stripped = result.strip()
        assert not stripped.startswith("<video")
        # First meaningful content is now a paragraph
        # (there may be whitespace/newlines from the stripped video)
