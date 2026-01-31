# tests/e2e/conftest.py
"""E2E test configuration and fixtures.

This provides the requires_server decorator/marker for tests that need
a running wrangler dev server.
"""

import os
import socket

import pytest

# Configuration for e2e tests
E2E_HOST = os.environ.get("E2E_HOST", "localhost")
E2E_PORT = int(os.environ.get("E2E_PORT", "8787"))


def is_server_running(host: str = E2E_HOST, port: int = E2E_PORT) -> bool:
    """Check if the dev server is running on the specified host:port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


# Decorator to skip tests when server is not running
requires_server = pytest.mark.skipif(
    not is_server_running(),
    reason=f"E2E server not running on {E2E_HOST}:{E2E_PORT}. Start with: npx wrangler dev --remote",
)
