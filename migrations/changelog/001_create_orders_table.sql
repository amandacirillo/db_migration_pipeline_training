-- context: ALL
-- Base schema: every environment needs the orders table, regardless of context.
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    program_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'LOADED',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
