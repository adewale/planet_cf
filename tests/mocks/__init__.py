# tests/mocks/__init__.py
"""
Mock objects for testing Planet CF.

These mocks simulate the behavior of production objects, particularly
the Pyodide JsProxy objects that wrap JavaScript values.
"""

from .d1 import MockD1Database, MockD1PreparedStatement, MockD1Result
from .jsproxy import JsProxyArray, JsProxyDict, JsProxyMock

__all__ = [
    "JsProxyMock",
    "JsProxyArray",
    "JsProxyDict",
    "MockD1Database",
    "MockD1PreparedStatement",
    "MockD1Result",
]
