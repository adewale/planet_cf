-- migrations/002_seed_admins.sql
-- Seed initial admin users
-- NOTE: This is generated from config/admins.json during deployment
-- The github_id is populated on first OAuth login

INSERT INTO admins (github_username, github_id, display_name, is_active)
VALUES ('adewale', 0, 'Adewale Oshineye', 1)
ON CONFLICT(github_username) DO NOTHING;
