from typing import Any

from langchain_core.tools import tool

from backend.db import connect
from backend.schemas.tools import AssortmentArgs
from backend.tools.common import ToolInputError, lookback_window, resolve_scope

CLASS_A_CUMULATIVE_SHARE = 0.70
CLASS_B_CUMULATIVE_SHARE = 0.90
TOP_COUNT = 5
TAIL_COUNT = 8

_PERFORMANCE_SQL = """
SELECT p.sku, p.name, p.unit_cost,
       COALESCE(SUM(s.units), 0) AS units,
       COALESCE(SUM(s.revenue), 0) AS revenue
FROM products p
LEFT JOIN daily_sales s ON s.sku = p.sku AND s.date BETWEEN ? AND ?
WHERE p.sku IN (SELECT value FROM json_each(?))
GROUP BY p.sku
ORDER BY revenue DESC, p.sku
"""


def _abc_class(cumulative_share_before: float) -> str:
    if cumulative_share_before < CLASS_A_CUMULATIVE_SHARE:
        return "A"
    if cumulative_share_before < CLASS_B_CUMULATIVE_SHARE:
        return "B"
    return "C"


@tool("assortment_analysis", args_schema=AssortmentArgs)
def assortment_analysis(category: str, days: int) -> dict[str, Any]:
    """ABC (Pareto) classification of the SKUs in one category by revenue contribution, with the
    top performers, the long-tail SKUs with the lowest gross profit, and SKUs with no sales. Use it
    for range, delisting and space allocation questions."""
    if not (category or "").strip():
        raise ToolInputError("assortment_analysis requires a category.")
    with connect() as conn:
        scope = resolve_scope(conn, category, None)
        start, end = lookback_window(conn, days)
        records = conn.execute(
            _PERFORMANCE_SQL, (start.isoformat(), end.isoformat(), scope.skus_json)
        ).fetchall()

    total_revenue = sum(r["revenue"] for r in records)
    total_profit = sum(r["revenue"] - r["units"] * r["unit_cost"] for r in records)

    rows = []
    cumulative = 0.0
    for record in records:
        share = record["revenue"] / total_revenue if total_revenue else 0.0
        rows.append(
            {
                "sku": record["sku"],
                "name": record["name"],
                "abc_class": _abc_class(cumulative),
                "revenue_share_pct": round(share * 100, 1),
                "gross_profit": round(record["revenue"] - record["units"] * record["unit_cost"], 2),
                "units_per_day": round(record["units"] / days, 1),
            }
        )
        cumulative += share

    class_summary = {}
    for label in ("A", "B", "C"):
        members = [r for r in rows if r["abc_class"] == label]
        class_summary[label] = {
            "sku_count": len(members),
            "revenue_share_pct": round(sum(r["revenue_share_pct"] for r in members), 1),
        }

    tail = sorted((r for r in rows if r["abc_class"] == "C"), key=lambda r: r["gross_profit"])
    return {
        "category": scope.category,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "sku_count": len(rows),
        "category_revenue": round(total_revenue, 2),
        "category_gross_profit": round(total_profit, 2),
        "gross_margin_pct": round(total_profit / total_revenue * 100, 1) if total_revenue else None,
        "class_summary": class_summary,
        "top_skus": rows[:TOP_COUNT],
        "tail_skus": tail[:TAIL_COUNT],
        "zero_sales_skus": [r["sku"] for r in records if r["units"] == 0],
    }
