"""Generate a reproducible synthetic supermarket dataset in SQLite."""

import argparse
import math
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

DEFAULT_DB_PATH = Path(__file__).with_name("retail.db")
DEFAULT_END_DATE = date(2026, 8, 31)
DEFAULT_SEED = 42
HISTORY_DAYS = 365

WEEKDAY_FACTOR = (0.90, 0.90, 0.92, 0.95, 1.05, 1.25, 1.20)
PROMO_DISCOUNTS = (5.0, 10.0, 15.0, 20.0, 25.0, 30.0)
PROMO_DEMAND_HALO = 1.15
PROMO_MARGIN_BUFFER_PCT = 3.0
PRICE_FLOOR_MARKUP = 1.05
LEAD_TIMES_DAYS = (2, 3, 5, 7)

SCHEMA = """
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE products (
    sku       TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL,
    unit_cost REAL NOT NULL
);
CREATE INDEX idx_products_category ON products (category);
CREATE TABLE price_history (
    sku            TEXT NOT NULL REFERENCES products (sku),
    effective_date TEXT NOT NULL,
    price          REAL NOT NULL,
    PRIMARY KEY (sku, effective_date)
) WITHOUT ROWID;
CREATE TABLE daily_sales (
    sku      TEXT NOT NULL REFERENCES products (sku),
    date     TEXT NOT NULL,
    units    INTEGER NOT NULL,
    revenue  REAL NOT NULL,
    on_promo INTEGER NOT NULL,
    PRIMARY KEY (sku, date)
) WITHOUT ROWID;
CREATE TABLE inventory (
    sku            TEXT PRIMARY KEY REFERENCES products (sku),
    on_hand        INTEGER NOT NULL,
    lead_time_days INTEGER NOT NULL
);
CREATE TABLE promotions (
    promo_id     INTEGER PRIMARY KEY,
    sku          TEXT NOT NULL REFERENCES products (sku),
    start_date   TEXT NOT NULL,
    end_date     TEXT NOT NULL,
    discount_pct REAL NOT NULL
);
"""


@dataclass(frozen=True)
class CategoryProfile:
    prefix: str
    daily_volume: float
    cost_ratio: tuple[float, float]
    elasticity: tuple[float, float]
    seasonal_amplitude: float
    seasonal_peak_day: int
    items: tuple[tuple[str, float], ...]
    max_cover_days: float = 140.0


