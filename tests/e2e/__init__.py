# tests/e2e/__init__.py
"""
End-to-End Testing for Planet CF

This package provides infrastructure for testing the actual Cloudflare Workers
environment, including D1 database access and JsProxy handling.

The key insight: our unit tests use Python mocks that return Python dicts,
but production uses Pyodide/JsProxy which returns JavaScript objects.
This E2E test suite runs against `wrangler dev --remote` to use real D1.
"""
