import json
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from backend.db import as_of_date, list_categories


class ToolInputError(ValueError):
    """Raised when a tool receives arguments that do not match the catalog."""


@dataclass(frozen=True)
class Scope:
    skus: tuple[str, ...]
    category: str | None
    sku: str | None

    @property
    def skus_json(self) -> str:
        return json.dumps(self.skus)

    def describe(self) -> dict[str, Any]:
        return {"category": self.category, "sku": self.sku, "sku_count": len(self.skus)}


def resolve_scope(conn: sqlite3.Connection, category: str | None, sku: str | None) -> Scope:
    sku_query = (sku or "").strip()
    category_query = (category or "").strip()

    if sku_query:
        row = conn.execute(
            "SELECT sku, category FROM products "
            "WHERE UPPER(sku) = UPPER(?) OR LOWER(name) = LOWER(?)",
            (sku_query, sku_query),
        ).fetchone()
        if row is None:
            raise ToolInputError(f"Unknown SKU '{sku_query}'.")
        if category_query and category_query.lower() != row["category"].lower():
            raise ToolInputError(
                f"SKU {row['sku']} belongs to {row['category']}, not '{category_query}'."
            )
        return Scope((row["sku"],), row["category"], row["sku"])

    if category_query:
        rows = conn.execute(
            "SELECT sku, category FROM products WHERE LOWER(category) = LOWER(?) ORDER BY sku",
            (category_query,),
        ).fetchall()
        if not rows:
            valid = ", ".join(list_categories(conn))
            raise ToolInputError(f"Unknown category '{category_query}'. Valid categories: {valid}.")
        return Scope(tuple(row["sku"] for row in rows), rows[0]["category"], None)

    rows = conn.execute("SELECT sku FROM products ORDER BY sku").fetchall()
    return Scope(tuple(row["sku"] for row in rows), None, None)


def lookback_window(conn: sqlite3.Connection, days: int) -> tuple[date, date]:
    end = as_of_date(conn)
    return end - timedelta(days=days - 1), end


def pct_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def top_and_bottom[T](rows: Sequence[T], count: int) -> tuple[list[T], list[T]]:
    """Split rows ranked best-first into the best `count` and the worst `count`, without overlap."""
    top = list(rows[:count])
    bottom = list(reversed(rows[count:][-count:]))
    return top, bottom


def load_price_history(
    conn: sqlite3.Connection, scope: Scope, as_of: date
) -> dict[str, list[tuple[str, float]]]:
    rows = conn.execute(
        """
        SELECT sku, effective_date, price
        FROM price_history
        WHERE sku IN (SELECT value FROM json_each(?)) AND effective_date <= ?
        ORDER BY sku, effective_date
        """,
        (scope.skus_json, as_of.isoformat()),
    ).fetchall()
    history: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        history[row["sku"]].append((row["effective_date"], row["price"]))
    return history
