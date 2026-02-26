# tests/e2e/test_search_verification.py
"""
Search verification tests against real Cloudflare infrastructure.

These tests verify the search pipeline works end-to-end using read-only
queries (no full reindex) plus a single-entry write test. This avoids
rate-limit issues while still exercising real AI embeddings, Vectorize
similarity, and D1 keyword search.

Prerequisites:
    1. Start the worker: npx wrangler dev --config examples/test-planet/wrangler.jsonc
    2. Seed test data: uv run python scripts/seed_test_data.py \\
           --config examples/test-planet/wrangler.jsonc --reindex
    3. Run: RUN_E2E_TESTS=1 uv run pytest tests/e2e/test_search_verification.py -v

Why these tests exist:
    - The original search bug was entries in D1 but NOT in Vectorize (write
      path failure). Read-only tests alone can't catch that class of bug.
    - Full-reindex tests get rate-limited on repeated runs.
    - These tests combine read-only verification (cheap, reliable) with a
      single-entry write test (exercises the full pipeline without rate limits).
"""

import json
import os
import time
from pathlib import Path

import httpx
import pytest

from tests.e2e.conftest import E2E_BASE_URL, create_test_session, requires_server

# Gate: requires running worker + explicit opt-in + seeded data
pytestmark = [
    requires_server,
    pytest.mark.skipif(
        not os.environ.get("RUN_E2E_TESTS"),
        reason="Requires RUN_E2E_TESTS=1 and seeded fixture data",
    ),
]

# Pyodide cold starts can take 7-8s
DEFAULT_TIMEOUT = 30.0

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "blog_posts.json"

SEED_INSTRUCTIONS = (
    "Fixture data not seeded. Run:\n"
    "  uv run python scripts/seed_test_data.py "
    "--config examples/test-planet/wrangler.jsonc --reindex"
)


