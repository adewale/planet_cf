# tests/unit/test_xml_sanitizer.py
"""Unit tests for XML control character sanitization.

XML 1.0 allows only specific characters:
  #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]

This module tests the strip_xml_control_chars function that removes
illegal control characters (0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F) while
preserving valid ones (tab=0x09, newline=0x0A, carriage return=0x0D).
"""

from src.xml_sanitizer import strip_xml_control_chars


class TestStripXmlControlChars:
    """Tests for the strip_xml_control_chars function."""

    def test_removes_null_char(self):
        """Removes NUL character (0x00)."""
        text = "hello\x00world"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"

    def test_removes_chars_0x01_to_0x08(self):
        """Removes control characters 0x01 through 0x08."""
        # Build string with all chars from 0x01 to 0x08
        control_chars = "".join(chr(i) for i in range(0x01, 0x09))
        text = f"hello{control_chars}world"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"

    def test_removes_vertical_tab_0x0b(self):
        """Removes vertical tab (0x0B)."""
        text = "hello\x0bworld"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"

    def test_removes_form_feed_0x0c(self):
        """Removes form feed (0x0C)."""
        text = "hello\x0cworld"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"

    def test_removes_chars_0x0e_to_0x1f(self):
        """Removes control characters 0x0E through 0x1F."""
        # Build string with all chars from 0x0E to 0x1F
        control_chars = "".join(chr(i) for i in range(0x0E, 0x20))
        text = f"hello{control_chars}world"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"

    def test_keeps_tab_0x09(self):
        """Preserves horizontal tab (0x09) - valid in XML."""
        text = "hello\tworld"
        result = strip_xml_control_chars(text)
        assert result == "hello\tworld"

    def test_keeps_newline_0x0a(self):
        """Preserves newline (0x0A) - valid in XML."""
        text = "hello\nworld"
        result = strip_xml_control_chars(text)
        assert result == "hello\nworld"

    def test_keeps_carriage_return_0x0d(self):
        """Preserves carriage return (0x0D) - valid in XML."""
        text = "hello\rworld"
        result = strip_xml_control_chars(text)
        assert result == "hello\rworld"

    def test_keeps_normal_text_unchanged(self):
        """Normal text without control characters is unchanged."""
        text = "Hello, World! This is a normal text with numbers 12345."
        result = strip_xml_control_chars(text)
        assert result == text

    def test_handles_empty_string(self):
        """Empty string returns empty string."""
        result = strip_xml_control_chars("")
        assert result == ""

    def test_handles_none_input(self):
        """None input returns empty string."""
        result = strip_xml_control_chars(None)
        assert result == ""

    def test_handles_mixed_content(self):
        """Correctly handles text with both valid and invalid control chars."""
        # Tab (valid), NUL (invalid), newline (valid), BEL (invalid), CR (valid)
        text = "line1\t\x00text\n\x07more\rend"
        result = strip_xml_control_chars(text)
        assert result == "line1\ttext\nmore\rend"

    def test_handles_unicode_content(self):
        """Unicode content is preserved."""
        text = "Hello \u4e16\u754c \u0645\u0631\u062d\u0628\u0627"  # "Hello 世界 مرحبا"
        result = strip_xml_control_chars(text)
        assert result == text

    def test_handles_html_content(self):
        """HTML content is preserved (only control chars removed)."""
        text = "<p>Hello\x00<strong>World</strong></p>"
        result = strip_xml_control_chars(text)
        assert result == "<p>Hello<strong>World</strong></p>"

    def test_handles_all_illegal_chars_in_sequence(self):
        """Removes all illegal control characters when they appear together."""
        # All illegal chars: 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F
        illegal = (
            "".join(chr(i) for i in range(0x00, 0x09))
            + "\x0b\x0c"
            + "".join(chr(i) for i in range(0x0E, 0x20))
        )
        text = f"start{illegal}end"
        result = strip_xml_control_chars(text)
        assert result == "startend"

    def test_keeps_all_legal_chars(self):
        """Preserves all legal control characters (tab, newline, CR)."""
        text = "\t\n\r"
        result = strip_xml_control_chars(text)
        assert result == "\t\n\r"

    def test_handles_only_illegal_chars(self):
        """String containing only illegal chars becomes empty."""
        text = "\x00\x01\x02\x03"
        result = strip_xml_control_chars(text)
        assert result == ""

    def test_preserves_space_and_printable(self):
        """Space (0x20) and printable characters are preserved."""
        text = " !\"#$%&'()*+,-./"
        result = strip_xml_control_chars(text)
        assert result == text

    def test_handles_emoji(self):
        """Emoji characters (high Unicode) are preserved."""
        text = "Hello \U0001f600 World"  # Grinning face emoji
        result = strip_xml_control_chars(text)
        assert result == text