CATEGORIES: dict[str, CategoryProfile] = {
    "Beverages": CategoryProfile(
        prefix="BEV",
        daily_volume=40,
        cost_ratio=(0.55, 0.70),
        elasticity=(1.2, 2.4),
        seasonal_amplitude=0.35,
        seasonal_peak_day=135,
        items=(
            ("Assam Tea 500g", 240),
            ("Filter Coffee Powder 200g", 210),
            ("Instant Coffee 100g", 320),
            ("Cola 750ml", 45),
            ("Lemon Soda 600ml", 30),
            ("Orange Juice 1L", 110),
            ("Mango Drink 1L", 95),
            ("Coconut Water 200ml", 40),
            ("Energy Drink 250ml", 125),
            ("Packaged Water 1L", 20),
            ("Iced Tea 500ml", 60),
            ("Green Tea 25 Bags", 155),
            ("Malt Drink 500g", 285),
            ("Sparkling Water 750ml", 55),
        ),
    ),
    "Snacks": CategoryProfile(
        prefix="SNK",
        daily_volume=35,
        cost_ratio=(0.60, 0.72),
        elasticity=(1.0, 2.2),
        seasonal_amplitude=0.12,
        seasonal_peak_day=300,
        items=(
            ("Potato Chips 150g", 50),
            ("Masala Peanuts 200g", 60),
            ("Salted Cashews 200g", 260),
            ("Namkeen Mix 400g", 110),
            ("Cream Biscuits 300g", 45),
            ("Digestive Biscuits 250g", 85),
            ("Chocolate Bar 40g", 40),
            ("Dark Chocolate 100g", 175),
            ("Instant Noodles 4 Pack", 60),
            ("Popcorn 100g", 45),
            ("Roasted Almonds 250g", 340),
            ("Nutrition Bar 6 Pack", 190),
            ("Rice Crackers 100g", 70),
            ("Trail Mix 200g", 210),
        ),
    ),
    "Dairy": CategoryProfile(
        prefix="DRY",
        daily_volume=60,
        cost_ratio=(0.78, 0.90),
        elasticity=(0.5, 1.2),
        seasonal_amplitude=0.05,
        seasonal_peak_day=30,
        items=(
            ("Full Cream Milk 1L", 68),
            ("Toned Milk 500ml", 27),
            ("Curd 400g", 40),
            ("Butter 500g", 285),
            ("Cheese Slices 200g", 130),
            ("Paneer 200g", 90),
            ("Ghee 1L", 640),
            ("Buttermilk 200ml", 15),
            ("Flavoured Yogurt 100g", 25),
            ("Cheese Spread 200g", 120),
            ("Cream 200ml", 75),
            ("Condensed Milk 400g", 135),
            ("Milk Powder 500g", 265),
        ),
        max_cover_days=30,
    ),
    "Staples": CategoryProfile(
        prefix="STP",
        daily_volume=30,
        cost_ratio=(0.82, 0.92),
        elasticity=(0.4, 1.0),
        seasonal_amplitude=0.06,
        seasonal_peak_day=300,
        items=(
            ("Basmati Rice 5kg", 620),
            ("Wheat Flour 5kg", 260),
            ("Toor Dal 1kg", 165),
            ("Moong Dal 1kg", 135),
            ("Sunflower Oil 1L", 145),
            ("Mustard Oil 1L", 175),
            ("Sugar 1kg", 46),
            ("Iodised Salt 1kg", 24),
            ("Chana Dal 1kg", 110),
            ("Rajma 1kg", 145),
            ("Poha 500g", 48),
            ("Semolina 500g", 42),
            ("Turmeric Powder 200g", 70),
            ("Jaggery 1kg", 80),
        ),
    ),
    "Personal Care": CategoryProfile(
        prefix="PCR",
        daily_volume=15,
        cost_ratio=(0.50, 0.65),
        elasticity=(0.9, 1.8),
        seasonal_amplitude=0.08,
        seasonal_peak_day=60,
        items=(
            ("Herbal Shampoo 340ml", 245),
            ("Conditioner 180ml", 190),
            ("Body Wash 250ml", 210),
            ("Bathing Soap 4 Pack", 150),
            ("Toothpaste 200g", 115),
            ("Toothbrush 3 Pack", 120),
            ("Face Wash 100ml", 175),
            ("Moisturiser 200ml", 230),
            ("Deodorant 150ml", 210),
            ("Hand Sanitiser 200ml", 95),
            ("Hair Oil 300ml", 160),
            ("Sunscreen 50g", 320),
            ("Razor 5 Pack", 140),
        ),
    ),
    "Household": CategoryProfile(
        prefix="HHD",
        daily_volume=12,
        cost_ratio=(0.60, 0.75),
        elasticity=(0.8, 1.6),
        seasonal_amplitude=0.10,
        seasonal_peak_day=295,
        items=(
            ("Laundry Detergent 2kg", 380),
            ("Dishwash Liquid 750ml", 175),
            ("Floor Cleaner 1L", 210),
            ("Toilet Cleaner 500ml", 105),
            ("Glass Cleaner 500ml", 130),
            ("Garbage Bags 30 Pack", 115),
            ("Kitchen Towels 2 Roll", 95),
            ("Aluminium Foil 25m", 140),
            ("Scrub Pads 3 Pack", 60),
            ("Air Freshener 250ml", 185),
            ("Fabric Softener 1L", 235),
            ("LED Bulb 9W 2 Pack", 220),
        ),
    ),
}


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    category: str
    base_price: float
    unit_cost: float
    base_volume: float
    elasticity: float
    growth: float


