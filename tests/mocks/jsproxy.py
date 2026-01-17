# tests/mocks/jsproxy.py
"""
Mock JsProxy objects that simulate Pyodide's JavaScript interop.

In production, Cloudflare Workers Python uses Pyodide, which wraps
JavaScript objects in JsProxy. These don't behave like Python dicts:
- They don't support `dict["key"]` syntax
- They need `.to_py()` to convert to Python
- Arrays are not Python lists

This module provides mocks that replicate this behavior for testing.
"""

from typing import Any


class JsProxyMock:
    """
    Base JsProxy mock that simulates Pyodide's JavaScript object wrapper.

    Key differences from Python objects:
    - `obj["key"]` raises TypeError (not subscriptable)
    - `obj.get("key")` returns JsProxy wrapper (needs conversion)
    - `obj.to_py()` converts to Python dict
    """

    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key):
        """Simulate JsProxy not being subscriptable like a dict."""
        raise TypeError("'pyodide.ffi.JsProxy' object is not subscriptable")

    def get(self, key, default=None):
        """Return wrapped value (simulates JS get behavior)."""
        value = self._data.get(key, default)
        if isinstance(value, dict):
            return JsProxyDict(value)
        return value

    def to_py(self) -> dict:
        """Convert to Python dict (the key Pyodide conversion method)."""
        return dict(self._data)

    def __iter__(self):
        """Iterate over keys."""
        return iter(self._data)

    def items(self):
        """Return items as JsProxy wrappers."""
        return self._data.items()

    def keys(self):
        """Return keys."""
        return self._data.keys()

    def values(self):
        """Return values."""
        return self._data.values()


class JsProxyDict(JsProxyMock):
    """JsProxy wrapper for dict-like objects."""

    pass


class JsProxyArray:
    """
    JsProxy wrapper for arrays (JavaScript Array).

    In Pyodide, JavaScript arrays are wrapped and:
    - `arr[0]` returns JsProxy-wrapped element
    - `len(arr)` may not work directly
    - `for item in arr` yields JsProxy-wrapped elements
    - `arr.to_py()` converts to Python list
    """

    def __init__(self, items: list):
        self._items = items

    def __iter__(self):
        """Iterate yields JsProxy-wrapped items."""
        for item in self._items:
            if isinstance(item, dict):
                yield JsProxyDict(item)
            else:
                yield item

    def __len__(self):
        """Some JsProxy arrays support len, some don't."""
        return len(self._items)

    def __getitem__(self, index):
        """Get item returns JsProxy-wrapped element."""
        item = self._items[index]
        if isinstance(item, dict):
            return JsProxyDict(item)
        return item

    def to_py(self) -> list:
        """Convert to Python list."""
        return list(self._items)


def wrap_as_jsproxy(value: Any) -> Any:
    """
    Wrap a Python value as a JsProxy mock.

    Use this to simulate D1 query results in tests:

        result = MockD1Result(results=wrap_as_jsproxy([
            {"id": 1, "url": "https://example.com/feed.xml"},
            {"id": 2, "url": "https://other.com/rss.xml"},
        ]))
    """
    if isinstance(value, dict):
        return JsProxyDict(value)
    elif isinstance(value, list):
        return JsProxyArray(value)
    else:
        return value
