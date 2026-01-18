# tests/integration/conftest.py
"""Integration test configuration and fixtures."""

import socket

import pytest

# Configuration for e2e tests that require a running wrangler server
WRANGLER_HOST = "localhost"
WRANGLER_PORT = 8787


def is_wrangler_running() -> bool:
    """Check if wrangler dev server is running on localhost:8787."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((WRANGLER_HOST, WRANGLER_PORT))
        sock.close()
        return result == 0
    except OSError:
        return False


# Skip marker for tests requiring wrangler server
requires_wrangler = pytest.mark.skipif(
    not is_wrangler_running(),
    reason=f"Wrangler dev server not running on {WRANGLER_HOST}:{WRANGLER_PORT}",
)
