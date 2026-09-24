"""Hand-built dataset with known numbers, for exact assertions on tool output.

Window arithmetic (as of 2026-01-31, 60 days of history from 2025-12-03):
  30-day window            2026-01-02 .. 2026-01-31
  previous 30-day window   2025-12-03 .. 2026-01-01
  promo baseline           28 non-promo days before each promo start
"""

import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from backend.data.generate_data import SCHEMA

AS_OF = date(2026, 1, 31)
HISTORY_DAYS = 60
FIRST_DATE = AS_OF - timedelta(days=HISTORY_DAYS - 1)

PRODUCTS = [
    ("A-001", "Star", "Alpha", 60.0),
    ("A-002", "Mid", "Alpha", 40.0),
    ("A-003", "Tail", "Alpha", 15.0),
    ("A-004", "Dead", "Alpha", 20.0),
    ("B-001", "Base", "Beta", 9.0),
    ("B-002", "Edge Cover", "Beta", 9.0),
    ("B-003", "Edge Overstock", "Beta", 9.0),
]

PRICES = {
    "A-001": [(FIRST_DATE, 100.0)],
    "A-002": [(FIRST_DATE, 50.0)],
    "A-003": [(FIRST_DATE, 20.0)],
    "A-004": [(FIRST_DATE, 30.0), (date(2026, 1, 10), 33.0)],
    "B-001": [(FIRST_DATE, 10.0)],
    "B-002": [(FIRST_DATE, 10.0)],
    "B-003": [(FIRST_DATE, 10.0)],
}

BASE_UNITS = {"A-001": 10, "A-002": 4, "A-003": 1, "A-004": 0, "B-001": 5, "B-002": 5, "B-003": 5}

PROMOS = [
    ("A-001", date(2026, 1, 10), date(2026, 1, 14), 20.0, 25),
    ("A-002", date(2026, 1, 20), date(2026, 1, 22), 10.0, 4),
    ("B-001", FIRST_DATE, FIRST_DATE + timedelta(days=2), 10.0, 6),
    ("A-003", date(2026, 2, 1), date(2026, 2, 5), 15.0, 3),
]

INVENTORY = {
    "A-001": (30, 5),
    "A-002": (400, 3),
    "A-003": (30, 7),
    "A-004": (50, 3),
    "B-001": (100, 2),
    "B-002": (15, 3),
    "B-003": (300, 2),
}


def _price_on(sku: str, day: date) -> float:
    return [price for effective, price in PRICES[sku] if effective <= day][-1]


def build_small_db(path: Path) -> None:
    promo_days = {
        (sku, start + timedelta(days=offset)): (discount, units)
        for sku, start, end, discount, units in PROMOS
        for offset in range((end - start).days + 1)
        if start + timedelta(days=offset) <= AS_OF
    }

    sales = []
    for sku, base_units in BASE_UNITS.items():
        for offset in range(HISTORY_DAYS):
            day = FIRST_DATE + timedelta(days=offset)
            discount, units = promo_days.get((sku, day), (0.0, base_units))
            revenue = round(units * _price_on(sku, day) * (1 - discount / 100), 2)
            sales.append((sku, day.isoformat(), units, revenue, int(discount > 0)))

    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO meta (key, value) VALUES ('as_of_date', ?)", (AS_OF.isoformat(),))
        conn.executemany(
            "INSERT INTO products (sku, name, category, unit_cost) VALUES (?, ?, ?, ?)", PRODUCTS
        )
        conn.executemany(
            "INSERT INTO price_history (sku, effective_date, price) VALUES (?, ?, ?)",
            [
                (sku, effective.isoformat(), price)
                for sku, rows in PRICES.items()
                for effective, price in rows
            ],
        )
        conn.executemany(
            "INSERT INTO daily_sales (sku, date, units, revenue, on_promo) VALUES (?, ?, ?, ?, ?)",
            sales,
        )
        conn.executemany(
            "INSERT INTO inventory (sku, on_hand, lead_time_days) VALUES (?, ?, ?)",
            [(sku, on_hand, lead) for sku, (on_hand, lead) in INVENTORY.items()],
        )
        conn.executemany(
            "INSERT INTO promotions (sku, start_date, end_date, discount_pct) VALUES (?, ?, ?, ?)",
            [(sku, start.isoformat(), end.isoformat(), pct) for sku, start, end, pct, _ in PROMOS],
        )
