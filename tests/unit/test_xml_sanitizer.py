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
        assert isinstance(result, str)
        assert "\x00" not in result
        assert "hello" in result and "world" in result

    def test_removes_chars_0x01_to_0x08(self):
        """Removes control characters 0x01 through 0x08."""
        # Build string with all chars from 0x01 to 0x08
        control_chars = "".join(chr(i) for i in range(0x01, 0x09))
        text = f"hello{control_chars}world"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"
        assert len(result) == len("helloworld")
        for c in range(0x01, 0x09):
            assert chr(c) not in result

    def test_removes_vertical_tab_0x0b(self):
        """Removes vertical tab (0x0B)."""
        text = "hello\x0bworld"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"
        assert "\x0b" not in result
        assert len(result) == len(text) - 1

    def test_removes_form_feed_0x0c(self):
        """Removes form feed (0x0C)."""
        text = "hello\x0cworld"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"
        assert "\x0c" not in result
        assert len(result) == len(text) - 1

    def test_removes_chars_0x0e_to_0x1f(self):
        """Removes control characters 0x0E through 0x1F."""
        # Build string with all chars from 0x0E to 0x1F
        control_chars = "".join(chr(i) for i in range(0x0E, 0x20))
        text = f"hello{control_chars}world"
        result = strip_xml_control_chars(text)
        assert result == "helloworld"
        assert len(result) == len("helloworld")
        for c in range(0x0E, 0x20):
            assert chr(c) not in result

    def test_keeps_tab_0x09(self):
        """Preserves horizontal tab (0x09) - valid in XML."""
        text = "hello\tworld"
        result = strip_xml_control_chars(text)
        assert result == "hello\tworld"
        assert "\t" in result
        assert len(result) == len(text)
        # Verify nearby illegal chars would be stripped
        assert strip_xml_control_chars("hello\x08\tworld") == "hello\tworld"

    def test_keeps_newline_0x0a(self):
        """Preserves newline (0x0A) - valid in XML."""
        text = "hello\nworld"
        result = strip_xml_control_chars(text)
        assert result == "hello\nworld"
        assert "\n" in result
        assert len(result) == len(text)
        # Verify adjacent illegal char 0x0B is stripped while 0x0A is kept
        assert strip_xml_control_chars("hello\n\x0bworld") == "hello\nworld"

    def test_keeps_carriage_return_0x0d(self):
        """Preserves carriage return (0x0D) - valid in XML."""
        text = "hello\rworld"
        result = strip_xml_control_chars(text)
        assert result == "hello\rworld"
        assert "\r" in result
        assert len(result) == len(text)
        # Verify adjacent illegal char 0x0E is stripped while 0x0D is kept
        assert strip_xml_control_chars("hello\r\x0eworld") == "hello\rworld"

    def test_keeps_normal_text_unchanged(self):
        """Normal text without control characters is unchanged."""
        text = "Hello, World! This is a normal text with numbers 12345."
        result = strip_xml_control_chars(text)
        assert result == text
        assert isinstance(result, str)
        assert len(result) == len(text)

    def test_handles_empty_string(self):
        """Empty string returns empty string."""
        result = strip_xml_control_chars("")
        assert result == ""
        assert isinstance(result, str)
        assert len(result) == 0

    def test_handles_none_input(self):
        """None input returns empty string."""
        result = strip_xml_control_chars(None)
        assert result == ""
        assert isinstance(result, str)
        assert len(result) == 0

    def test_handles_mixed_content(self):
        """Correctly handles text with both valid and invalid control chars."""
        # Tab (valid), NUL (invalid), newline (valid), BEL (invalid), CR (valid)
        text = "line1\t\x00text\n\x07more\rend"
        result = strip_xml_control_chars(text)
        assert result == "line1\ttext\nmore\rend"
        # Valid control chars preserved
        assert "\t" in result
        assert "\n" in result
        assert "\r" in result
        # Invalid control chars removed
        assert "\x00" not in result
        assert "\x07" not in result

    def test_handles_unicode_content(self):
        """Unicode content is preserved."""
        text = "Hello \u4e16\u754c \u0645\u0631\u062d\u0628\u0627"  # "Hello 世界 مرحبا"
        result = strip_xml_control_chars(text)
        assert result == text
        assert len(result) == len(text)
        # Unicode with embedded illegal chars should strip only the illegal chars
        assert strip_xml_control_chars("Hello\x00\u4e16\u754c") == "Hello\u4e16\u754c"

    def test_handles_html_content(self):
        """HTML content is preserved (only control chars removed)."""
        text = "<p>Hello\x00<strong>World</strong></p>"
        result = strip_xml_control_chars(text)
        assert result == "<p>Hello<strong>World</strong></p>"
        assert "\x00" not in result
        # HTML structure preserved intact
        assert result.startswith("<p>") and result.endswith("</p>")

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
        assert len(result) == len("startend")
        # Verify every illegal char is gone
        for c in range(0x00, 0x09):
            assert chr(c) not in result
        assert "\x0b" not in result
        assert "\x0c" not in result

    def test_keeps_all_legal_chars(self):
        """Preserves all legal control characters (tab, newline, CR)."""
        text = "\t\n\r"
        result = strip_xml_control_chars(text)
        assert result == "\t\n\r"
        assert len(result) == 3
        # All three legal control chars present
        assert "\t" in result
        assert "\n" in result
        assert "\r" in result

    def test_handles_only_illegal_chars(self):
        """String containing only illegal chars becomes empty."""
        text = "\x00\x01\x02\x03"
        result = strip_xml_control_chars(text)
        assert result == ""
        assert isinstance(result, str)
        assert len(result) == 0

    def test_preserves_space_and_printable(self):
        """Space (0x20) and printable characters are preserved."""
        text = " !\"#$%&'()*+,-./"
        result = strip_xml_control_chars(text)
        assert result == text
        assert len(result) == len(text)
        # Space (0x20) is the first legal non-control char; 0x1F just below it is illegal
        assert strip_xml_control_chars("\x1f " + text) == " " + text

    def test_handles_emoji(self):
        """Emoji characters (high Unicode) are preserved."""
        text = "Hello \U0001f600 World"  # Grinning face emoji
        result = strip_xml_control_chars(text)
        assert result == text
        assert "\U0001f600" in result
        # Emoji with embedded illegal chars should strip only the illegal chars
        assert strip_xml_control_chars("\x00\U0001f600\x01") == "\U0001f600"
