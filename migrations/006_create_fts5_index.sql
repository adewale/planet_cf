-- migrations/006_create_fts5_index.sql
-- FTS5 full-text search index for entries table.
--
-- Replaces LIKE-based keyword search with FTS5 inverted index.
-- Uses external content mode (content='entries') so the FTS index
-- stores only tokens, not a copy of the full HTML content.
--
-- IMPORTANT: D1 requires lowercase 'fts5' (case-sensitive).

-- Create FTS5 virtual table
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title,
    content,
    content='entries',
    content_rowid='id',
    tokenize='unicode61'
);

-- Backfill: index all existing entries
INSERT INTO entries_fts(rowid, title, content)
    SELECT id, title, content FROM entries;

-- Keep FTS index in sync with entries table via triggers.
-- Required because external content FTS5 tables do not auto-update.

-- New entry inserted
CREATE TRIGGER IF NOT EXISTS entries_fts_insert AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, title, content)
        VALUES (new.id, new.title, new.content);
END;

-- Entry deleted
CREATE TRIGGER IF NOT EXISTS entries_fts_delete AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, content)
        VALUES ('delete', old.id, old.title, old.content);
END;

-- Entry title or content updated (includes UPSERT conflict path)
CREATE TRIGGER IF NOT EXISTS entries_fts_update AFTER UPDATE OF title, content ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, title, content)
        VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO entries_fts(rowid, title, content)
        VALUES (new.id, new.title, new.content);
END;
