# tests/integration/test_contracts.py
"""Contract tests validating API response shapes for all public endpoints.

Each test validates the "contract" between the endpoint and its consumers:
- Correct status codes
- Correct Content-Type headers
- Required fields present in JSON responses
- Well-formed XML in feed responses
- Expected structural elements in HTML responses
"""

import json
import xml.etree.ElementTree as ET  # noqa: S405

import pytest

from tests.conftest import MockRequest

# =============================================================================
# /health — JSON health endpoint
# =============================================================================


@pytest.mark.asyncio
async def test_health_returns_200_json(mock_env_with_feeds):
    """GET /health returns 200 with application/json content type."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/health")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/json" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_health_json_has_service_identity(mock_env_with_feeds):
    """GET /health JSON must identify this service as 'planetcf'."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/health")
    response = await worker.fetch(request)

    data = json.loads(response.body)
    assert data.get("service") == "planetcf", (
        "Health response must contain 'service': 'planetcf' for server identity checks"
    )
    assert "status" in data, "Health response must contain 'status' field"
    assert data["status"] in ("healthy", "degraded", "unhealthy")


@pytest.mark.asyncio
async def test_health_json_has_feeds_object(mock_env_with_feeds):
    """GET /health JSON must contain a 'feeds' object with count fields."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/health")
    response = await worker.fetch(request)

    data = json.loads(response.body)
    assert "feeds" in data, "Health response must contain 'feeds' object"

    feeds = data["feeds"]
    required_keys = {"total", "healthy", "warning", "failing", "inactive"}
    missing = required_keys - set(feeds.keys())
    assert not missing, f"feeds object missing keys: {missing}"

    # All values should be integers
    for key in required_keys:
        assert isinstance(feeds[key], int), f"feeds.{key} should be an integer"


@pytest.mark.asyncio
async def test_health_json_no_cache(mock_env_with_feeds):
    """GET /health should not be cached (no Cache-Control or no-cache)."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/health")
    response = await worker.fetch(request)

    cache_control = response.headers.get("Cache-Control", "")
    # Health should either have no Cache-Control or not be publicly cached
    assert "max-age=3600" not in cache_control


# =============================================================================
# /feed.atom — Atom XML feed (aliased as /feed.atom in routes)
# =============================================================================


@pytest.mark.asyncio
async def test_atom_returns_200_with_correct_content_type(mock_env_with_entries):
    """GET /feed.atom returns 200 with application/atom+xml content type."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.atom")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/atom+xml" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_atom_is_well_formed_xml(mock_env_with_entries):
    """GET /feed.atom must return well-formed, parseable XML."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.atom")
    response = await worker.fetch(request)

    try:
        root = ET.fromstring(response.body)  # noqa: S314
    except ET.ParseError as e:
        pytest.fail(f"Atom feed is not well-formed XML: {e}")

    # Atom namespace
    ns = "http://www.w3.org/2005/Atom"
    assert root.tag == f"{{{ns}}}feed", f"Root element should be atom:feed, got {root.tag}"


@pytest.mark.asyncio
async def test_atom_contains_required_elements(mock_env_with_entries):
    """Atom feed must contain title, id, and updated elements."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.atom")
    response = await worker.fetch(request)

    ns = "http://www.w3.org/2005/Atom"
    root = ET.fromstring(response.body)  # noqa: S314

    assert root.find(f"{{{ns}}}title") is not None, "Atom feed must have <title>"
    assert root.find(f"{{{ns}}}id") is not None, "Atom feed must have <id>"
    assert root.find(f"{{{ns}}}updated") is not None, "Atom feed must have <updated>"


@pytest.mark.asyncio
async def test_atom_entries_have_required_fields(mock_env_with_entries):
    """Each Atom entry must have title, id, and link."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.atom")
    response = await worker.fetch(request)

    ns = "http://www.w3.org/2005/Atom"
    root = ET.fromstring(response.body)  # noqa: S314
    entries = root.findall(f"{{{ns}}}entry")

    assert len(entries) > 0, "Atom feed should contain at least one entry"

    for entry in entries:
        assert entry.find(f"{{{ns}}}title") is not None, "entry must have <title>"
        assert entry.find(f"{{{ns}}}id") is not None, "entry must have <id>"
        assert entry.find(f"{{{ns}}}link") is not None, "entry must have <link>"