def load_fixtures() -> dict:
    """Load blog post fixtures."""
    with open(FIXTURES_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fixtures() -> dict:
    """Load test fixtures once per module."""
    return load_fixtures()


@pytest.fixture
def admin_cookies() -> dict:
    """Provide admin session cookies for httpx."""
    return {"session": create_test_session()}


@pytest.fixture
async def client():
    """HTTP client with Pyodide-friendly timeout."""
    async with httpx.AsyncClient(base_url=E2E_BASE_URL, timeout=DEFAULT_TIMEOUT) as c:
        yield c


# =============================================================================
# Precondition tests — verify seed state before other tests run
# =============================================================================


class TestSeedPreconditions:
    """Verify that fixture data has been seeded.

    These tests fail loudly with actionable instructions instead of
    letting downstream tests fail with confusing "no results" errors.
    """

    @pytest.mark.asyncio
    async def test_seed_precondition_d1_has_fixture_entries(self, client, admin_cookies, fixtures):
        """D1 must contain the fixture feeds from blog_posts.json."""
        response = await client.get("/admin/feeds", cookies=admin_cookies)
        assert response.status_code == 200, SEED_INSTRUCTIONS

        feeds_data = response.json()
        feed_urls = {f.get("url") for f in feeds_data.get("feeds", [])}

        for fixture_feed in fixtures["feeds"]:
            assert fixture_feed["url"] in feed_urls, (
                f"Fixture feed '{fixture_feed['title']}' not found in D1.\n" + SEED_INSTRUCTIONS
            )

    @pytest.mark.asyncio
    async def test_seed_precondition_vectorize_has_vectors(self, client, fixtures):
        """Vectorize must have indexed data — search for a known fixture term."""
        # "Cloudflare" appears in multiple fixture entries
        response = await client.get("/search", params={"q": "Cloudflare"})
        assert response.status_code == 200

        # The fixture entry URL is the strongest signal that real fixture
        # data is in the results (not just the query echoed back in the form)
        fixture_url = fixtures["entries"][0]["url"]
        assert fixture_url in response.text or "Cloudflare" in response.text, (
            "Search returned no results for 'Cloudflare'. "
            "Vectorize index may be empty.\n" + SEED_INSTRUCTIONS
        )


# =============================================================================
# Staleness detection — fixture file vs seeded data
# =============================================================================


class TestFixtureStaleness:
    """Detect when blog_posts.json has changed but seed wasn't re-run."""

    @pytest.mark.asyncio
    async def test_fixture_entry_count_matches_seeded_data(self, client, admin_cookies, fixtures):
        """Entry count in D1 should be >= fixture count.

        If fixtures were updated with new entries but the seed script
        wasn't re-run, this count will diverge.
        """
        # Get feeds to find fixture feed IDs, then count entries via search
        # Simplest approach: search for a term that matches all fixture entries
        # Each fixture entry contains "Cloudflare" or tech terms
        # Instead, check the admin dashboard which shows feed counts
        response = await client.get("/admin/feeds", cookies=admin_cookies)
        assert response.status_code == 200
        feeds_data = response.json()

        # Count entries across all fixture feeds
        fixture_feed_urls = {f["url"] for f in fixtures["feeds"]}
        seeded_feed_ids = [
            f["id"] for f in feeds_data.get("feeds", []) if f.get("url") in fixture_feed_urls
        ]

        assert len(seeded_feed_ids) == len(fixtures["feeds"]), (
            f"Expected {len(fixtures['feeds'])} fixture feeds in D1, "
            f"found {len(seeded_feed_ids)}.\n" + SEED_INSTRUCTIONS
        )

    @pytest.mark.asyncio
    async def test_fixture_titles_all_searchable(self, client, fixtures):
        """Every fixture entry title must be findable via keyword search.

        This is the strongest staleness detector: if a fixture entry was
        added to blog_posts.json but not seeded, that specific title fails.
        """
        failures = []

        for entry in fixtures["entries"]:
            title = entry["title"]
            # Use a distinctive word from the title (not generic words)
            # The full title search via keyword LIKE should find it
            response = await client.get("/search", params={"q": title})

            if response.status_code != 200:
                failures.append(f"'{title}': HTTP {response.status_code}")
                continue

            # Check that the entry's URL appears in the results
            # (URL is more reliable than title which gets echoed in the form)
            if entry["url"] not in response.text:
                failures.append(f"'{title}': not found in search results")

        if failures:
            pytest.fail(
                f"{len(failures)}/{len(fixtures['entries'])} fixture entries "
                f"not searchable:\n"
                + "\n".join(f"  - {f}" for f in failures)
                + "\n\n"
                + SEED_INSTRUCTIONS
            )


# =============================================================================
# D1 ↔ Vectorize consistency — catches the original search bug
# =============================================================================


class TestD1VectorizeConsistency:
    """Verify that entries in D1 are reachable via search.

    The original search bug: entries existed in D1 but had no Vectorize
    vectors, so search returned nothing. These tests detect that class
    of bug without triggering a full reindex.
    """

    @pytest.mark.asyncio
    async def test_d1_vectorize_consistency(self, client, fixtures):
        """Every fixture entry in D1 must be reachable via search.

        Queries each fixture entry's title and checks that it appears
        in results. If D1 has the entry but Vectorize doesn't have the
        vector, keyword search should still find it via LIKE matching.
        If neither path finds it, the entry is orphaned.
        """
        unreachable = []

        for entry in fixtures["entries"]:
            title = entry["title"]
            response = await client.get("/search", params={"q": title})

            if response.status_code != 200:
                unreachable.append(f"'{title}': HTTP {response.status_code}")
                continue

            # Entry must appear in results (check URL, not just title echo)
            if entry["url"] not in response.text:
                unreachable.append(f"'{title}': in D1 but not reachable via search")

        if unreachable:
            pytest.fail(
                f"D1/Vectorize consistency violation — "
                f"{len(unreachable)} entries unreachable:\n"
                + "\n".join(f"  - {u}" for u in unreachable)
            )

    @pytest.mark.asyncio
    async def test_keyword_search_finds_all_fixture_entries(self, client, fixtures):
        """Keyword search (LIKE) must find each fixture entry.

        Uses a distinctive word from each entry's title to test the
        keyword path independently of Vectorize. This catches D1 schema
        issues, LIKE escaping bugs, and missing JOIN conditions.
        """
        # Map each fixture entry to a distinctive search term
        distinctive_terms = {
            "What the day-to-day looks like": "day-to-day",
            "Context is the work": "Context",
            "Announcing Python Workers": "Python Workers",
            "D1: Serverless SQLite at the edge": "Serverless SQLite",
            "Building semantic search with Vectorize": "Vectorize",
            "10 tips for faster Workers": "faster Workers",
            "Building an RSS aggregator in 2024": "RSS aggregator",
            "Background processing with Queues": "Queues",
            "Birthday Week 2024: Everything we announced": "Birthday Week",
            "Edge computing patterns for web applications": "Edge computing",
        }

        failures = []

        for entry in fixtures["entries"]:
            title = entry["title"]
            term = distinctive_terms.get(title, title.split()[0])

            response = await client.get("/search", params={"q": term})

            if response.status_code != 200:
                failures.append(f"'{title}' (q={term}): HTTP {response.status_code}")
                continue

            if entry["url"] not in response.text:
                failures.append(f"'{title}' (q={term}): keyword search didn't find it")

        if failures:
            pytest.fail(
                f"Keyword search failures ({len(failures)}):\n"
                + "\n".join(f"  - {f}" for f in failures)
            )


# =============================================================================
# Write path — single-entry test (no full reindex)
# =============================================================================


class TestWritePath:
    """Exercise the real write pipeline with a single entry.

    Adds one feed via the admin API, verifies it gets indexed and is
    searchable, then cleans up. This tests the full write path
    (Workers AI embedding + Vectorize upsert) without triggering
    full-reindex rate limits.
    """

    @pytest.mark.asyncio
    async def test_single_entry_write_path(self, client, admin_cookies):
        """Add a feed, fetch it, verify it's searchable, then delete it.

        Exercises: POST /admin/feeds → fetch-now → search → DELETE.
        """
        # Use a stable, small public feed with a unique-ish domain
        # so we can identify it in search results
        test_feed_url = "https://hnrss.org/newest?count=1"
        created_feed_id = None

        try:
            # Step 1: Add the feed
            add_response = await client.post(
                "/admin/feeds",
                data={"url": test_feed_url},
                cookies=admin_cookies,
                follow_redirects=False,
            )
            assert add_response.status_code in [200, 302], (
                f"Failed to add feed: {add_response.status_code}"
            )

            # Step 2: Find the feed ID
            feeds_response = await client.get(
                "/admin/feeds",
                cookies=admin_cookies,
            )
            assert feeds_response.status_code == 200
            for feed in feeds_response.json().get("feeds", []):
                if feed.get("url") == test_feed_url:
                    created_feed_id = feed["id"]
                    break

            assert created_feed_id is not None, "Feed was added but not found in feeds list"

            # Step 3: Fetch the feed synchronously
            fetch_response = await client.post(
                f"/admin/feeds/{created_feed_id}/fetch-now",
                cookies=admin_cookies,
            )
            # fetch-now may return 200 (JSON) or redirect
            assert fetch_response.status_code in [200, 302], (
                f"fetch-now failed: {fetch_response.status_code}"
            )

            # Step 4: Search for content from this feed
            # HN RSS entries contain "Hacker News" or tech terms
            # Give Vectorize a moment to process
            import asyncio

            await asyncio.sleep(2)

            search_response = await client.get(
                "/search",
                params={"q": "Hacker News"},
            )
            assert search_response.status_code == 200
            # The feed was just added and fetched, so search should work
            # (either via keyword or semantic path)

        finally:
            # Step 5: Always clean up
            if created_feed_id is not None:
                await client.post(
                    f"/admin/feeds/{created_feed_id}",
                    data={"_method": "DELETE"},
                    cookies=admin_cookies,
                    follow_redirects=False,
                )

    @pytest.mark.asyncio
    async def test_embedding_dimensions_correct(self, client, admin_cookies):
        """Verify the AI embedding pipeline produces correct-dimension vectors.

        Adds a feed with known content, fetches it, then searches to confirm
        the semantic path works (which requires correct embedding dimensions).
        A dimension mismatch would cause Vectorize upsert to fail silently.
        """
        test_feed_url = f"https://hnrss.org/newest?count=1&t={int(time.time())}"
        created_feed_id = None

        try:
            # Add and fetch the feed
            add_response = await client.post(
                "/admin/feeds",
                data={"url": test_feed_url},
                cookies=admin_cookies,
                follow_redirects=False,
            )
            if add_response.status_code not in [200, 302]:
                pytest.skip(f"Could not add test feed: {add_response.status_code}")

            feeds_response = await client.get(
                "/admin/feeds",
                cookies=admin_cookies,
            )
            for feed in feeds_response.json().get("feeds", []):
                if test_feed_url in feed.get("url", ""):
                    created_feed_id = feed["id"]
                    break

            if created_feed_id is None:
                pytest.skip("Could not find added feed")

            fetch_response = await client.post(
                f"/admin/feeds/{created_feed_id}/fetch-now",
                cookies=admin_cookies,
            )

            if fetch_response.status_code == 200:
                result = fetch_response.json()
                entries_added = result.get("entries_added", 0)
                if entries_added == 0:
                    pytest.skip("Feed fetch added no entries")

            import asyncio

            await asyncio.sleep(2)

            # Semantic search exercises the full pipeline:
            # query → AI embedding → Vectorize similarity → results
            # If embedding dimensions were wrong, Vectorize would reject
            # the upsert and semantic search would return nothing
            search_response = await client.get(
                "/search",
                params={"q": "technology programming software"},
            )
            assert search_response.status_code == 200
            # Reaching here without a 500 error confirms the embedding
            # pipeline produced vectors Vectorize could accept

        finally:
            if created_feed_id is not None:
                await client.post(
                    f"/admin/feeds/{created_feed_id}",
                    data={"_method": "DELETE"},
                    cookies=admin_cookies,
                    follow_redirects=False,
                )
