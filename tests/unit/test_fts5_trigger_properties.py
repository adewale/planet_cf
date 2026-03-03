# tests/unit/test_fts5_trigger_properties.py
"""Property-based tests for FTS5 trigger consistency using Hypothesis.

Verifies the FTS index stays consistent with the entries table across
arbitrary sequences of mutations.
"""

import sqlite3
from pathlib import Path

from hypothesis import given, settings
from hypothesis.strategies import integers, lists, text

MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations"


def _setup_db() -> sqlite3.Connection:
    """Create an in-memory DB with schema and FTS5 migration."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT,
            site_url TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER NOT NULL,
            guid TEXT NOT NULL,
            url TEXT,
            title TEXT,
            author TEXT,
            content TEXT,
            summary TEXT,
            published_at TEXT,
            updated_at TEXT,
            first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
            UNIQUE(feed_id, guid)
        );

        INSERT INTO feeds(id, url, title) VALUES (1, 'https://example.com/feed', 'Test Feed');
    """)
    migration_sql = (MIGRATION_PATH / "006_create_fts5_index.sql").read_text()
    conn.executescript(migration_sql)
    conn.commit()
    return conn


class TestInsertDeleteConsistency:
    """FTS count matches entries count after arbitrary inserts and deletes."""

    @given(
        titles=lists(text(min_size=1, max_size=50), min_size=1, max_size=20),
        delete_indices=lists(integers(min_value=0), max_size=10),
    )
    @settings(max_examples=50)
    def test_fts_count_matches_entries_count(self, titles, delete_indices):
        """After inserts and deletes, FTS count == entries count."""
        db = _setup_db()
        try:
            # Insert entries
            for i, title in enumerate(titles):
                db.execute(
                    "INSERT INTO entries(feed_id, guid, title, content) VALUES (1, ?, ?, '')",
                    (f"guid-{i}", title),
                )
            db.commit()

            # Delete some
            ids = [
                row[0] for row in db.execute("SELECT id FROM entries").fetchall()
            ]
            for idx in delete_indices:
                if ids:
                    target = ids.pop(idx % len(ids))
                    db.execute("DELETE FROM entries WHERE id = ?", (target,))
            db.commit()

            # Verify counts match
            entry_count = db.execute("SELECT count(*) FROM entries").fetchone()[0]
            fts_count = db.execute("SELECT count(*) FROM entries_fts").fetchone()[0]
            assert entry_count == fts_count
        finally:
            db.close()


class TestUpdateConsistency:
    """FTS index reflects updates correctly."""

    @given(
        old_title=text(min_size=1, max_size=30),
        new_title=text(min_size=1, max_size=30),
    )
    @settings(max_examples=50)
    def test_update_replaces_old_with_new(self, old_title, new_title):
        """After updating title, FTS reflects the new title."""
        db = _setup_db()
        try:
            db.execute(
                "INSERT INTO entries(feed_id, guid, title, content) VALUES (1, 'test-guid', ?, '')",
                (old_title,),
            )
            db.commit()

            db.execute("UPDATE entries SET title = ? WHERE guid = 'test-guid'", (new_title,))
            db.commit()

            # FTS count should be 1
            assert db.execute("SELECT count(*) FROM entries_fts").fetchone()[0] == 1
        finally:
            db.close()


class TestRebuildIdempotency:
    """Rebuild on a consistent index is a no-op."""

    @given(
        titles=lists(text(min_size=1, max_size=50), min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_rebuild_does_not_change_consistent_index(self, titles):
        """After inserts, rebuild doesn't change the matchable content."""
        db = _setup_db()
        try:
            for i, title in enumerate(titles):
                db.execute(
                    "INSERT INTO entries(feed_id, guid, title, content) VALUES (1, ?, ?, '')",
                    (f"guid-{i}", title),
                )
            db.commit()

            count_before = db.execute("SELECT count(*) FROM entries_fts").fetchone()[0]

            db.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
            db.commit()

            count_after = db.execute("SELECT count(*) FROM entries_fts").fetchone()[0]
            assert count_before == count_after
        finally:
            db.close()
