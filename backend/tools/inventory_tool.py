from collections import Counter
from typing import Any

from langchain_core.tools import tool

from backend.db import as_of_date, connect
from backend.schemas.tools import InventoryArgs
from backend.tools.common import lookback_window, resolve_scope

DEMAND_WINDOW_DAYS = 30
OVERSTOCK_COVER_DAYS = 60
LIST_LIMIT = 10

_INVENTORY_SQL = """
WITH demand AS (
    SELECT sku, CAST(SUM(units) AS REAL) / :window_days AS avg_daily_units
    FROM daily_sales
    WHERE sku IN (SELECT value FROM json_each(:skus)) AND date BETWEEN :start AND :end
    GROUP BY sku
)
SELECT i.sku, p.name, i.on_hand, i.lead_time_days,
       COALESCE(d.avg_daily_units, 0) AS avg_daily_units
FROM inventory i
JOIN products p USING (sku)
LEFT JOIN demand d USING (sku)
WHERE i.sku IN (SELECT value FROM json_each(:skus))
"""


def _cover_and_status(
    on_hand: int, avg_daily_units: float, lead_time_days: int
) -> tuple[float | None, str]:
    if avg_daily_units <= 0:
        return None, "no_recent_demand"
    cover = on_hand / avg_daily_units
    if cover < lead_time_days:
        return cover, "stockout_risk"
    if cover > OVERSTOCK_COVER_DAYS:
        return cover, "overstock"
    return cover, "healthy"


@tool("inventory_status", args_schema=InventoryArgs)
def inventory_status(category: str | None, sku: str | None) -> dict[str, Any]:
    """Current stock position: days of cover based on the last 30 days of demand, and which SKUs
    are at risk of a stockout (cover below supplier lead time) or overstocked (over 60 days)."""
    with connect() as conn:
        scope = resolve_scope(conn, category, sku)
        start, end = lookback_window(conn, DEMAND_WINDOW_DAYS)
        as_of = as_of_date(conn)
        records = conn.execute(
            _INVENTORY_SQL,
            {
                "skus": scope.skus_json,
                "window_days": DEMAND_WINDOW_DAYS,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        ).fetchall()

    rows = []
    for record in records:
        cover, status = _cover_and_status(
            record["on_hand"], record["avg_daily_units"], record["lead_time_days"]
        )
        rows.append(
            {
                "sku": record["sku"],
                "name": record["name"],
                "on_hand": record["on_hand"],
                "avg_daily_units": round(record["avg_daily_units"], 1),
                "days_of_cover": None if cover is None else round(cover, 1),
                "lead_time_days": record["lead_time_days"],
                "status": status,
            }
        )

    at_risk = sorted(
        (r for r in rows if r["status"] == "stockout_risk"), key=lambda r: r["days_of_cover"]
    )
    overstocked = sorted(
        (r for r in rows if r["status"] == "overstock"),
        key=lambda r: r["days_of_cover"],
        reverse=True,
    )
    result: dict[str, Any] = {
        "scope": scope.describe(),
        "as_of": as_of.isoformat(),
        "demand_window_days": DEMAND_WINDOW_DAYS,
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "stockout_risk": at_risk[:LIST_LIMIT],
        "overstock": overstocked[:LIST_LIMIT],
    }
    if len(rows) <= LIST_LIMIT:
        result["items"] = sorted(rows, key=lambda r: r["sku"])
    return result
