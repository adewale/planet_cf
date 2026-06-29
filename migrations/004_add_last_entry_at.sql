-- migrations/004_add_last_entry_at.sql
-- Add last_entry_at column to feeds table for health tracking
--
-- last_entry_at tracks when the most recent entry was added to this feed.
-- This is used by the health dashboard to identify stale feeds that
-- haven't had new content in a while.

-- Add last_entry_at column
--
-- M-D1 (re-run safety): D1/SQLite has no `ADD COLUMN IF NOT EXISTS`, so re-running
-- this file raises "duplicate column name: last_entry_at" once the column exists.
-- That error is intentionally tolerated by scripts/deploy_instance.sh and
-- .github/workflows/check.yml (they grep wrangler's output for "duplicate column"
-- and treat it as already-applied). Kept as a plain ALTER so no data is rebuilt.
ALTER TABLE feeds ADD COLUMN last_entry_at TEXT;

-- Backfill existing feeds: use the most recent entry's published_at or first_seen
UPDATE feeds SET last_entry_at = (
    SELECT COALESCE(MAX(published_at), MAX(first_seen), MAX(created_at))
    FROM entries
    WHERE entries.feed_id = feeds.id
);

-- Create index for efficient health dashboard queries
CREATE INDEX IF NOT EXISTS idx_feeds_last_entry_at ON feeds(last_entry_at DESC);