@pytest.mark.asyncio
async def test_atom_has_cache_control(mock_env_with_entries):
    """Atom feed should include Cache-Control header."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.atom")
    response = await worker.fetch(request)

    assert "Cache-Control" in response.headers


# =============================================================================
# /feed.rss — RSS 2.0 XML feed
# =============================================================================


@pytest.mark.asyncio
async def test_rss_returns_200_with_correct_content_type(mock_env_with_entries):
    """GET /feed.rss returns 200 with application/rss+xml content type."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.rss")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/rss+xml" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_rss_is_well_formed_xml(mock_env_with_entries):
    """GET /feed.rss must return well-formed, parseable XML."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.rss")
    response = await worker.fetch(request)

    try:
        root = ET.fromstring(response.body)  # noqa: S314
    except ET.ParseError as e:
        pytest.fail(f"RSS feed is not well-formed XML: {e}")

    assert root.tag == "rss", f"Root element should be <rss>, got {root.tag}"


@pytest.mark.asyncio
async def test_rss_contains_channel_with_required_elements(mock_env_with_entries):
    """RSS feed must have a channel with title, link, and description."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.rss")
    response = await worker.fetch(request)

    root = ET.fromstring(response.body)  # noqa: S314
    channel = root.find("channel")
    assert channel is not None, "RSS feed must have <channel>"

    assert channel.find("title") is not None, "channel must have <title>"
    assert channel.find("link") is not None, "channel must have <link>"
    assert channel.find("description") is not None, "channel must have <description>"


@pytest.mark.asyncio
async def test_rss_items_have_required_fields(mock_env_with_entries):
    """Each RSS item must have title and link."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.rss")
    response = await worker.fetch(request)

    root = ET.fromstring(response.body)  # noqa: S314
    channel = root.find("channel")
    items = channel.findall("item")

    assert len(items) > 0, "RSS feed should contain at least one item"

    for item in items:
        assert item.find("title") is not None, "item must have <title>"
        assert item.find("link") is not None, "item must have <link>"


@pytest.mark.asyncio
async def test_rss_has_cache_control(mock_env_with_entries):
    """RSS feed should include Cache-Control header."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/feed.rss")
    response = await worker.fetch(request)

    assert "Cache-Control" in response.headers


# =============================================================================
# /foafroll.xml — FOAF RDF/XML
# =============================================================================


@pytest.mark.asyncio
async def test_foafroll_returns_200_with_correct_content_type(mock_env_with_feeds):
    """GET /foafroll.xml returns 200 with application/rdf+xml content type."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/foafroll.xml")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "application/rdf+xml" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_foafroll_is_well_formed_xml(mock_env_with_feeds):
    """GET /foafroll.xml must return well-formed, parseable XML."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/foafroll.xml")
    response = await worker.fetch(request)

    try:
        ET.fromstring(response.body)  # noqa: S314
    except ET.ParseError as e:
        pytest.fail(f"FOAF XML is not well-formed: {e}")


@pytest.mark.asyncio
async def test_foafroll_has_rdf_root(mock_env_with_feeds):
    """FOAF XML should have an RDF root element."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/foafroll.xml")
    response = await worker.fetch(request)

    root = ET.fromstring(response.body)  # noqa: S314
    # RDF root should be rdf:RDF
    rdf_ns = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    assert root.tag == f"{{{rdf_ns}}}RDF", f"Root should be rdf:RDF, got {root.tag}"


@pytest.mark.asyncio
async def test_foafroll_has_cache_control(mock_env_with_feeds):
    """FOAF feed should include Cache-Control header."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_feeds

    request = MockRequest("https://planetcf.com/foafroll.xml")
    response = await worker.fetch(request)

    assert "Cache-Control" in response.headers


# =============================================================================
# /titles — HTML titles-only view
# =============================================================================


@pytest.mark.asyncio
async def test_titles_returns_200_with_html_content_type(mock_env_with_entries):
    """GET /titles returns 200 with text/html content type."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/titles")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "text/html" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_titles_contains_html_structure(mock_env_with_entries):
    """GET /titles should return HTML with basic structural elements."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/titles")
    response = await worker.fetch(request)

    body = response.body
    assert "<!DOCTYPE html>" in body or "<html" in body, "Response should contain HTML"
    assert "</html>" in body, "Response should contain closing </html> tag"
    assert "<head" in body, "Response should contain <head> element"
    assert "<body" in body, "Response should contain <body> element"


@pytest.mark.asyncio
async def test_titles_contains_entry_titles(mock_env_with_entries):
    """GET /titles should contain the titles of entries from the database."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/titles")
    response = await worker.fetch(request)

    # mock_env_with_entries has entries titled "Test Entry 1" and "Test Entry 2"
    assert "Test Entry 1" in response.body
    assert "Test Entry 2" in response.body


@pytest.mark.asyncio
async def test_titles_has_cache_control(mock_env_with_entries):
    """Titles page should include Cache-Control header."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/titles")
    response = await worker.fetch(request)

    assert "Cache-Control" in response.headers


# =============================================================================
# Cross-endpoint contract: charset in Content-Type
# =============================================================================


