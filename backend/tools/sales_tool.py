import sqlite3
from datetime import date, timedelta
from typing import Any

from langchain_core.tools import tool

from backend.db import connect, first_sales_date
from backend.schemas.tools import SalesArgs
from backend.tools.common import Scope, lookback_window, pct_change, resolve_scope, top_and_bottom

RANKING_SIZE = 5

_TOTALS_SQL = """
SELECT COALESCE(SUM(revenue), 0) AS revenue,
       COALESCE(SUM(units), 0) AS units,
       COALESCE(SUM(CASE WHEN on_promo = 1 THEN units END), 0) AS promo_units
FROM daily_sales
WHERE sku IN (SELECT value FROM json_each(?)) AND date BETWEEN ? AND ?
"""

_BY_SKU_SQL = """
SELECT s.sku, p.name, SUM(s.revenue) AS revenue, SUM(s.units) AS units
FROM daily_sales s
JOIN products p USING (sku)
WHERE s.sku IN (SELECT value FROM json_each(?)) AND s.date BETWEEN ? AND ?
GROUP BY s.sku
ORDER BY revenue DESC, s.sku
"""


def _totals(conn: sqlite3.Connection, scope: Scope, start: date, end: date) -> sqlite3.Row:
    return conn.execute(
        _TOTALS_SQL, (scope.skus_json, start.isoformat(), end.isoformat())
    ).fetchone()


def _sku_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "sku": row["sku"],
        "name": row["name"],
        "revenue": round(row["revenue"], 2),
        "units": row["units"],
    }


@tool("sales_summary", args_schema=SalesArgs)
def sales_summary(category: str | None, sku: str | None, days: int) -> dict[str, Any]:
    """Revenue, units, growth versus the previous period, promo share of units, and the best and
    worst selling SKUs for a category, a single SKU, or the whole store over a lookback window."""
    with connect() as conn:
        scope = resolve_scope(conn, category, sku)
        start, end = lookback_window(conn, days)
        current = _totals(conn, scope, start, end)
        previous_start = start - timedelta(days=days)
        previous = (
            _totals(conn, scope, previous_start, start - timedelta(days=1))
            if previous_start >= first_sales_date(conn)
            else None
        )
        ranked = [
            _sku_row(row)
            for row in conn.execute(
                _BY_SKU_SQL, (scope.skus_json, start.isoformat(), end.isoformat())
            )
        ]

    revenue_change = units_change = None
    if previous is not None:
        revenue_change = pct_change(current["revenue"], previous["revenue"])
        units_change = pct_change(current["units"], previous["units"])

    top, bottom = top_and_bottom(ranked, RANKING_SIZE)
    return {
        "scope": scope.describe(),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "revenue": round(current["revenue"], 2),
        "units": current["units"],
        "avg_daily_units": round(current["units"] / days, 1),
        "revenue_change_pct_vs_previous_period": revenue_change,
        "units_change_pct_vs_previous_period": units_change,
        "promo_units_share_pct": round(current["promo_units"] / current["units"] * 100, 1)
        if current["units"]
        else 0.0,
        "top_skus": top,
        "bottom_skus": bottom,
    }
