-- migrations/005_create_applied_migrations.sql
-- Track which migrations have been applied to this database.

CREATE TABLE IF NOT EXISTS applied_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_name TEXT UNIQUE NOT NULL,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Seed with all existing migrations (already applied if we got this far)
INSERT INTO applied_migrations (migration_name) VALUES ('001_initial.sql')
ON CONFLICT(migration_name) DO NOTHING;

INSERT INTO applied_migrations (migration_name) VALUES ('002_seed_admins.sql')
ON CONFLICT(migration_name) DO NOTHING;

INSERT INTO applied_migrations (migration_name) VALUES ('003_add_first_seen.sql')
ON CONFLICT(migration_name) DO NOTHING;

INSERT INTO applied_migrations (migration_name) VALUES ('004_add_last_entry_at.sql')
ON CONFLICT(migration_name) DO NOTHING;

INSERT INTO applied_migrations (migration_name) VALUES ('005_create_applied_migrations.sql')
ON CONFLICT(migration_name) DO NOTHING;
