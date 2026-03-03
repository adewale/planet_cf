# tests/unit/test_fts5_migration.py
"""Tests for FTS5 migration (006_create_fts5_index.sql).

Verifies the migration SQL executes correctly against a real SQLite database.
Tests triggers, UPSERT interaction, rebuild, NULL handling, cascade DELETE,
and phrase search tokenization.
"""

import sqlite3
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations"


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create the entries and feeds tables matching the production schema."""
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
    """)


def _run_migration(conn: sqlite3.Connection) -> None:
    """Run the FTS5 migration SQL."""
    migration_sql = (MIGRATION_PATH / "006_create_fts5_index.sql").read_text()
    conn.executescript(migration_sql)


def _insert_feed(conn: sqlite3.Connection, feed_id: int = 1) -> None:
    """Insert a test feed."""
    conn.execute(
        "INSERT OR IGNORE INTO feeds(id, url, title) VALUES (?, ?, ?)",
        (feed_id, f"https://example.com/feed{feed_id}", f"Feed {feed_id}"),
    )


def _insert_entry(
    conn: sqlite3.Connection,
    entry_id: int,
    feed_id: int = 1,
    guid: str | None = None,
    title: str = "Test Title",
    content: str = "Test content",
) -> None:
    """Insert a test entry."""
    conn.execute(
        "INSERT INTO entries(id, feed_id, guid, title, content) VALUES (?, ?, ?, ?, ?)",
        (entry_id, feed_id, guid or f"guid-{entry_id}", title, content),
    )


def _fts_match_rowids(conn: sqlite3.Connection, match_expr: str) -> list[int]:
    """Return rowids matching an FTS5 MATCH expression."""
    rows = conn.execute(
        "SELECT rowid FROM entries_fts WHERE entries_fts MATCH ?", (match_expr,)
    ).fetchall()
    return [r[0] for r in rows]


def _fts_count(conn: sqlite3.Connection) -> int:
    """Return the number of rows in the FTS index."""
    return conn.execute("SELECT count(*) FROM entries_fts").fetchone()[0]


@pytest.fixture
def db():
    """In-memory SQLite database with schema and FTS5 migration applied."""
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    _insert_feed(conn)
    _run_migration(conn)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def db_no_migration():
    """In-memory SQLite database with schema but NO FTS5 migration."""
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    _insert_feed(conn)
    conn.commit()
    yield conn
    conn.close()


class TestBasicMigration:
    """Tests for the migration itself."""

    def test_creates_fts5_table(self, db):
        """Migration creates the entries_fts virtual table."""
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries_fts'"
        ).fetchall()
        assert len(tables) == 1
        assert tables[0][0] == "entries_fts"

    def test_backfill_populates_fts(self, db_no_migration):
        """Backfill indexes all existing entries."""
        conn = db_no_migration
        _insert_entry(conn, 1, title="Python Workers", content="Serverless Python")
        _insert_entry(conn, 2, title="D1 Database", content="SQLite at the edge")
        _insert_entry(conn, 3, title="Queues", content="Background processing")
        conn.commit()

        _run_migration(conn)
        conn.commit()

        assert _fts_count(conn) == 3
        assert _fts_match_rowids(conn, '"Python"') == [1]
        assert _fts_match_rowids(conn, '"edge"') == [2]

    def test_migration_is_idempotent(self, db_no_migration):
        """Running migration twice doesn't error."""
        conn = db_no_migration
        _run_migration(conn)
        conn.commit()
        # Second run should not raise
        _run_migration(conn)
        conn.commit()

    def test_fts5_match_end_to_end(self, db):
        """Full MATCH query with JOIN works."""
        _insert_entry(db, 1, title="Python Workers", content="Serverless Python")
        _insert_entry(db, 2, title="D1 Database", content="SQLite at the edge")
        db.commit()

        rows = db.execute("""
            SELECT e.id, e.title
            FROM entries e
            JOIN entries_fts fts ON e.id = fts.rowid
            WHERE entries_fts MATCH ?
            ORDER BY e.id
        """, ('"Python"',)).fetchall()

        assert len(rows) == 1
        assert rows[0][0] == 1
        assert rows[0][1] == "Python Workers"


