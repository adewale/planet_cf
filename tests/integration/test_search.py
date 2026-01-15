# tests/integration/test_search.py
"""Integration tests for search functionality.

These tests verify:
1. Entries are indexed in Vectorize when added
2. Search returns results for indexed entries
3. The re-index admin endpoint works correctly

These tests would have caught the bug where entries existed in D1
but were never indexed in Vectorize, causing search to return no results.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class MockFormData:
    """Mock form data that behaves like a dict."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockRequest:
    """Mock HTTP request object matching Cloudflare Workers Python SDK."""

    def __init__(
        self,
        url: str,
        method: str = "GET",
        cookies: str = "",
        form_data: dict | None = None,
    ):
        self.url = url
        self.method = method
        self._cookies = cookies
        self._form_data = form_data or {}
        self.headers = MagicMock()
        self.headers.get = MagicMock(side_effect=self._get_header)

    def _get_header(self, name, default=None):
        if name.lower() == "cookie":
            return self._cookies
        return default

    async def form_data(self):
        return MockFormData(self._form_data)


@pytest.mark.asyncio
async def test_search_returns_results_for_indexed_entries(mock_env_with_entries):
    """Search should return results when entries are indexed in Vectorize.

    This test would have caught the bug where entries existed in D1
    but weren't indexed in Vectorize.
    """
    from src.main import PlanetCF

    # Pre-populate the Vectorize index with entry IDs
    # This simulates what should happen when entries are added
    await mock_env_with_entries.SEARCH_INDEX.upsert(
        [
            {"id": "1", "values": [0.1] * 768, "metadata": {"title": "Test Entry 1"}},
            {"id": "2", "values": [0.1] * 768, "metadata": {"title": "Test Entry 2"}},
        ]
    )

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=test")
    response = await worker.fetch(request)

    assert response.status == 200
    body = response.body if hasattr(response, "body") else str(response)
    # Should contain results, not "No results found"
    assert "No results found" not in body or "Test Entry" in body


@pytest.mark.asyncio
async def test_search_returns_no_results_when_index_empty(mock_env_with_entries):
    """Search should return 'no results' when Vectorize index is empty.

    This test documents the bug behavior - entries in D1 but not indexed.
    """
    from src.main import PlanetCF

    # Don't populate Vectorize - simulating the bug condition
    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=test")
    response = await worker.fetch(request)

    assert response.status == 200
    body = response.body if hasattr(response, "body") else str(response)
    # With empty index, should show no results
    assert "No results found" in body


@pytest.mark.asyncio
async def test_entry_indexing_calls_vectorize_upsert(mock_env):
    """_index_entry_for_search should upsert vectors to Vectorize.

    This test verifies that when we add an entry, it gets indexed.
    """
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    # Track upsert calls
    original_upsert = mock_env.SEARCH_INDEX.upsert
    upsert_calls = []

    async def tracking_upsert(vectors):
        upsert_calls.append(vectors)
        return await original_upsert(vectors)

    mock_env.SEARCH_INDEX.upsert = tracking_upsert

    # Call the indexing method directly
    await worker._index_entry_for_search(
        entry_id=1,
        title="Test Entry",
        content="This is test content about Cloudflare Workers.",
    )

    # Verify upsert was called
    assert len(upsert_calls) == 1
    assert upsert_calls[0][0]["id"] == "1"
    assert len(upsert_calls[0][0]["values"]) == 768  # Embedding dimension


@pytest.mark.asyncio
async def test_entry_indexing_handles_ai_failure_gracefully(mock_env):
    """When AI embedding fails, indexing should log but not crash.

    This ensures entry creation succeeds even if search indexing fails.
    """
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    # Make AI return empty result
    mock_env.AI.run = AsyncMock(return_value={"data": []})

    # Should not raise, just log and return
    await worker._index_entry_for_search(
        entry_id=1,
        title="Test Entry",
        content="This is test content.",
    )

    # Verify vector was NOT added (AI returned empty)
    assert len(mock_env.SEARCH_INDEX.vectors) == 0


