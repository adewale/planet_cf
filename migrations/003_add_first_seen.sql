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
ALTER TABLE entries ADD COLUMN first_seen TEXT;

-- Backfill existing entries: use created_at if available, otherwise published_at
UPDATE entries SET first_seen = COALESCE(created_at, published_at, CURRENT_TIMESTAMP);

-- Create index for efficient sorting by first_seen
CREATE INDEX IF NOT EXISTS idx_entries_first_seen ON entries(first_seen DESC);
