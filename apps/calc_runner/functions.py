"""The stored-procedure-equivalent calculations calc_runner's config names by string.

In the real service these are actual PL/pgSQL functions (`SELECT function_name(?, ?)`); here
they're plain Python functions taking `(connection, order_id)` so the whole pipeline runs against
sqlite3 with zero external services. `FUNCTION_REGISTRY` is what config.py's `function_name`
strings are looked up in - the same "config says a name, code maps it to actual behavior"
indirection the real Lambda gets from the database itself resolving `function_name(?, ?)`.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, Dict

FunctionCallable = Callable[[sqlite3.Connection, str], None]


def _ensure_totals_row(connection: sqlite3.Connection, order_id: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO order_totals (order_id) VALUES (?)",
        (order_id,),
    )


def calc_line_item_total(connection: sqlite3.Connection, order_id: str) -> None:
    """Sequential (S, order=1) - every other calculation depends on this having run first."""
    _ensure_totals_row(connection, order_id)
    line_item_total = 100.0  # stand-in for a real SUM(...) over an order_line_items table
    connection.execute(
        "UPDATE order_totals SET line_item_total = ?, updated_at = ? WHERE order_id = ?",
        (line_item_total, _now(), order_id),
    )


def calc_discount_total(connection: sqlite3.Connection, order_id: str) -> None:
    """Parallel (P) - independent of calc_tax_total, both only need line_item_total to exist."""
    discount_total = 10.0
    connection.execute(
        "UPDATE order_totals SET discount_total = ?, updated_at = ? WHERE order_id = ?",
        (discount_total, _now(), order_id),
    )


def calc_tax_total(connection: sqlite3.Connection, order_id: str) -> None:
    """Parallel (P) - independent of calc_discount_total."""
    tax_total = 7.5
    connection.execute(
        "UPDATE order_totals SET tax_total = ?, updated_at = ? WHERE order_id = ?",
        (tax_total, _now(), order_id),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


FUNCTION_REGISTRY: Dict[str, FunctionCallable] = {
    'calc_line_item_total': calc_line_item_total,
    'calc_discount_total': calc_discount_total,
    'calc_tax_total': calc_tax_total,
}
