-- context: ALL
-- A later migration touching a table an earlier migration created - demonstrates that
-- migrations are additive/ordered, never edited after being applied (see MigrationRunner's
-- checksum guard in db/migration_runner.py).
ALTER TABLE order_totals ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD';
