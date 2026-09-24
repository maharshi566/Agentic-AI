import sqlite3
from typing import Any

from langchain_core.tools import tool

from backend.db import as_of_date, connect
from backend.schemas.tools import PromotionArgs
from backend.tools.common import resolve_scope, top_and_bottom

BASELINE_DAYS = 28
RECENT_COUNT = 5
RANKED_COUNT = 3

_PROMO_SQL = f"""
SELECT pm.promo_id, pm.sku, p.name, pm.start_date, pm.end_date, pm.discount_pct, p.unit_cost,
    (SELECT AVG(units) FROM daily_sales s
        WHERE s.sku = pm.sku AND s.date BETWEEN pm.start_date AND pm.end_date) AS promo_units,
    (SELECT AVG(revenue) FROM daily_sales s
        WHERE s.sku = pm.sku AND s.date BETWEEN pm.start_date AND pm.end_date) AS promo_revenue,
    (SELECT AVG(units) FROM daily_sales s
        WHERE s.sku = pm.sku AND s.on_promo = 0
          AND s.date >= date(pm.start_date, '-{BASELINE_DAYS} days')
          AND s.date < pm.start_date) AS base_units,
    (SELECT AVG(revenue) FROM daily_sales s
        WHERE s.sku = pm.sku AND s.on_promo = 0
          AND s.date >= date(pm.start_date, '-{BASELINE_DAYS} days')
          AND s.date < pm.start_date) AS base_revenue
FROM promotions pm
JOIN products p USING (sku)
WHERE pm.sku IN (SELECT value FROM json_each(?)) AND pm.end_date <= ?
ORDER BY pm.start_date DESC
"""


def _evaluate(record: sqlite3.Row) -> dict[str, Any] | None:
    if not record["base_units"] or not record["base_revenue"]:
        return None
    cost = record["unit_cost"]
    promo_profit = record["promo_revenue"] - record["promo_units"] * cost
    base_profit = record["base_revenue"] - record["base_units"] * cost
    return {
        "promo_id": record["promo_id"],
        "sku": record["sku"],
        "name": record["name"],
        "start_date": record["start_date"],
        "end_date": record["end_date"],
        "discount_pct": record["discount_pct"],
        "unit_uplift_pct": round((record["promo_units"] / record["base_units"] - 1) * 100, 1),
        "daily_profit_change_pct": round((promo_profit - base_profit) / base_profit * 100, 1)
        if base_profit > 0
        else None,
    }


@tool("promotion_history", args_schema=PromotionArgs)
def promotion_history(category: str | None, sku: str | None) -> dict[str, Any]:
    """Past promotions for a category, a single SKU, or the whole store: discount depth, unit uplift
    against the 28 days before each promotion, and the effect on daily gross profit."""
    with connect() as conn:
        scope = resolve_scope(conn, category, sku)
        as_of = as_of_date(conn)
        records = conn.execute(_PROMO_SQL, (scope.skus_json, as_of.isoformat())).fetchall()

    promos = [promo for promo in map(_evaluate, records) if promo is not None]
    with_profit = [p for p in promos if p["daily_profit_change_pct"] is not None]
    by_profit = sorted(with_profit, key=lambda p: p["daily_profit_change_pct"], reverse=True)
    most_profitable, least_profitable = top_and_bottom(by_profit, RANKED_COUNT)

    def average(key: str, rows: list[dict[str, Any]]) -> float | None:
        return round(sum(r[key] for r in rows) / len(rows), 1) if rows else None

    return {
        "scope": scope.describe(),
        "promotion_count": len(promos),
        "avg_discount_pct": average("discount_pct", promos),
        "avg_unit_uplift_pct": average("unit_uplift_pct", promos),
        "profitable_promo_share_pct": round(
            sum(1 for p in with_profit if p["daily_profit_change_pct"] > 0)
            / len(with_profit)
            * 100,
            1,
        )
        if with_profit
        else None,
        "most_profitable": most_profitable,
        "least_profitable": least_profitable,
        "most_recent": promos[:RECENT_COUNT],
    }
