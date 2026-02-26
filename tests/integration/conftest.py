# tests/integration/conftest.py
"""Integration test configuration and fixtures.

Server detection delegates to the canonical ``is_planetcf_running()`` in
``tests.e2e.conftest`` so there is exactly one implementation to maintain.
"""

import pytest

from tests.e2e.conftest import E2E_BASE_URL, is_planetcf_running

WRANGLER_BASE_URL = E2E_BASE_URL

# Skip marker for tests requiring wrangler server
requires_wrangler = pytest.mark.skipif(
    not is_planetcf_running(WRANGLER_BASE_URL),
    reason=(
        f"Planet CF not responding at {WRANGLER_BASE_URL}/health "
        "(expected JSON with service='planetcf')"
    ),
)
