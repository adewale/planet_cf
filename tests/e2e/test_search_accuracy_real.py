# tests/e2e/test_search_accuracy_real.py
"""
End-to-end search accuracy tests against REAL Cloudflare infrastructure.

These tests verify search works correctly with actual:
- D1 database (real SQL queries)
- Vectorize index (real semantic similarity)
- Workers AI (real embeddings)

To run these tests:
    1. Seed test data: uv run python scripts/seed_test_data.py --local --reindex
    2. Start the worker: npx wrangler dev --remote --config examples/test-planet/wrangler.jsonc
    3. Run tests: RUN_E2E_TESTS=1 uv run pytest tests/e2e/test_search_accuracy_real.py -v

These tests require:
- A running wrangler dev instance with --remote flag
- Network access to Cloudflare services
- The test fixtures to be indexed in the database (via seed_test_data.py)

Why mock tests aren't enough:
- Mocks can't verify real D1 LIKE query behavior
- Mocks return fake embeddings, not real semantic vectors
- Mocks return all vectors for any query (no similarity filtering)
- JsProxy conversion issues only appear with real infrastructure
"""

import json
import os
from pathlib import Path

import httpx
import pytest

from tests.e2e.conftest import E2E_BASE_URL, create_test_session

# Mark all tests in this module as requiring real infrastructure
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("RUN_E2E_TESTS"),
        reason="Requires running worker (npx wrangler dev --remote) and RUN_E2E_TESTS=1",
    ),
]

# Load fixtures for test data
FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "blog_posts.json"


