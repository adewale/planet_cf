-- migrations/001_initial.sql
-- Planet CF D1 Schema

-- Feeds table
CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    site_url TEXT,
    author_name TEXT,
    author_email TEXT,

    -- HTTP caching
    etag TEXT,
    last_modified TEXT,

    -- Health tracking
    last_fetch_at TEXT,
    last_success_at TEXT,
    fetch_error TEXT,
    fetch_error_count INTEGER DEFAULT 0,
    consecutive_failures INTEGER DEFAULT 0,

    -- Status
    is_active INTEGER DEFAULT 1,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feeds_active ON feeds(is_active);
CREATE INDEX IF NOT EXISTS idx_feeds_url ON feeds(url);

-- Entries table
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL,
    guid TEXT NOT NULL,
    url TEXT,
    title TEXT,
    author TEXT,
    content TEXT,           -- Full sanitized HTML content
    summary TEXT,           -- Short summary/excerpt
    published_at TEXT,
    updated_at TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
    UNIQUE(feed_id, guid)
);

CREATE INDEX IF NOT EXISTS idx_entries_published ON entries(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_entries_feed ON entries(feed_id);
CREATE INDEX IF NOT EXISTS idx_entries_guid ON entries(feed_id, guid);

-- Admin users table
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_username TEXT UNIQUE NOT NULL,
    github_id INTEGER,  -- Populated on first login
    display_name TEXT,
    avatar_url TEXT,

    is_active INTEGER DEFAULT 1,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_admins_github ON admins(github_username);

-- Audit log for admin actions
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT NOT NULL,       -- 'add_feed', 'remove_feed', 'update_feed', etc.
    target_type TEXT,           -- 'feed', 'admin', etc.
    target_id INTEGER,
    details TEXT,               -- JSON blob with action details

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (admin_id) REFERENCES admins(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