@dataclass(frozen=True)
class Calendar:
    dates: list[date]
    weekday_factor: np.ndarray
    day_of_year: np.ndarray

    @classmethod
    def ending(cls, end_date: date, days: int) -> "Calendar":
        dates = [end_date - timedelta(days=days - 1 - offset) for offset in range(days)]
        return cls(
            dates=dates,
            weekday_factor=np.array([WEEKDAY_FACTOR[d.weekday()] for d in dates]),
            day_of_year=np.array([d.timetuple().tm_yday for d in dates]),
        )

    @property
    def size(self) -> int:
        return len(self.dates)


def build_products(rng: np.random.Generator) -> list[Product]:
    products: list[Product] = []
    for category, profile in CATEGORIES.items():
        for number, (name, price) in enumerate(profile.items, start=1):
            volume = profile.daily_volume * rng.lognormal(0.0, 0.5) * (100 / price) ** 0.4
            products.append(
                Product(
                    sku=f"{profile.prefix}-{number:03d}",
                    name=name,
                    category=category,
                    base_price=float(price),
                    unit_cost=round(price * rng.uniform(*profile.cost_ratio), 2),
                    base_volume=float(volume),
                    elasticity=float(rng.uniform(*profile.elasticity)),
                    growth=float(rng.normal(0.05, 0.15)),
                )
            )
    return products


def build_price_events(
    rng: np.random.Generator, base_price: float, unit_cost: float, n_days: int
) -> list[tuple[int, float]]:
    change_days = sorted(
        {int(d) for d in rng.integers(20, n_days - 20, size=int(rng.integers(0, 3)))}
    )
    price_floor = float(math.ceil(unit_cost * PRICE_FLOOR_MARKUP))
    events = [(0, base_price)]
    price = base_price
    for day in change_days:
        new_price = max(float(round(price * (1 + rng.uniform(-0.06, 0.10)))), price_floor)
        if new_price != price:
            events.append((day, new_price))
            price = new_price
    return events


def expand_step_function(events: list[tuple[int, float]], n_days: int) -> np.ndarray:
    values = np.empty(n_days)
    stops = [day for day, _ in events[1:]] + [n_days]
    for (start, value), stop in zip(events, stops, strict=True):
        values[start:stop] = value
    return values


def build_promotions(
    rng: np.random.Generator, n_days: int, max_discount_pct: float
) -> list[tuple[int, int, float]]:
    depths = [d for d in PROMO_DISCOUNTS if d <= max_discount_pct] or [min(PROMO_DISCOUNTS)]
    promos: list[tuple[int, int, float]] = []
    occupied = np.zeros(n_days, dtype=bool)
    for _ in range(int(rng.poisson(1.6))):
        duration = int(rng.integers(5, 15))
        start = int(rng.integers(30, n_days - duration - 7))
        end = start + duration - 1
        if occupied[max(0, start - 14) : end + 15].any():
            continue
        occupied[start : end + 1] = True
        promos.append((start, end, float(rng.choice(depths))))
    return promos


