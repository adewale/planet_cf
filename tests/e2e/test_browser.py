# tests/e2e/test_browser.py
"""Browser-based E2E tests using agent-browser.

These tests use a real headless Chrome browser to verify JavaScript execution,
visual rendering, and user interaction on public routes. No admin actions.

Requires:
    - agent-browser installed: npm install -g agent-browser && agent-browser install
    - Test planet running or deployed

Run locally:
    E2E_BASE_URL=https://test-planet.adewale-883.workers.dev \
        uv run pytest tests/e2e/test_browser.py -v
"""

import contextlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

E2E_BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8787")
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"

# ============================================================================
# Helpers
# ============================================================================

_SESSION = "planetcf-test"


def _has_agent_browser() -> bool:
    return shutil.which("agent-browser") is not None


def ab(*args: str, timeout: int = 30) -> str:
    """Run an agent-browser command and return stdout.

    Raises RuntimeError on non-zero exit code.
    """
    result = subprocess.run(
        ["agent-browser", "--session", _SESSION, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"agent-browser {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def ab_eval(js: str) -> str:
    """Evaluate JavaScript in the browser and return the result."""
    return ab("eval", js)


def ab_bool(js: str) -> bool:
    """Evaluate JavaScript that returns a boolean."""
    return ab_eval(js) == "true"


def ab_int(css_selector: str) -> int:
    """Get the count of elements matching a CSS selector."""
    return int(ab("get", "count", css_selector))


# ============================================================================
# Skip conditions
# ============================================================================

requires_browser = pytest.mark.skipif(
    not _has_agent_browser(),
    reason="agent-browser not installed (npm install -g agent-browser && agent-browser install)",
)


def _server_reachable() -> bool:
    """Quick check: can we reach the test planet?"""
    try:
        import httpx

        resp = httpx.get(f"{E2E_BASE_URL}/health", timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


requires_server_for_browser = pytest.mark.skipif(
    not _server_reachable(),
    reason=f"Test planet not reachable at {E2E_BASE_URL}",
)

pytestmark = [requires_browser, requires_server_for_browser]


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="module", autouse=True)
def browser_session():
    """Start a browser session for the module, close it after."""
    ab("goto", f"{E2E_BASE_URL}/")
    yield
    with contextlib.suppress(Exception):
        subprocess.run(
            ["agent-browser", "session", "close", _SESSION],
            capture_output=True,
            timeout=10,
        )


@pytest.fixture()
def homepage():
    """Navigate to the homepage before a test."""
    ab("set", "viewport", "1280", "800")
    ab("goto", f"{E2E_BASE_URL}/")


# ============================================================================
# #2 Keyboard Navigation
# ============================================================================


class TestKeyboardNavigation:
    """Verify keyboard-nav.js works in a real browser."""

    def test_j_selects_first_article(self, homepage):
        """Pressing j selects the first article."""
        ab("press", "j")
        assert ab_bool("document.querySelector('article.selected') !== null")
        assert (
            ab_eval(
                "Array.from(document.querySelectorAll('article'))"
                ".findIndex(a => a.classList.contains('selected'))"
            )
            == "0"
        )

    def test_j_advances_selection(self, homepage):
        """Pressing j twice advances to the second article."""
        ab("press", "j")
        ab("press", "j")
        assert (
            ab_eval(
                "Array.from(document.querySelectorAll('article'))"
                ".findIndex(a => a.classList.contains('selected'))"
            )
            == "1"
        )

    def test_k_moves_back(self, homepage):
        """Pressing k after j moves selection back."""
        ab("press", "j")
        ab("press", "j")
        ab("press", "k")
        assert (
            ab_eval(
                "Array.from(document.querySelectorAll('article'))"
                ".findIndex(a => a.classList.contains('selected'))"
            )
            == "0"
        )

    def test_k_at_first_article_stays(self, homepage):
        """Pressing k at the first article doesn't go negative."""
        ab("press", "j")  # select first (index 0)
        ab("press", "k")  # try to go before first
        assert (
            ab_eval(
                "Array.from(document.querySelectorAll('article'))"
                ".findIndex(a => a.classList.contains('selected'))"
            )
            == "0"
        )

    def test_question_mark_opens_help(self, homepage):
        """Pressing ? opens the keyboard shortcuts panel."""
        ab("press", "?")
        assert ab_bool("!document.getElementById('shortcuts-panel').classList.contains('hidden')")

    def test_escape_closes_help(self, homepage):
        """Pressing Escape closes the help panel."""
        ab("press", "?")
        assert ab_bool("!document.getElementById('shortcuts-panel').classList.contains('hidden')")
        ab("press", "Escape")
        assert ab_bool("document.getElementById('shortcuts-panel').classList.contains('hidden')")

    def test_only_one_article_selected(self, homepage):
        """Only one article has the .selected class at a time."""
        ab("press", "j")
        ab("press", "j")
        ab("press", "j")
        assert ab_eval("document.querySelectorAll('article.selected').length") == "1"


# ============================================================================
# #3 Feed Entry Rendering
# ============================================================================


class TestFeedEntryRendering:
    """Verify feed entries render correctly with titles, authors, and links."""

    def test_articles_present(self, homepage):
        """Homepage has at least one article element."""
        count = ab_int("article")
        assert count > 0, "No articles found on homepage"

    def test_article_has_title_link(self, homepage):
        """Each article has a title inside an <h3> with a link."""
        title = ab_eval("document.querySelector('article h3 a')?.textContent?.trim()")
        assert title and title != "null" and title != '""', f"First article title is empty: {title}"

    def test_article_has_author(self, homepage):
        """Each article has an author in the .meta section."""
        author = ab_eval("document.querySelector('article .author')?.textContent?.trim()")
        assert author and author != "null", f"First article author is empty: {author}"

    def test_article_title_links_are_valid(self, homepage):
        """Article title links point to real URLs (not '#')."""
        href = ab_eval("document.querySelector('article h3 a')?.href")
        assert href and href != "null" and href != "#", f"First article link is invalid: {href}"
        assert href.startswith('"http'), f"Link is not an HTTP URL: {href}"

    def test_sidebar_has_subscriptions(self, homepage):
        """Sidebar displays a Subscriptions heading."""
        text = ab_eval("document.querySelector('aside.sidebar h2')?.textContent?.trim()")
        assert "Subscriptions" in text

    def test_sidebar_has_feeds(self, homepage):
        """Sidebar lists at least one feed."""
        count = ab_int(".feeds li")
        assert count > 0, "No feeds in sidebar"

    def test_date_sections_present(self, homepage):
        """Entries are grouped under date headings."""
        count = ab_int("section.day")
        assert count > 0, "No date sections found"

    def test_footer_has_feed_links(self, homepage):
        """Footer contains links to Atom, RSS, and OPML."""
        footer = ab_eval("document.querySelector('footer')?.textContent")
        assert "Atom" in footer
        assert "RSS" in footer
        assert "OPML" in footer


# ============================================================================
# #4 Search Form Validation
# ============================================================================


class TestSearchFormValidation:
    """Verify the search form shows validation messages in the browser."""

    def test_search_form_exists_on_homepage(self, homepage):
        """Homepage has a search form with input and button."""
        assert ab_int(".search-form") > 0, "No search form on homepage"
        assert ab_int(".search-form input[type='search']") > 0

    def test_empty_query_shows_validation_message(self):
        """Navigating to /search with no query shows a validation message."""
        ab("goto", f"{E2E_BASE_URL}/search")
        assert ab_bool("document.querySelector('main')?.textContent?.includes('2 characters')")

    def test_short_query_shows_validation_message(self):
        """Search with a single character shows a validation message."""
        ab("goto", f"{E2E_BASE_URL}/search?q=a")
        assert ab_bool("document.querySelector('main')?.textContent?.includes('2 characters')")

    def test_valid_query_does_not_show_validation_error(self):
        """A valid search query does not show the validation message."""
        ab("goto", f"{E2E_BASE_URL}/search?q=cloudflare")
        has_error = ab_bool("document.querySelector('main')?.textContent?.includes('2 characters')")
        assert not has_error, "Validation error shown for valid query"


# ============================================================================
# #5 Visual Regression Screenshots
# ============================================================================


class TestVisualScreenshots:
    """Capture screenshots at key viewports for visual regression.

    These tests capture screenshots and save them as artifacts. They do NOT
    fail on visual differences — this is advisory, not blocking. Review
    screenshots in CI artifacts after each run.
    """

    VIEWPORTS = {
        "desktop": (1280, 800),
        "tablet": (768, 1024),
        "mobile": (375, 812),
    }

    @pytest.fixture(autouse=True)
    def _ensure_screenshot_dir(self):
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    @pytest.mark.parametrize("name,size", VIEWPORTS.items())
    def test_capture_homepage(self, name, size):
        """Capture homepage screenshot at each viewport size."""
        w, h = size
        ab("set", "viewport", str(w), str(h))
        ab("goto", f"{E2E_BASE_URL}/")
        path = str(SCREENSHOT_DIR / f"homepage_{name}_{w}x{h}.png")
        ab("screenshot", path)
        assert Path(path).exists(), f"Screenshot not created: {path}"

    def test_capture_search_page(self):
        """Capture search results page screenshot."""
        ab("set", "viewport", "1280", "800")
        ab("goto", f"{E2E_BASE_URL}/search?q=cloudflare")
        path = str(SCREENSHOT_DIR / "search_results_1280x800.png")
        ab("screenshot", path)
        assert Path(path).exists()

    def test_capture_titles_page(self):
        """Capture titles-only page screenshot."""
        ab("set", "viewport", "1280", "800")
        ab("goto", f"{E2E_BASE_URL}/titles")
        path = str(SCREENSHOT_DIR / "titles_1280x800.png")
        ab("screenshot", path)
        assert Path(path).exists()


# ============================================================================
# #7 Responsive Layout
# ============================================================================


class TestResponsiveLayout:
    """Verify layout adapts correctly across viewport sizes."""

    def test_desktop_sidebar_visible(self):
        """At desktop width, sidebar is visible alongside main content."""
        ab("set", "viewport", "1280", "800")
        ab("goto", f"{E2E_BASE_URL}/")
        assert ab_bool(
            "getComputedStyle(document.querySelector('aside.sidebar')).display !== 'none'"
        )

    def test_desktop_articles_render(self):
        """At desktop width, articles render."""
        ab("set", "viewport", "1280", "800")
        ab("goto", f"{E2E_BASE_URL}/")
        assert ab_int("article") > 0

    def test_mobile_articles_render(self):
        """At mobile width, articles still render."""
        ab("set", "viewport", "375", "812")
        ab("goto", f"{E2E_BASE_URL}/")
        assert ab_int("article") > 0

    def test_mobile_content_not_clipped(self):
        """At mobile width, main content is not overflowing the viewport."""
        ab("set", "viewport", "375", "812")
        ab("goto", f"{E2E_BASE_URL}/")
        # Check that the body doesn't have horizontal overflow
        assert ab_bool("document.body.scrollWidth <= window.innerWidth + 1")

    def test_tablet_articles_render(self):
        """At tablet width, articles still render."""
        ab("set", "viewport", "768", "1024")
        ab("goto", f"{E2E_BASE_URL}/")
        assert ab_int("article") > 0

    def test_titles_page_responsive(self):
        """Titles page renders at mobile width without errors."""
        ab("set", "viewport", "375", "812")
        ab("goto", f"{E2E_BASE_URL}/titles")
        # Titles page should have some content
        assert ab_bool("document.querySelector('main')?.textContent?.trim()?.length > 0")
