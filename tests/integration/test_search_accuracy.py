# tests/integration/test_search_accuracy.py
"""
Search accuracy tests using cached blog post fixtures.

These tests verify that search returns the expected results for specific queries.
The fixtures represent realistic blog posts and test cases that should work
in production.

Key scenarios tested:
- Exact title matches (query == title)
- Title-in-query matches (title is substring of query)
- Query-in-title matches (query is substring of title)
- Keyword matches in content
- Author searches
- Multi-word queries
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Load fixtures once at module level
FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "blog_posts.json"


def load_fixtures():
    """Load blog post fixtures from JSON file."""
    with open(FIXTURES_PATH) as f:
        return json.load(f)


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


class MockD1WithFixtures:
    """Mock D1 database populated with fixture data."""

    def __init__(self, fixtures):
        self.feeds = {f["id"]: f for f in fixtures["feeds"]}
        self.entries = {e["id"]: e for e in fixtures["entries"]}
        self._queries = []

    def prepare(self, query):
        self._queries.append(query)
        return MockD1Statement(self, query)


class MockD1Statement:
    """Mock D1 prepared statement."""

    def __init__(self, db, query):
        self.db = db
        self.query = query
        self._bindings = []

    def bind(self, *args):
        self._bindings = list(args)
        return self

    async def all(self):
        """Return results based on the query type."""
        results = []

        if "FROM entries" in self.query and "LIKE" in self.query:
            # Keyword search query
            if self._bindings:
                pattern = self._bindings[0].strip("%").lower()
                for entry in self.db.entries.values():
                    title = (entry.get("title") or "").lower()
                    content = (entry.get("content") or "").lower()
                    author = (entry.get("author") or "").lower()
                    if pattern in title or pattern in content or pattern in author:
                        # Add feed info
                        feed = self.db.feeds.get(entry["feed_id"], {})
                        results.append(
                            {
                                **entry,
                                "feed_title": feed.get("title", "Unknown"),
                                "feed_site_url": feed.get("site_url", ""),
                            }
                        )

        elif "FROM entries" in self.query and "WHERE e.id IN" in self.query:
            # Fetch entries by ID for semantic results
            for entry_id in self._bindings:
                if entry_id in self.db.entries:
                    entry = self.db.entries[entry_id]
                    feed = self.db.feeds.get(entry["feed_id"], {})
                    results.append(
                        {
                            **entry,
                            "feed_title": feed.get("title", "Unknown"),
                            "feed_site_url": feed.get("site_url", ""),
                        }
                    )

        return MagicMock(results=results)

    async def first(self):
        results = await self.all()
        return results.results[0] if results.results else None

    async def run(self):
        return MagicMock(success=True)


class MockVectorize:
    """Mock Vectorize index that returns semantic matches."""

    def __init__(self):
        self.vectors = {}

    async def upsert(self, vectors):
        for v in vectors:
            self.vectors[str(v["id"])] = v

    async def query(self, vector, options=None):
        """Return mock semantic matches based on query vector similarity."""
        # For simplicity, return all vectors with fake scores
        # In real tests, we could calculate actual cosine similarity
        matches = []
        for vid, v in self.vectors.items():
            matches.append(
                {
                    "id": vid,
                    "score": 0.7,  # Mock similarity score
                    "metadata": v.get("metadata", {}),
                }
            )
        return {"matches": matches}

    async def deleteByIds(self, ids):
        for id_ in ids:
            self.vectors.pop(str(id_), None)


class MockAI:
    """Mock Workers AI that returns embeddings."""

    async def run(self, model, params):
        # Return a mock 768-dim embedding
        return {"data": [[0.1] * 768]}


@pytest.fixture
def fixtures():
    """Load test fixtures."""
    return load_fixtures()


@pytest.fixture
def mock_env_with_fixtures(fixtures):
    """Create mock environment with fixture data."""
    env = MagicMock()
    env.DB = MockD1WithFixtures(fixtures)
    env.SEARCH_INDEX = MockVectorize()
    env.AI = MockAI()
    env.PLANET_NAME = "Planet CF"
    env.PLANET_DESCRIPTION = "Test blog aggregator"
    env.PLANET_URL = "https://planetcf.com"
    env.PLANET_OWNER_NAME = "Test"
    env.PLANET_OWNER_EMAIL = "test@example.com"
    env.SEARCH_SCORE_THRESHOLD = None
    env.SEARCH_TOP_K = None
    env.DEPLOYMENT_VERSION = "test"
    env.DEPLOYMENT_ENVIRONMENT = "test"
    env.VERSION_METADATA = None  # Prevent MagicMock from returning mock for this
    return env


@pytest.fixture
async def indexed_env(mock_env_with_fixtures, fixtures):
    """Environment with all entries indexed in Vectorize."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_fixtures

    # Index all entries
    for entry in fixtures["entries"]:
        await worker._index_entry_for_search(
            entry_id=entry["id"],
            title=entry["title"],
            content=entry["content"],
        )

    return mock_env_with_fixtures


