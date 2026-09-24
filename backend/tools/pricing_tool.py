from datetime import timedelta
from typing import Any

from langchain_core.tools import tool

from backend.db import as_of_date, connect
from backend.schemas.tools import PricingArgs
from backend.tools.common import load_price_history, pct_change, resolve_scope

LIST_LIMIT = 10
RECENT_REPRICING_DAYS = 90


@tool("pricing_info", args_schema=PricingArgs)
def pricing_info(category: str | None, sku: str | None) -> dict[str, Any]:
    """Current selling price, unit cost, gross margin percentage, and recent price changes for a
    category, a single SKU, or the whole store. Lists the lowest-margin SKUs first."""
    with connect() as conn:
        scope = resolve_scope(conn, category, sku)
        as_of = as_of_date(conn)
        history = load_price_history(conn, scope, as_of)
        products = conn.execute(
            "SELECT sku, name, unit_cost FROM products "
            "WHERE sku IN (SELECT value FROM json_each(?))",
            (scope.skus_json,),
        ).fetchall()

    rows = []
    for product in products:
        prices = history[product["sku"]]
        price = prices[-1][1]
        changed = len(prices) > 1
        rows.append(
            {
                "sku": product["sku"],
                "name": product["name"],
                "price": price,
                "unit_cost": product["unit_cost"],
                "margin_pct": round((price - product["unit_cost"]) / price * 100, 1),
                "last_change_date": prices[-1][0] if changed else None,
                "last_change_pct": pct_change(price, prices[-2][1]) if changed else None,
            }
        )
    rows.sort(key=lambda r: r["margin_pct"])

    margins = [r["margin_pct"] for r in rows]
    recent_cutoff = (as_of - timedelta(days=RECENT_REPRICING_DAYS - 1)).isoformat()
    result: dict[str, Any] = {
        "scope": scope.describe(),
        "as_of": as_of.isoformat(),
        "avg_margin_pct": round(sum(margins) / len(margins), 1),
        "min_margin_pct": min(margins),
        "max_margin_pct": max(margins),
        f"repriced_last_{RECENT_REPRICING_DAYS}_days": sum(
            1 for r in rows if r["last_change_date"] and r["last_change_date"] >= recent_cutoff
        ),
        "lowest_margin_skus": rows[:LIST_LIMIT],
    }
    if scope.sku:
        result["price_history"] = [
            {"effective_date": date, "price": price} for date, price in history[scope.sku]
        ]
    return result
