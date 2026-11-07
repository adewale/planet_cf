"""Tests for inactive feed display behavior.

Verifies that is_active controls fetching only, not display.
Inactive feeds should remain visible in the sidebar with a visual indicator,
and their cached entries should still appear in the main content area.
"""

import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.main import Default

PROJECT_ROOT = Path(__file__).parent.parent.parent


class SqliteStatement:
    """Execute the production SQL using SQLite, not SQL-substring matching."""

    def __init__(self, connection, sql):
        self.connection = connection
        self.sql = sql
        self.values = ()

    def bind(self, *values):
        self.values = values
        return self

    async def all(self):
        rows = self.connection.execute(self.sql, self.values).fetchall()
        return SimpleNamespace(results=[dict(row) for row in rows], success=True)

    async def run(self):
        cursor = self.connection.execute(self.sql, self.values)
        return SimpleNamespace(results=[], success=True, meta={"changes": cursor.rowcount})

    async def first(self):
        row = self.connection.execute(self.sql, self.values).fetchone()
        return dict(row) if row is not None else None


class SqliteD1:
    def __init__(self, connection):
        self.connection = connection

    def prepare(self, sql):
        return SqliteStatement(self.connection, sql)


@pytest.fixture
def feed_worker(mock_env):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    for migration in sorted((PROJECT_ROOT / "migrations").glob("*.sql")):
        connection.executescript(migration.read_text())
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    for feed_id, active, name in [(1, 1, "Active"), (2, 0, "Inactive")]:
        connection.execute(
            "INSERT INTO feeds (id,url,title,site_url,is_active) VALUES (?,?,?,?,?)",
            (
                feed_id,
                f"https://{name.lower()}.example/feed",
                f"{name} fixture feed",
                f"https://{name.lower()}.example",
                active,
            ),
        )
        connection.execute(
            "INSERT INTO entries (feed_id,guid,url,title,content,published_at,first_seen) VALUES (?,?,?,?,?,?,?)",
            (
                feed_id,
                str(feed_id),
                f"https://{name.lower()}.example/entry",
                f"{name} fixture entry",
                "<p>Cached content</p>",
                now,
                now,
            ),
        )
    mock_env.DB = SqliteD1(connection)
    # Recovery is a separate opt-in scheduling behavior, covered by its own suite.
    mock_env.FEED_RECOVERY_ENABLED = "false"
    worker = Default()
    worker.env = mock_env
    try:
        yield worker, mock_env
    finally:
        connection.close()


@pytest.mark.asyncio
class TestInactiveFeedDisplayQueries:
    @pytest.mark.parametrize("theme", ["default", "planet-python", "planet-mozilla"])
    async def test_html_displays_both_active_and_inactive_cached_feeds(self, feed_worker, theme):
        worker, env = feed_worker
        env.THEME = theme
        # Rebind to invalidate the runtime wrapper's environment cache.
        worker.env = env
        page = await worker._generate_html()
        for name in ("Active", "Inactive"):
            assert f"{name} fixture feed" in page
            assert f"{name} fixture entry" in page

    async def test_feed_endpoints_include_cached_entries_from_inactive_feeds(self, feed_worker):
        worker, _ = feed_worker
        atom = ET.fromstring((await worker._serve_atom()).body)  # noqa: S314 - local generated fixture XML
        titles = {
            node.text
            for node in atom.findall(
                "{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}title"
            )
        }
        assert titles == {"Active fixture entry", "Inactive fixture entry"}
        rss = ET.fromstring((await worker._serve_rss()).body)  # noqa: S314 - local generated fixture XML
        assert {node.text for node in rss.findall("./channel/item/title")} == titles

    async def test_opml_exports_both_active_and_inactive_feeds(self, feed_worker):
        worker, _ = feed_worker
        opml = ET.fromstring((await worker._export_opml()).body)  # noqa: S314 - local generated fixture XML
        assert {node.attrib["xmlUrl"] for node in opml.findall(".//outline[@xmlUrl]")} == {
            "https://active.example/feed",
            "https://inactive.example/feed",
        }

    async def test_scheduler_only_enqueues_active_feeds_when_recovery_is_disabled(
        self, feed_worker
    ):
        worker, env = feed_worker
        await worker._run_scheduler()
        assert [message["feed_id"] for message in env.FEED_QUEUE.messages] == [1]


class TestInactiveFeedTemplates:
    """Verify templates render inactive feeds with correct CSS class."""

    def test_default_theme_has_feed_inactive_class(self):
        """Default theme template should render feed-inactive class."""
        template = (PROJECT_ROOT / "examples" / "default" / "templates" / "index.html").read_text()
        assert "feed-inactive" in template
        assert "is_inactive" in template

    def test_planet_python_has_feed_inactive_class(self):
        """Planet Python template should render feed-inactive class."""
        template = (
            PROJECT_ROOT / "examples" / "planet-python" / "templates" / "index.html"
        ).read_text()
        assert "feed-inactive" in template

    def test_planet_mozilla_has_feed_inactive_class(self):
        """Planet Mozilla template should render feed-inactive class."""
        template = (
            PROJECT_ROOT / "examples" / "planet-mozilla" / "templates" / "index.html"
        ).read_text()
        assert "feed-inactive" in template

    def test_compiled_templates_have_feed_inactive(self):
        """Compiled templates.py should contain feed-inactive for all themes."""
        templates = (PROJECT_ROOT / "src" / "templates.py").read_text()
        # Should appear at least 3 times (once per theme)
        count = templates.count("feed-inactive")
        assert count >= 3, f"Expected feed-inactive in at least 3 themes, found {count} occurrences"


class TestInactiveFeedCSS:
    """Verify all theme CSS files have .feed-inactive rule."""

    CSS_FILES = [
        "assets/static/style.css",
        "examples/default/assets/static/style.css",
        "examples/planet-cloudflare/assets/static/style.css",
        "examples/test-planet/assets/static/style.css",
        "examples/planet-python/assets/static/style.css",
        "examples/planet-mozilla/assets/static/style.css",
    ]

    def test_all_theme_css_has_feed_inactive(self):
        """Every theme CSS file must contain a .feed-inactive rule."""
        for css_path in self.CSS_FILES:
            full_path = PROJECT_ROOT / css_path
            assert full_path.exists(), f"CSS file not found: {css_path}"
            content = full_path.read_text()
            assert "feed-inactive" in content, f"{css_path} is missing .feed-inactive CSS rule"

    def test_feed_inactive_uses_opacity(self):
        """The .feed-inactive rule should use opacity for visual dimming."""
        for css_path in self.CSS_FILES:
            content = (PROJECT_ROOT / css_path).read_text()
            if "feed-inactive" in content:
                # Find the rule block
                match = re.search(r"\.feed-inactive\s*\{[^}]*\}", content)
                if match:
                    assert "opacity" in match.group(), (
                        f"{css_path}: .feed-inactive rule should use opacity"
                    )
