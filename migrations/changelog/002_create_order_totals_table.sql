-- context: ALL
-- Derived-data table the calc_runner's stored-procedure-equivalent functions populate.
CREATE TABLE order_totals (
    order_id TEXT PRIMARY KEY REFERENCES orders(order_id),
    line_item_total REAL,
    discount_total REAL,
    tax_total REAL,
    grand_total REAL,
    updated_at TEXT
);