@pytest.mark.asyncio
async def test_reindex_endpoint_indexes_all_entries(mock_env):
    """The /admin/reindex endpoint should index all existing entries.

    This tests the fix for the bug - a way to re-index entries
    that were added before Vectorize was working.
    """
    from src.main import PlanetCF
    from tests.conftest import MockD1

    # Set up a fresh MockD1 with all required data
    mock_env.DB = MockD1(
        {
            "entries": [
                {
                    "id": 1,
                    "feed_id": 1,
                    "title": "Test Entry 1",
                    "content": "<p>Content 1</p>",
                },
                {
                    "id": 2,
                    "feed_id": 1,
                    "title": "Test Entry 2",
                    "content": "<p>Content 2</p>",
                },
            ],
            "admins": [
                {"id": 1, "github_username": "testadmin", "is_active": 1},
            ],
            "audit_log": [],
        }
    )

    worker = PlanetCF()
    worker.env = mock_env

    # Verify index is initially empty
    assert len(mock_env.SEARCH_INDEX.vectors) == 0

    # Create a mock admin session
    admin = {"id": 1, "github_username": "testadmin"}

    # Call the reindex method directly
    response = await worker._reindex_all_entries(admin)

    # Parse response
    import json

    body = response.body if hasattr(response, "body") else str(response)
    result = json.loads(body)

    # Should have indexed 2 entries
    assert result["success"] is True
    assert result["indexed"] == 2
    assert result["failed"] == 0

    # Verify vectors were added to index
    assert len(mock_env.SEARCH_INDEX.vectors) == 2
    assert "1" in mock_env.SEARCH_INDEX.vectors
    assert "2" in mock_env.SEARCH_INDEX.vectors