class TestTriggers:
    """Tests for FTS sync triggers."""

    def test_insert_trigger(self, db):
        """Inserting an entry makes it findable via FTS."""
        _insert_entry(db, 1, title="Cloudflare Workers", content="Edge computing")
        db.commit()

        assert _fts_match_rowids(db, '"Cloudflare"') == [1]
        assert _fts_match_rowids(db, '"Edge"') == [1]

    def test_delete_trigger(self, db):
        """Deleting an entry removes it from FTS."""
        _insert_entry(db, 1, title="Temporary Entry", content="Will be deleted")
        db.commit()
        assert _fts_match_rowids(db, '"Temporary"') == [1]

        db.execute("DELETE FROM entries WHERE id = 1")
        db.commit()
        assert _fts_match_rowids(db, '"Temporary"') == []

    def test_update_trigger_title_change(self, db):
        """Updating title removes old and adds new to FTS."""
        _insert_entry(db, 1, title="Old Title", content="Some content")
        db.commit()
        assert _fts_match_rowids(db, '"Old"') == [1]

        db.execute("UPDATE entries SET title = 'New Title' WHERE id = 1")
        db.commit()

        assert _fts_match_rowids(db, '"Old"') == []
        assert _fts_match_rowids(db, '"New"') == [1]

    def test_update_trigger_content_change(self, db):
        """Updating content removes old and adds new to FTS."""
        _insert_entry(db, 1, title="Title", content="Original content here")
        db.commit()
        assert _fts_match_rowids(db, '"Original"') == [1]

        db.execute(
            "UPDATE entries SET content = 'Replacement text here' WHERE id = 1"
        )
        db.commit()

        assert _fts_match_rowids(db, '"Original"') == []
        assert _fts_match_rowids(db, '"Replacement"') == [1]

    def test_upsert_new_entry(self, db):
        """UPSERT of new entry fires INSERT trigger."""
        db.execute("""
            INSERT INTO entries(feed_id, guid, title, content)
            VALUES (1, 'upsert-guid', 'Upserted Title', 'Upserted content')
            ON CONFLICT(feed_id, guid) DO UPDATE SET
                title = excluded.title,
                content = excluded.content
        """)
        db.commit()

        assert _fts_match_rowids(db, '"Upserted"') != []

    def test_upsert_existing_entry(self, db):
        """UPSERT of existing entry fires UPDATE trigger, not INSERT."""
        # Insert original
        db.execute("""
            INSERT INTO entries(feed_id, guid, title, content)
            VALUES (1, 'upsert-guid', 'Original Title', 'Original content')
        """)
        db.commit()
        assert _fts_match_rowids(db, '"Original"') != []

        # Upsert with conflict
        db.execute("""
            INSERT INTO entries(feed_id, guid, title, content)
            VALUES (1, 'upsert-guid', 'Updated Title', 'Updated content')
            ON CONFLICT(feed_id, guid) DO UPDATE SET
                title = excluded.title,
                content = excluded.content
        """)
        db.commit()

        # Old title gone, new title present
        assert _fts_match_rowids(db, '"Original"') == []
        assert _fts_match_rowids(db, '"Updated"') != []
        # No duplicate FTS entries
        assert _fts_count(db) == 1

    def test_batch_delete(self, db):
        """Batch DELETE removes all entries from FTS."""
        _insert_entry(db, 1, title="Entry One", content="First")
        _insert_entry(db, 2, title="Entry Two", content="Second")
        _insert_entry(db, 3, title="Entry Three", content="Third")
        db.commit()
        assert _fts_count(db) == 3

        db.execute("DELETE FROM entries WHERE id IN (1, 3)")
        db.commit()

        assert _fts_count(db) == 1
        assert _fts_match_rowids(db, '"One"') == []
        assert _fts_match_rowids(db, '"Two"') == [2]
        assert _fts_match_rowids(db, '"Three"') == []


class TestRebuildAndIntegrity:
    """Tests for FTS5 rebuild and integrity-check commands."""

    def test_rebuild_after_stale_data(self, db):
        """Rebuild reconciles FTS index with entries table."""
        _insert_entry(db, 1, title="Keep This", content="Keep content")
        _insert_entry(db, 2, title="Remove This", content="Remove content")
        db.commit()
        assert _fts_count(db) == 2

        # Simulate stale FTS data: manually insert a bogus FTS entry.
        # With external content mode, count(*) reads from the content table,
        # so we verify staleness via MATCH instead.
        db.execute(
            "INSERT INTO entries_fts(rowid, title, content) "
            "VALUES (999, 'UniqueStaleGhost', 'Stale content')"
        )
        db.commit()
        # The stale entry is matchable
        assert _fts_match_rowids(db, '"UniqueStaleGhost"') == [999]

        # Rebuild from content table — stale entry should be purged
        db.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        db.commit()

        assert _fts_count(db) == 2
        assert _fts_match_rowids(db, '"Keep"') == [1]
        assert _fts_match_rowids(db, '"Remove"') == [2]
        assert _fts_match_rowids(db, '"UniqueStaleGhost"') == []

    def test_integrity_check_passes(self, db):
        """integrity-check does not raise after normal operations."""
        _insert_entry(db, 1, title="Test Entry", content="Test content")
        db.commit()

        # Should not raise
        db.execute("INSERT INTO entries_fts(entries_fts) VALUES('integrity-check')")


