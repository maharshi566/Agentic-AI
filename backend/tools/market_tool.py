from dataclasses import asdict
from typing import Any

from langchain_core.tools import tool

from backend.db import as_of_date, connect
from backend.integrations.market_api import ProductRef, get_market_client
from backend.schemas.tools import MarketArgs
from backend.tools.common import load_price_history, resolve_scope, top_and_bottom

RANKING_SIZE = 5
PARITY_BAND_PCT = 5


@tool("market_signals", args_schema=MarketArgs)
def market_signals(category: str | None, sku: str | None) -> dict[str, Any]:
    """External market data: competitor price levels against our current prices (price index of 100
    means parity) and 30-day category demand trend and search interest. Use it for pricing and
    promotion decisions."""
    with connect() as conn:
        scope = resolve_scope(conn, category, sku)
        history = load_price_history(conn, scope, as_of_date(conn))
        products = conn.execute(
            "SELECT sku, name, category FROM products "
            "WHERE sku IN (SELECT value FROM json_each(?))",
            (scope.skus_json,),
        ).fetchall()

    client = get_market_client()
    refs = [
        ProductRef(
            sku=p["sku"],
            name=p["name"],
            our_price=history[p["sku"]][-1][1],
            reference_price=history[p["sku"]][0][1],
        )
        for p in products
    ]
    competitor = client.competitor_prices(refs)

    rows = []
    for ref in refs:
        quote = competitor[ref.sku]
        rows.append(
            {
                "sku": ref.sku,
                "name": ref.name,
                "our_price": ref.our_price,
                "competitor_avg_price": quote.avg_price,
                "competitor_min_price": quote.min_price,
                "price_index": round(ref.our_price / quote.avg_price * 100, 1),
            }
        )
    rows.sort(key=lambda r: r["price_index"], reverse=True)
    highest, lowest = top_and_bottom(rows, RANKING_SIZE)

    return {
        "source": client.source,
        "scope": scope.describe(),
        "category_demand": [
            asdict(client.category_demand(name))
            for name in sorted({p["category"] for p in products})
        ],
        "price_position": {
            "above_market": sum(1 for r in rows if r["price_index"] > 100 + PARITY_BAND_PCT),
            "at_parity": sum(1 for r in rows if abs(r["price_index"] - 100) <= PARITY_BAND_PCT),
            "below_market": sum(1 for r in rows if r["price_index"] < 100 - PARITY_BAND_PCT),
        },
        "highest_price_index": highest,
        "lowest_price_index": lowest,
    }