@pytest.mark.asyncio
async def test_html_endpoints_specify_charset(mock_env_with_entries):
    """HTML endpoints should specify charset=utf-8 in Content-Type."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    for path in ("/", "/titles"):
        request = MockRequest(f"https://planetcf.com{path}")
        response = await worker.fetch(request)

        content_type = response.headers.get("Content-Type", "")
        assert "charset=utf-8" in content_type, (
            f"{path} Content-Type should include charset=utf-8, got: {content_type}"
        )


@pytest.mark.asyncio
async def test_feed_endpoints_specify_charset(mock_env_with_entries):
    """Feed endpoints should specify charset=utf-8 in Content-Type."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    feed_paths = [
        ("/feed.atom", "application/atom+xml"),
        ("/feed.rss", "application/rss+xml"),
    ]

    for path, expected_type in feed_paths:
        request = MockRequest(f"https://planetcf.com{path}")
        response = await worker.fetch(request)

        content_type = response.headers.get("Content-Type", "")
        assert expected_type in content_type, (
            f"{path} should have {expected_type}, got: {content_type}"
        )
        assert "charset=utf-8" in content_type, (
            f"{path} Content-Type should include charset=utf-8, got: {content_type}"
        )


# =============================================================================
# /search — HTML search results
# =============================================================================


@pytest.mark.asyncio
async def test_search_returns_200_with_html_content_type(mock_env_with_entries):
    """GET /search?q=test returns 200 with text/html content type."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=test")
    response = await worker.fetch(request)

    assert response.status == 200
    assert "text/html" in response.headers.get("Content-Type", "")


@pytest.mark.asyncio
async def test_search_html_has_basic_structure(mock_env_with_entries):
    """GET /search?q=test should return HTML with DOCTYPE, html, head, body tags."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=test")
    response = await worker.fetch(request)

    body = response.body
    assert "<!DOCTYPE html>" in body or "<html" in body, "Response should contain HTML"
    assert "</html>" in body, "Response should contain closing </html> tag"
    assert "<head" in body, "Response should contain <head> element"
    assert "<body" in body, "Response should contain <body> element"


@pytest.mark.asyncio
async def test_search_no_cache(mock_env_with_entries):
    """GET /search should not be cached (max-age=0 or no-cache)."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=test")
    response = await worker.fetch(request)

    cache_control = response.headers.get("Cache-Control", "")
    assert "no-cache" in cache_control or "max-age=0" in cache_control, (
        f"Search should not be cached, got Cache-Control: {cache_control}"
    )


@pytest.mark.asyncio
async def test_search_short_query_returns_200_with_error(mock_env_with_entries):
    """GET /search?q=a returns 200 with an error message (query too short)."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=a")
    response = await worker.fetch(request)

    assert response.status == 200
    # Should contain an error message in the HTML body
    assert "error" in response.body.lower() or "at least" in response.body.lower(), (
        "Short query should produce an error message in the response"
    )


@pytest.mark.asyncio
async def test_search_short_query_error_contains_message(mock_env_with_entries):
    """Short query error response should tell the user about the minimum length."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=a")
    response = await worker.fetch(request)

    assert "at least 2 characters" in response.body, (
        "Error response should contain 'at least 2 characters' guidance"
    )


@pytest.mark.asyncio
async def test_search_missing_q_param_returns_200(mock_env_with_entries):
    """GET /search (no q param) returns 200 with an error or empty state."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search")
    response = await worker.fetch(request)

    assert response.status == 200


@pytest.mark.asyncio
async def test_search_empty_q_returns_200(mock_env_with_entries):
    """GET /search?q= (empty query) returns 200 with an error or empty state."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=")
    response = await worker.fetch(request)

    assert response.status == 200


@pytest.mark.asyncio
async def test_search_specifies_charset(mock_env_with_entries):
    """Search Content-Type should include charset=utf-8."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=test")
    response = await worker.fetch(request)

    content_type = response.headers.get("Content-Type", "")
    assert "charset=utf-8" in content_type, (
        f"/search Content-Type should include charset=utf-8, got: {content_type}"
    )


@pytest.mark.asyncio
async def test_search_xss_in_query_not_reflected_raw(mock_env_with_entries):
    """GET /search?q=<script>alert(1)</script> must not reflect raw <script> tag."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=<script>alert(1)</script>")
    response = await worker.fetch(request)

    assert response.status == 200
    # The raw <script>alert(1)</script> must NOT appear in the response body.
    # It should be escaped (e.g., &lt;script&gt;) by the template engine.
    assert "<script>alert(1)</script>" not in response.body, (
        "XSS payload must not be reflected raw in the response — "
        "it should be HTML-escaped by the template engine"
    )


@pytest.mark.asyncio
async def test_search_results_contain_entry_data(mock_env_with_entries):
    """GET /search?q=test should find entries with 'Test' in their title."""
    from src.main import PlanetCF

    worker = PlanetCF()
    worker.env = mock_env_with_entries

    request = MockRequest("https://planetcf.com/search?q=test")
    response = await worker.fetch(request)

    assert response.status == 200
    # mock_env_with_entries has entries titled "Test Entry 1" and "Test Entry 2"
    assert "Test Entry" in response.body, (
        "Search for 'test' should find entries with 'Test' in the title"
    )