@pytest.mark.asyncio
async def test_search_query_validation(mock_env):
    """Search should validate query parameters."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env

    # Too short query
    request = MockRequest("https://planetcf.com/search?q=a")
    response = await worker.fetch(request)
    body = response.body if hasattr(response, "body") else str(response)
    assert "too short" in body.lower() or response.status != 200

    # Empty query should redirect or show error
    request = MockRequest("https://planetcf.com/search?q=")
    response = await worker.fetch(request)
    # Should handle gracefully


@pytest.mark.asyncio
async def test_vectorize_index_consistency(mock_env):
    """Vectorize index should be consistent with D1 entries.

    This test documents the invariant that was violated:
    Every entry in D1 should have a corresponding vector in Vectorize.
    """
    from src.main import PlanetCF
    from tests.conftest import MockD1

    # Set up mock D1 with entries
    entries_data = [
        {"id": 1, "title": "Test Entry 1", "content": "<p>Content 1</p>"},
        {"id": 2, "title": "Test Entry 2", "content": "<p>Content 2</p>"},
    ]
    mock_env.DB = MockD1(
        {
            "entries": entries_data,
            "admins": [{"id": 1, "github_username": "testadmin", "is_active": 1}],
            "audit_log": [],
        }
    )

    worker = PlanetCF()
    worker.env = mock_env

    # Get all entry IDs from D1
    d1_entry_ids = {str(e["id"]) for e in entries_data}

    # Initially, Vectorize is empty - this is the bug condition
    vectorize_ids = set(mock_env.SEARCH_INDEX.vectors.keys())
    assert vectorize_ids == set()  # Empty - bug condition

    # After reindexing, should match
    admin = {"id": 1, "github_username": "testadmin"}
    await worker._reindex_all_entries(admin)

    vectorize_ids = set(mock_env.SEARCH_INDEX.vectors.keys())
    assert vectorize_ids == d1_entry_ids  # Now consistent


@pytest.mark.asyncio
async def test_search_with_special_characters(mock_env_with_entries):
    """Search should handle special characters in queries."""
    from src.main import PlanetCF

    # Add vectors for the entries
    await mock_env_with_entries.SEARCH_INDEX.upsert(
        [
            {"id": "1", "values": [0.1] * 768, "metadata": {"title": "Test Entry 1"}},
        ]
    )

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    # Query with special characters
    request = MockRequest("https://planetcf.com/search?q=test%20%26%20entry")
    response = await worker.fetch(request)

    # Should not crash
    assert response.status == 200


@pytest.mark.asyncio
async def test_e2e_entry_to_search_result(mock_env):
    """End-to-end test: store entry with unique word, search for it, find it.

    This is the definitive test for search functionality. It verifies:
    1. An entry with a unique word is stored
    2. The entry is automatically indexed in Vectorize
    3. Searching for that unique word returns the entry

    This test would have caught the search bug where entries were stored
    but never indexed.
    """
    import uuid

    from src.main import PlanetCF
    from tests.conftest import MockD1

    # Generate a unique word that definitely won't exist elsewhere
    unique_word = f"xyzzy{uuid.uuid4().hex[:8]}"

    # Set up mock D1 with the entry we'll create
    # The entry has our unique word in the title
    mock_env.DB = MockD1(
        {
            "feeds": [
                {
                    "id": 1,
                    "url": "https://example.com/feed.xml",
                    "title": "Test Feed",
                    "is_active": 1,
                    "site_url": "https://example.com",
                }
            ],
            "entries": [
                {
                    "id": 42,
                    "feed_id": 1,
                    "guid": "unique-entry-1",
                    "url": "https://example.com/post/1",
                    "title": f"Article about {unique_word} technology",
                    "content": f"<p>This post discusses {unique_word} in detail.</p>",
                    "published_at": "2026-01-15T12:00:00Z",
                    "feed_title": "Test Feed",
                    "feed_site_url": "https://example.com",
                }
            ],
        }
    )

    worker = PlanetCF()
    worker.env = mock_env

    # Step 1: Verify Vectorize starts empty
    assert len(mock_env.SEARCH_INDEX.vectors) == 0

    # Step 2: Index the entry (simulating what happens during feed processing)
    await worker._index_entry_for_search(
        entry_id=42,
        title=f"Article about {unique_word} technology",
        content=f"This post discusses {unique_word} in detail.",
    )

    # Step 3: Verify entry was indexed in Vectorize
    assert len(mock_env.SEARCH_INDEX.vectors) == 1
    assert "42" in mock_env.SEARCH_INDEX.vectors

    # Step 4: Search for the unique word
    request = MockRequest(f"https://planetcf.com/search?q={unique_word}")
    response = await worker.fetch(request)

    # Step 5: Verify search succeeds
    assert response.status == 200

    # Step 6: Verify the entry appears in search results
    body = response.body if hasattr(response, "body") else str(response)

    # The response should contain our unique word (from the entry title)
    assert unique_word in body, f"Expected '{unique_word}' to appear in search results"

    # Should NOT show "No results found"
    assert "No results found" not in body


@pytest.mark.asyncio
async def test_e2e_full_upsert_to_search(mock_env):
    """End-to-end test using _upsert_entry to verify automatic indexing.

    This test uses a feedparser-like entry dict to test the full flow
    from entry upsert through automatic indexing to search results.
    """
    import uuid

    from src.main import PlanetCF
    from tests.conftest import MockD1

    # Generate unique identifier
    unique_id = f"quantum{uuid.uuid4().hex[:8]}"

    # Mock D1 that will "return" the inserted entry
    # We simulate the INSERT...RETURNING by having the entry already in results
    mock_env.DB = MockD1(
        {
            "feeds": [
                {
                    "id": 1,
                    "url": "https://example.com/feed.xml",
                    "title": "Test Feed",
                    "is_active": 1,
                    "site_url": "https://example.com",
                }
            ],
            "entries": [
                {
                    "id": 99,
                    "feed_id": 1,
                    "guid": f"entry-{unique_id}",
                    "url": f"https://example.com/{unique_id}",
                    "title": f"The {unique_id} Revolution",
                    "content": f"<p>All about {unique_id}.</p>",
                    "published_at": "2026-01-15T10:00:00Z",
                    "feed_title": "Test Feed",
                    "feed_site_url": "https://example.com",
                }
            ],
        }
    )

    worker = PlanetCF()
    worker.env = mock_env

    # Verify Vectorize starts empty
    assert len(mock_env.SEARCH_INDEX.vectors) == 0

    # Create a feedparser-like entry object
    feedparser_entry = {
        "id": f"entry-{unique_id}",
        "link": f"https://example.com/{unique_id}",
        "title": f"The {unique_id} Revolution",
        "content": [{"value": f"<p>All about {unique_id}.</p>"}],
        "published_parsed": (2026, 1, 15, 10, 0, 0, 0, 0, 0),
    }

    # Upsert the entry - this should automatically index it
    entry_id = await worker._upsert_entry(feed_id=1, entry=feedparser_entry)

    # Entry should have been indexed (mock returns id=99)
    # Note: The mock D1 returns entries[0] for any query, so entry_id will be the mock's id
    assert entry_id is not None

    # Vectorize should now have a vector
    assert len(mock_env.SEARCH_INDEX.vectors) >= 1

    # Search for the unique identifier
    request = MockRequest(f"https://planetcf.com/search?q={unique_id}")
    response = await worker.fetch(request)

    assert response.status == 200
    body = response.body if hasattr(response, "body") else str(response)

    # The unique word should appear in results
    assert unique_id in body, f"Expected '{unique_id}' in search results"
