-- Databases for the sample stack.
-- raw_portals: immutable raw portal tables (seeded by 02_*/03_* files)
-- analysis:    pipeline output; its tables are created by migrations (Phase 2)

CREATE DATABASE IF NOT EXISTS raw_portals
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS analysis
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- MARIADB_USER is created by the image entrypoint; grant it what the pipeline needs.
-- Note: the user name here must match DB_USER in .env.
GRANT SELECT ON raw_portals.* TO 'jobpipe'@'%';
GRANT ALL PRIVILEGES ON analysis.* TO 'jobpipe'@'%';
FLUSH PRIVILEGES;
