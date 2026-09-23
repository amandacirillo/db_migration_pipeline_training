-- context: DEV,STAGE
-- Seed/sample data - the exact kind of changeset that must NEVER run in production. This is
-- what a Liquibase `contexts` attribute (and here, our own tiny reimplementation of the same
-- idea) is for: one changelog, applied identically everywhere, EXCEPT for changesets explicitly
-- scoped away from prod.
INSERT INTO orders (order_id, program_code, status) VALUES
    ('demo-order-1', 'DEMO', 'LOADED'),
    ('demo-order-2', 'DEMO', 'LOADED');
