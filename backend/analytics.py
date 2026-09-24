from typing import Any

from backend.config import get_settings
from backend.db import connect

WEEKDAYS_MONDAY_FIRST = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
SQLITE_WEEKDAY_TO_NAME = {0: "Sunday", **dict(enumerate(WEEKDAYS_MONDAY_FIRST, start=1))}

_HEADLINE_SQL = """
SELECT SUM(s.revenue) AS revenue,
       SUM(s.units) AS units,
       SUM(s.revenue - s.units * p.unit_cost) AS gross_profit,
       SUM(CASE WHEN s.on_promo = 1 THEN s.units END) * 1.0 / SUM(s.units) AS promo_share,
       MIN(s.date) AS first_date,
       MAX(s.date) AS last_date,
       COUNT(DISTINCT s.sku) AS products
FROM daily_sales s JOIN products p USING (sku)
"""

_MONTHLY_REVENUE_SQL = """
SELECT substr(s.date, 1, 7) AS month, p.category, SUM(s.revenue) / 100000.0 AS revenue_lakh
FROM daily_sales s JOIN products p USING (sku)
GROUP BY month, p.category
ORDER BY month, p.category
"""

_WEEKDAY_SQL = """
SELECT CAST(strftime('%w', date) AS INTEGER) AS weekday, AVG(units) AS avg_units
FROM daily_sales GROUP BY weekday
"""

_CATEGORY_SQL = """
WITH current_price AS (
    SELECT ph.sku, ph.price FROM price_history ph
    WHERE ph.effective_date = (SELECT MAX(effective_date) FROM price_history WHERE sku = ph.sku)
),
promo_counts AS (
    SELECT p.category, COUNT(*) AS promotions
    FROM promotions pm JOIN products p USING (sku) GROUP BY p.category
),
sales AS (
    SELECT p.category,
           SUM(s.revenue) AS revenue,
           SUM(s.revenue - s.units * p.unit_cost) AS gross_profit
    FROM daily_sales s JOIN products p USING (sku) GROUP BY p.category
)
SELECT p.category AS category,
       COUNT(*) AS products,
       sales.revenue / 100000.0 AS revenue_lakh,
       sales.gross_profit * 100.0 / sales.revenue AS gross_margin_pct,
       AVG(cp.price) AS average_price,
       COALESCE(pc.promotions, 0) AS promotions
FROM products p
JOIN current_price cp USING (sku)
JOIN sales ON sales.category = p.category
LEFT JOIN promo_counts pc ON pc.category = p.category
GROUP BY p.category
ORDER BY sales.revenue DESC
"""


def _rows(sql: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql)]


def data_signature() -> tuple[str, int]:
    path = get_settings().db_path.resolve()
    return str(path), path.stat().st_mtime_ns


def headline() -> dict[str, Any]:
    row = _rows(_HEADLINE_SQL)[0]
    return {
        "revenue": row["revenue"],
        "units": row["units"],
        "gross_margin_pct": row["gross_profit"] / row["revenue"] * 100,
        "promo_share_pct": row["promo_share"] * 100,
        "first_date": row["first_date"],
        "last_date": row["last_date"],
        "products": row["products"],
    }


def revenue_by_month() -> list[dict[str, Any]]:
    return _rows(_MONTHLY_REVENUE_SQL)


def weekday_demand() -> list[dict[str, Any]]:
    by_day = {SQLITE_WEEKDAY_TO_NAME[r["weekday"]]: r["avg_units"] for r in _rows(_WEEKDAY_SQL)}
    return [{"day": day, "avg_units": by_day[day]} for day in WEEKDAYS_MONDAY_FIRST]


def category_summary() -> list[dict[str, Any]]:
    return _rows(_CATEGORY_SQL)


def product_catalog() -> list[dict[str, Any]]:
    return _rows("SELECT sku, name, category FROM products ORDER BY sku")