def simulate_demand(
    rng: np.random.Generator,
    product: Product,
    calendar: Calendar,
    list_price: np.ndarray,
    discount_pct: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    profile = CATEGORIES[product.category]
    effective_price = list_price * (1 - discount_pct / 100)
    seasonal = 1 + profile.seasonal_amplitude * np.cos(
        2 * np.pi * (calendar.day_of_year - profile.seasonal_peak_day) / 365
    )
    trend = np.exp(product.growth * np.arange(calendar.size) / 365)
    price_effect = (effective_price / product.base_price) ** -product.elasticity
    halo = np.where(discount_pct > 0, PROMO_DEMAND_HALO, 1.0)
    expected = (
        product.base_volume * calendar.weekday_factor * seasonal * trend * price_effect * halo
    )
    units = rng.poisson(expected)
    revenue = np.round(units * effective_price, 2)
    return units, revenue


def build_inventory(
    rng: np.random.Generator, recent_daily_units: float, max_cover_days: float
) -> tuple[int, int]:
    bucket = rng.random()
    if bucket < 0.12:
        cover_days = rng.uniform(1, 6)
    elif bucket < 0.27:
        cover_days = rng.uniform(70, 140)
    else:
        cover_days = rng.uniform(14, 45)
    lead_time = int(rng.choice(LEAD_TIMES_DAYS))
    on_hand = int(round(recent_daily_units * min(cover_days, max_cover_days)))
    return on_hand, lead_time


def populate(
    path: Path,
    rng: np.random.Generator,
    calendar: Calendar,
    products: list[Product],
    seed: int,
    end_date: date,
) -> dict[str, int]:
    date_strings = [d.isoformat() for d in calendar.dates]

    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [
                ("as_of_date", end_date.isoformat()),
                ("seed", str(seed)),
                ("currency", "INR"),
            ],
        )
        conn.executemany(
            "INSERT INTO products (sku, name, category, unit_cost) VALUES (?, ?, ?, ?)",
            [(p.sku, p.name, p.category, p.unit_cost) for p in products],
        )

        for product in products:
            events = build_price_events(rng, product.base_price, product.unit_cost, calendar.size)
            list_price = expand_step_function(events, calendar.size)
            conn.executemany(
                "INSERT INTO price_history (sku, effective_date, price) VALUES (?, ?, ?)",
                [(product.sku, date_strings[day], price) for day, price in events],
            )

            discount_pct = np.zeros(calendar.size)
            margin_pct = (1 - product.unit_cost / product.base_price) * 100
            promos = build_promotions(rng, calendar.size, margin_pct - PROMO_MARGIN_BUFFER_PCT)
            for start, end, pct in promos:
                discount_pct[start : end + 1] = pct
            conn.executemany(
                "INSERT INTO promotions (sku, start_date, end_date, discount_pct) "
                "VALUES (?, ?, ?, ?)",
                [(product.sku, date_strings[s], date_strings[e], pct) for s, e, pct in promos],
            )

            units, revenue = simulate_demand(rng, product, calendar, list_price, discount_pct)
            conn.executemany(
                "INSERT INTO daily_sales (sku, date, units, revenue, on_promo) "
                "VALUES (?, ?, ?, ?, ?)",
                zip(
                    [product.sku] * calendar.size,
                    date_strings,
                    units.tolist(),
                    revenue.tolist(),
                    (discount_pct > 0).astype(int).tolist(),
                    strict=True,
                ),
            )

            on_hand, lead_time = build_inventory(
                rng, float(units[-30:].mean()), CATEGORIES[product.category].max_cover_days
            )
            conn.execute(
                "INSERT INTO inventory (sku, on_hand, lead_time_days) VALUES (?, ?, ?)",
                (product.sku, on_hand, lead_time),
            )

        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("products", "price_history", "daily_sales", "promotions", "inventory")
        }


def generate(
    path: Path = DEFAULT_DB_PATH,
    seed: int = DEFAULT_SEED,
    end_date: date = DEFAULT_END_DATE,
    days: int = HISTORY_DAYS,
) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    calendar = Calendar.ending(end_date, days)
    products = build_products(rng)

    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f"{path.name}.tmp")
    staging.unlink(missing_ok=True)
    try:
        counts = populate(staging, rng, calendar, products, seed, end_date)
        os.replace(staging, path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic retail SQLite database.")
    parser.add_argument("--output", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE)
    args = parser.parse_args()

    counts = generate(args.output, args.seed, args.end_date)
    print(f"Wrote {args.output}")
    for table, count in counts.items():
        print(f"  {table:<14}{count:>8}")


if __name__ == "__main__":
    main()