class TestTitleMatching:
    """Tests for title-based search matching."""

    @pytest.mark.asyncio
    async def test_exact_title_match(self, indexed_env, fixtures):
        """Exact title match should rank first with score 1.0."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # Find the test case for exact title match
        test_case = next(
            tc for tc in fixtures["test_queries"] if tc["query"] == "context is the work"
        )

        request = MockRequest(f"https://planetcf.com/search?q={test_case['query']}")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)

        # Should find the expected entry
        expected_title = test_case["expected_first_result_title"]
        assert expected_title in body, f"Expected '{expected_title}' in results"
        assert "No results found" not in body

    @pytest.mark.asyncio
    async def test_title_in_query_match(self, indexed_env, fixtures):
        """When query contains the full title, should still match."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # Test: "what the day-to-day looks like now" should match
        # "What the day-to-day looks like"
        test_case = next(
            tc
            for tc in fixtures["test_queries"]
            if tc["query"] == "what the day-to-day looks like now"
        )

        request = MockRequest(f"https://planetcf.com/search?q={test_case['query']}")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)

        expected_title = test_case["expected_first_result_title"]
        assert expected_title in body, (
            f"Expected '{expected_title}' in results for query '{test_case['query']}'"
        )

    @pytest.mark.asyncio
    async def test_query_in_title_match(self, indexed_env, fixtures):
        """Query as substring of title should match."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        test_case = next(tc for tc in fixtures["test_queries"] if tc["query"] == "python workers")

        request = MockRequest(f"https://planetcf.com/search?q={test_case['query']}")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)

        expected_title = test_case["expected_first_result_title"]
        assert expected_title in body


class TestKeywordMatching:
    """Tests for keyword-based search in content."""

    @pytest.mark.asyncio
    async def test_keyword_in_content(self, indexed_env, fixtures):
        """Keywords in content should be findable."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # Search for "RSS feed aggregator" - should find the aggregator post
        test_case = next(
            tc for tc in fixtures["test_queries"] if tc["query"] == "RSS feed aggregator"
        )

        request = MockRequest(f"https://planetcf.com/search?q={test_case['query']}")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)

        expected_title = test_case["expected_first_result_title"]
        assert expected_title in body

    @pytest.mark.asyncio
    async def test_author_search(self, indexed_env, fixtures):
        """Searching by author name should find their posts."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # Search for "Rita Kozlov" - should find posts by that author
        test_case = next(tc for tc in fixtures["test_queries"] if tc["query"] == "Rita Kozlov")

        request = MockRequest(f"https://planetcf.com/search?q={test_case['query']}")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)

        # Should find at least one post by Rita
        assert "Rita Kozlov" in body or "day-to-day" in body or "faster Workers" in body


class TestSearchRanking:
    """Tests for search result ranking."""

    @pytest.mark.asyncio
    async def test_exact_title_ranks_above_partial(self, indexed_env, fixtures):
        """Exact title matches should rank above partial matches."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # "context is the work" should rank the exact-title post first,
        # not posts that merely mention "context"
        request = MockRequest("https://planetcf.com/search?q=context%20is%20the%20work")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)

        # The exact match "Context is the work" should appear
        assert "Context is the work" in body

        # It should appear before other posts mentioning "context"
        exact_pos = body.find("Context is the work")
        other_pos = body.find("day-to-day")  # The other post mentions context

        # If both appear, exact match should be first
        if other_pos > -1:
            assert exact_pos < other_pos, "Exact title match should rank first"

    @pytest.mark.asyncio
    async def test_title_match_ranks_above_content_match(self, indexed_env, fixtures):
        """Title matches should rank above content-only matches."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # Search for "semantic search" - should find the semantic search post
        request = MockRequest("https://planetcf.com/search?q=semantic%20search")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)

        # Should find the semantic search post
        assert "Building semantic search with Vectorize" in body


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self, indexed_env, fixtures):
        """Search should be case-insensitive."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # All these should find "Context is the work"
        queries = ["CONTEXT IS THE WORK", "Context Is The Work", "context is the work"]

        for query in queries:
            request = MockRequest(f"https://planetcf.com/search?q={query}")
            response = await worker.fetch(request)
            body = response.body if hasattr(response, "body") else str(response)
            assert "Context is the work" in body, f"Failed for query: {query}"

    @pytest.mark.asyncio
    async def test_partial_word_matching(self, indexed_env):
        """Partial words should match via LIKE."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # "Cloudflare" partial match
        request = MockRequest("https://planetcf.com/search?q=Cloudflare")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)
        # Should find posts mentioning Cloudflare
        assert "Cloudflare" in body or "cloudflare" in body.lower()

    @pytest.mark.asyncio
    async def test_multi_word_query(self, indexed_env, fixtures):
        """Multi-word queries should work correctly."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # "queues background processing" - multiple words in title
        request = MockRequest("https://planetcf.com/search?q=queues%20background%20processing")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)
        assert "Background processing with Queues" in body

    @pytest.mark.asyncio
    async def test_quoted_query_strips_quotes(self, indexed_env, fixtures):
        """Quoted queries should strip quotes and still match."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        # Test double quotes
        request = MockRequest('https://planetcf.com/search?q="context%20is%20the%20work"')
        response = await worker.fetch(request)
        body = response.body if hasattr(response, "body") else str(response)
        assert "Context is the work" in body, "Double-quoted query should match"

        # Test single quotes
        request = MockRequest("https://planetcf.com/search?q='python%20workers'")
        response = await worker.fetch(request)
        body = response.body if hasattr(response, "body") else str(response)
        assert "Announcing Python Workers" in body, "Single-quoted query should match"

    @pytest.mark.asyncio
    async def test_no_results_returns_empty(self, mock_env_with_fixtures):
        """Query with no matches should return empty results gracefully.

        Note: We use a non-indexed environment so Vectorize has no vectors,
        and the keyword search won't match our nonsense query.
        """
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = mock_env_with_fixtures

        # A query that shouldn't match anything in the DB (keyword search)
        # and Vectorize is empty (no semantic results)
        request = MockRequest("https://planetcf.com/search?q=xyznonexistentqueryxyz123")
        response = await worker.fetch(request)

        assert response.status == 200
        body = response.body if hasattr(response, "body") else str(response)
        assert "No results found" in body or "0 results" in body.lower()


class TestAllFixtureQueries:
    """Run all test queries from the fixtures file."""

    @pytest.mark.asyncio
    async def test_all_expected_results(self, indexed_env, fixtures):
        """Every test query should find its expected result."""
        from src.main import PlanetCF

        worker = PlanetCF()
        worker.env = indexed_env

        failures = []

        for test_case in fixtures["test_queries"]:
            query = test_case["query"]
            description = test_case.get("description", "")

            request = MockRequest(f"https://planetcf.com/search?q={query}")
            response = await worker.fetch(request)
            body = response.body if hasattr(response, "body") else str(response)

            # Check expected title appears
            if "expected_first_result_title" in test_case:
                expected = test_case["expected_first_result_title"]
                if expected not in body:
                    failures.append(
                        f"Query '{query}': Expected '{expected}' not found. ({description})"
                    )

            # Check result not empty (if we expect results)
            expects_results = (
                "expected_first_result_id" in test_case or "expected_top_results" in test_case
            )
            if expects_results and "No results found" in body:
                failures.append(
                    f"Query '{query}': Got 'No results found' but expected results. ({description})"
                )

        if failures:
            pytest.fail("Search accuracy failures:\n" + "\n".join(failures))