class TestNullHandling:
    """Tests for NULL title/content in FTS triggers."""

    def test_null_title(self, db):
        """Entry with NULL title is indexed (content still searchable)."""
        db.execute(
            "INSERT INTO entries(id, feed_id, guid, title, content) "
            "VALUES (1, 1, 'null-title', NULL, 'searchable content here')"
        )
        db.commit()

        assert _fts_match_rowids(db, '"searchable"') == [1]
        assert _fts_match_rowids(db, '"nonexistent"') == []

    def test_null_content(self, db):
        """Entry with NULL content is indexed (title still searchable)."""
        db.execute(
            "INSERT INTO entries(id, feed_id, guid, title, content) "
            "VALUES (1, 1, 'null-content', 'searchable title', NULL)"
        )
        db.commit()

        assert _fts_match_rowids(db, '"searchable"') == [1]

    def test_update_null_to_non_null(self, db):
        """Updating NULL title to real title makes it searchable."""
        db.execute(
            "INSERT INTO entries(id, feed_id, guid, title, content) "
            "VALUES (1, 1, 'null-update', NULL, 'some content')"
        )
        db.commit()
        assert _fts_match_rowids(db, '"NewTitle"') == []

        db.execute("UPDATE entries SET title = 'NewTitle' WHERE id = 1")
        db.commit()
        assert _fts_match_rowids(db, '"NewTitle"') == [1]


class TestCascadeDelete:
    """Tests for CASCADE DELETE behavior with FTS.

    Note: In CPython's sqlite3, CASCADE deletes fire triggers on child tables.
    In Cloudflare D1, they may not (depends on recursive_triggers setting).
    These tests verify the behavior we get in local SQLite and that the
    JOIN-based query always returns correct results regardless.
    """

    def test_cascade_delete_cleans_entries(self, db):
        """CASCADE delete removes entries from the entries table."""
        _insert_feed(db, 2)
        _insert_entry(db, 1, feed_id=2, title="Cascade Me", content="Will cascade")
        db.commit()
        assert _fts_match_rowids(db, '"Cascade"') == [1]

        db.execute("DELETE FROM feeds WHERE id = 2")
        db.commit()

        # Entry is gone from entries table
        assert db.execute("SELECT count(*) FROM entries WHERE id = 1").fetchone()[0] == 0

    def test_cascade_join_query_returns_nothing(self, db):
        """After cascade, JOIN-based search returns no results (safe regardless)."""
        _insert_feed(db, 2)
        _insert_entry(db, 1, feed_id=2, title="Cascade Me", content="Cascade content")
        db.commit()

        db.execute("DELETE FROM feeds WHERE id = 2")
        db.commit()

        # JOINed query returns nothing — even if FTS had stale entries,
        # the JOIN to entries filters them out
        rows = db.execute("""
            SELECT e.id
            FROM entries e
            JOIN entries_fts fts ON e.id = fts.rowid
            WHERE entries_fts MATCH ?
        """, ('"Cascade"',)).fetchall()
        assert len(rows) == 0

    def test_rebuild_after_cascade(self, db):
        """Rebuild after cascade delete leaves FTS consistent."""
        _insert_feed(db, 2)
        _insert_entry(db, 1, feed_id=2, title="Cascade Clean", content="Content")
        _insert_entry(db, 2, title="Keep This", content="Stays")
        db.commit()

        db.execute("DELETE FROM feeds WHERE id = 2")
        db.commit()

        # Rebuild
        db.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        db.commit()

        assert _fts_match_rowids(db, '"Cascade"') == []
        assert _fts_match_rowids(db, '"Keep"') == [2]


class TestPhraseSearchTokenization:
    """Tests for FTS5 phrase matching with real SQLite."""

    def test_hyphenated_phrase(self, db):
        """Hyphenated words match as adjacent tokens."""
        _insert_entry(db, 1, title="The day-to-day experience", content="Daily work")
        db.commit()

        # unicode61 splits on hyphens: "day" "to" "day"
        # Phrase query with hyphens should match
        assert _fts_match_rowids(db, '"day-to-day"') == [1]
        # Equivalent without hyphens also matches (same tokens)
        assert _fts_match_rowids(db, '"day to day"') == [1]

    def test_punctuated_phrase(self, db):
        """Punctuation between words doesn't prevent phrase match."""
        _insert_entry(
            db, 1, title="Test", content="We handle error.handling patterns carefully"
        )
        db.commit()

        # Period is a token separator, so "error" and "handling" are adjacent tokens
        assert _fts_match_rowids(db, '"error handling"') == [1]

    def test_case_insensitive_phrase(self, db):
        """Phrase search is case-insensitive."""
        _insert_entry(db, 1, title="Context Is The Work", content="Engineering")
        db.commit()

        assert _fts_match_rowids(db, '"context is the work"') == [1]
        assert _fts_match_rowids(db, '"CONTEXT IS THE WORK"') == [1]

    def test_multi_word_implicit_and(self, db):
        """Multi-word non-phrase search uses implicit AND (unordered)."""
        _insert_entry(
            db, 1, title="Python Workers", content="Serverless edge computing"
        )
        _insert_entry(db, 2, title="D1 Database", content="SQLite at the edge")
        db.commit()

        # "Python" AND "edge" — only entry 1 has both
        assert _fts_match_rowids(db, '"Python" "edge"') == [1]
        # Order doesn't matter for implicit AND
        assert _fts_match_rowids(db, '"edge" "Python"') == [1]
