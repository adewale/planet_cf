# src/xml_sanitizer.py
"""XML control character sanitization utility.

This module provides a function to strip illegal XML 1.0 control characters
from text content. It's applied at the lowest layer in the content pipeline
to ensure all output is valid XML.

XML 1.0 Specification (Section 2.2 Characters):
  Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]

This means the following control characters are ILLEGAL in XML 1.0:
  - 0x00-0x08 (NUL through BACKSPACE)
  - 0x0B (Vertical Tab)
  - 0x0C (Form Feed)
  - 0x0E-0x1F (Shift Out through Unit Separator)

LEGAL control characters:
  - 0x09 (Horizontal Tab)
  - 0x0A (Line Feed / Newline)
  - 0x0D (Carriage Return)
"""

import re

# Pre-compiled regex for illegal XML 1.0 control characters
# Matches: 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F
# Excludes: 0x09 (tab), 0x0A (newline), 0x0D (carriage return)
_ILLEGAL_XML_CHARS_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f]",
    re.UNICODE,
)


def strip_xml_control_chars(text: str | None) -> str:
    """Remove control characters that are illegal in XML 1.0.

    XML 1.0 allows: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    This function removes: 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F

    Args:
        text: The text to sanitize. If None, returns empty string.

    Returns:
        The sanitized text with illegal control characters removed.

    Example:
        >>> strip_xml_control_chars("hello\\x00world")
        'helloworld'
        >>> strip_xml_control_chars("line1\\tline2")  # Tab is preserved
        'line1\\tline2'
    """
    if text is None:
        return ""

    return _ILLEGAL_XML_CHARS_RE.sub("", text)