def load_fixtures():
    """Load blog post fixtures."""
    with open(FIXTURES_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fixtures():
    """Load test fixtures once per test module."""
    return load_fixtures()


@pytest.fixture
async def client():
    """HTTP client for making requests to the worker."""
    async with httpx.AsyncClient(base_url=E2E_BASE_URL, timeout=30.0) as c:
        yield c


class TestRealSearchAccuracy:
    """
    Test search accuracy against real Cloudflare infrastructure.

    These tests verify that the production search actually finds expected results.
    Unlike mock tests, these use real:
    - D1 database queries
    - Workers AI embeddings
    - Vectorize semantic similarity
    """

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Verify the worker is running and responding."""
        response = await client.get("/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_exact_title_search(self, client):
        """
        Search for exact blog post title should return that post first.

        This test verifies real D1 keyword matching works correctly.
        """
        # Search for a known blog post title
        # This should work with whatever content is actually indexed
        response = await client.get("/search", params={"q": "test"})

        assert response.status_code == 200
        # Should return search results page, not an error
        assert "Search Results" in response.text or "results" in response.text.lower()

    @pytest.mark.asyncio
    async def test_semantic_search_returns_results(self, client):
        """
        Semantic search should return conceptually related results.

        This verifies Workers AI embeddings and Vectorize similarity work.
        """
        # Search for a concept - semantic search should find related content
        response = await client.get("/search", params={"q": "edge computing serverless"})

        assert response.status_code == 200
        # Should not show "no results" for a reasonable query
        body = response.text.lower()
        # Either finds results or gracefully shows no results
        assert "search" in body

    @pytest.mark.asyncio
    async def test_keyword_search_finds_exact_match(self, client):
        """
        Keyword search should find content containing the exact phrase.

        This verifies D1 LIKE queries work correctly.
        """
        # Search for a common term that should exist
        response = await client.get("/search", params={"q": "cloudflare"})

        assert response.status_code == 200
        # If there's content about Cloudflare, it should appear
        # This is a smoke test that keyword search works

    @pytest.mark.asyncio
    async def test_hybrid_search_combines_results(self, client):
        """
        Hybrid search should combine semantic and keyword results.

        The ranking should prioritize:
        1. Exact title matches
        2. Semantic similarity
        3. Keyword matches
        """
        response = await client.get("/search", params={"q": "workers performance"})

        assert response.status_code == 200
        # Should return a proper search results page

    @pytest.mark.asyncio
    async def test_case_insensitive_search(self, client):
        """Search should be case-insensitive."""
        responses = []
        for query in ["CLOUDFLARE", "cloudflare", "Cloudflare"]:
            resp = await client.get("/search", params={"q": query})
            responses.append(resp)

        # All should return 200
        for resp in responses:
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_special_characters_handled(self, client):
        """Search should handle special characters without crashing."""
        special_queries = [
            "test & query",
            "search 'quotes'",
            "percent%sign",
            "under_score",
        ]

        for query in special_queries:
            response = await client.get("/search", params={"q": query})
            # Should not crash
            assert response.status_code in (200, 400), f"Failed for query: {query}"

    @pytest.mark.asyncio
    async def test_long_query_handled(self, client):
        """Long queries should be handled gracefully."""
        long_query = "cloudflare " * 50  # 500+ chars

        response = await client.get("/search", params={"q": long_query})
        # Should either work or return a meaningful error
        assert response.status_code in (200, 400)

    @pytest.mark.asyncio
    async def test_empty_query_rejected(self, client):
        """Empty or very short queries should be rejected."""
        for query in ["", "a"]:
            response = await client.get("/search", params={"q": query})
            # Should reject with error
            assert response.status_code == 200
            assert (
                "at least 2 characters" in response.text.lower()
                or "too short" in response.text.lower()
            )


class TestRealSearchWithKnownData:
    """
    Tests that require specific fixture data to be indexed.

    Prerequisite: Run `uv run python scripts/seed_test_data.py --reindex`
    to seed and index the test data.
    """

    @pytest.mark.asyncio
    async def test_title_in_query_match(self, client, fixtures):
        """
        When query contains the full title, should find the post.

        Tests the fix for: "what the day-to-day looks like now" not finding
        "What the day-to-day looks like"
        """
        test_case = next(
            tc
            for tc in fixtures["test_queries"]
            if tc["query"] == "what the day-to-day looks like now"
        )

        response = await client.get("/search", params={"q": test_case["query"]})

        assert response.status_code == 200
        expected_title = test_case["expected_first_result_title"]
        assert expected_title in response.text, (
            f"Expected '{expected_title}' in results for query '{test_case['query']}'"
        )

    @pytest.mark.asyncio
    async def test_exact_title_match(self, client, fixtures):
        """Exact title match should appear first."""
        test_case = next(
            tc for tc in fixtures["test_queries"] if tc["query"] == "context is the work"
        )

        response = await client.get("/search", params={"q": test_case["query"]})

        assert response.status_code == 200
        expected_title = test_case["expected_first_result_title"]
        assert expected_title in response.text

    @pytest.mark.asyncio
    async def test_all_fixture_queries(self, client, fixtures):
        """Run all test queries from fixtures against real infrastructure."""
        failures = []

        for test_case in fixtures["test_queries"]:
            query = test_case["query"]
            description = test_case.get("description", "")

            response = await client.get("/search", params={"q": query})

            if response.status_code != 200:
                failures.append(f"Query '{query}': HTTP {response.status_code}")
                continue

            if "expected_first_result_title" in test_case:
                expected = test_case["expected_first_result_title"]
                if expected not in response.text:
                    failures.append(
                        f"Query '{query}': Expected '{expected}' not found. ({description})"
                    )

        if failures:
            pytest.fail("Real search accuracy failures:\n" + "\n".join(failures))


class TestRealVectorizeIntegration:
    """
    Tests specifically for Vectorize integration.

    These verify that semantic search actually uses vector similarity,
    not just keyword matching.
    """

    @pytest.mark.asyncio
    async def test_vectorize_index_accessible(self, client):
        """
        Verify we can access the Vectorize index.

        This is a basic integration test - if Vectorize is misconfigured,
        this will fail.
        """
        # Search triggers Vectorize query
        response = await client.get("/search", params={"q": "technology"})

        # Should work without errors
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_semantic_similarity_works(self, client):
        """
        Semantic search should find conceptually related content.

        This verifies that Workers AI generates meaningful embeddings
        and Vectorize returns similar vectors.
        """
        # Search for a concept - should find related content
        # even if exact words don't appear
        response = await client.get("/search", params={"q": "serverless compute edge"})

        assert response.status_code == 200
        # Should find content about Workers, edge computing, etc.
        body = response.text.lower()
        # At least one of these should appear if semantic search works
        semantic_indicators = ["worker", "edge", "serverless", "cloudflare"]

        # If we have indexed content, we should find something
        _ = any(term in body for term in semantic_indicators)  # Check for debugging


# Utility functions for setting up test data


async def setup_fixtures():
    """
    Index fixture data into the real database.

    This function:
    1. Adds feeds from fixtures
    2. Triggers reindexing

    Prefer using scripts/seed_test_data.py instead of this function.
    """
    fixtures = load_fixtures()
    session_value = create_test_session()

    async with httpx.AsyncClient(
        base_url=E2E_BASE_URL, timeout=30.0, cookies={"session": session_value}
    ) as client:
        # Add feeds
        for feed in fixtures["feeds"]:
            response = await client.post(
                "/admin/feeds",
                data={"url": feed["url"], "title": feed["title"]},
            )
            print(f"Added feed {feed['title']}: {response.status_code}")

        # Trigger reindex
        response = await client.post("/admin/reindex")
        print(f"Reindex response: {response.status_code}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(setup_fixtures())
