-- migrations/003_add_first_seen.sql
-- Add first_seen column to entries table for spam prevention
--
-- first_seen tracks when an entry was FIRST discovered by the system.
-- This is preserved during updates to prevent spam attacks where feeds
-- retroactively add old entries that would appear as new.
--
-- Different from published_at which comes from the feed and can change.

-- Add first_seen column (no default - SQLite doesn't allow non-constant defaults in ALTER)
-- The INSERT statement in _upsert_entry handles setting CURRENT_TIMESTAMP
--
-- M-D1 (re-run safety): D1/SQLite has no `ADD COLUMN IF NOT EXISTS`, so re-running
-- this file against a database that already has the column raises
-- "duplicate column name: first_seen". That is the intended, tolerated outcome:
-- both scripts/deploy_instance.sh and .github/workflows/check.yml capture
-- wrangler's output and treat a "duplicate column" error on re-run as
-- already-applied (failing only on unexpected errors). This keeps the ALTER a
-- plain, data-safe statement rather than a guarded rebuild that could lose rows.
ALTER TABLE entries ADD COLUMN first_seen TEXT;

-- Backfill existing entries: use created_at if available, otherwise published_at
UPDATE entries SET first_seen = COALESCE(created_at, published_at, CURRENT_TIMESTAMP);

-- Create index for efficient sorting by first_seen
CREATE INDEX IF NOT EXISTS idx_entries_first_seen ON entries(first_seen DESC);
