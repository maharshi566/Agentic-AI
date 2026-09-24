import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.data.generate_data import (
    DEFAULT_END_DATE,
    DEFAULT_SEED,
    HISTORY_DAYS,
    PRICE_FLOOR_MARKUP,
    PROMO_DISCOUNTS,
    PROMO_MARGIN_BUFFER_PCT,
    generate,
)

TABLES = ("products", "price_history", "daily_sales", "inventory", "promotions")


def dump(path: Path) -> dict[str, list[tuple]]:
    with closing(sqlite3.connect(path)) as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in TABLES
        }


def test_dataset_shape(db: sqlite3.Connection) -> None:
    assert db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 80
    assert db.execute("SELECT COUNT(DISTINCT category) FROM products").fetchone()[0] == 6
    assert db.execute("SELECT COUNT(*) FROM daily_sales").fetchone()[0] == 80 * HISTORY_DAYS
    assert db.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 80
    assert db.execute("SELECT MIN(date), MAX(date) FROM daily_sales").fetchone() == (
        (DEFAULT_END_DATE - timedelta(days=HISTORY_DAYS - 1)).isoformat(),
        DEFAULT_END_DATE.isoformat(),
    )


def test_metadata_records_as_of_date_and_seed(db: sqlite3.Connection) -> None:
    meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
    assert meta == {
        "as_of_date": DEFAULT_END_DATE.isoformat(),
        "seed": str(DEFAULT_SEED),
        "currency": "INR",
    }


def test_same_seed_reproduces_every_table(tmp_path: Path) -> None:
    generate(tmp_path / "a.db", seed=7)
    generate(tmp_path / "b.db", seed=7)
    assert dump(tmp_path / "a.db") == dump(tmp_path / "b.db")


def test_different_seeds_produce_different_data(tmp_path: Path) -> None:
    generate(tmp_path / "a.db", seed=1)
    generate(tmp_path / "b.db", seed=2)

    first, second = dump(tmp_path / "a.db"), dump(tmp_path / "b.db")
    assert first["daily_sales"] != second["daily_sales"]
    assert first["promotions"] != second["promotions"]


def test_end_date_and_history_length_are_honoured(tmp_path: Path) -> None:
    path = tmp_path / "short.db"
    generate(path, end_date=date(2025, 6, 30), days=90)

    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM daily_sales"
        ).fetchone() == (
            "2025-04-02",
            "2025-06-30",
            80 * 90,
        )
        assert (
            conn.execute("SELECT value FROM meta WHERE key = 'as_of_date'").fetchone()[0]
            == "2025-06-30"
        )


@pytest.mark.parametrize("seed", [20, 48, 54])
def test_prices_never_fall_to_unit_cost(tmp_path: Path, seed: int) -> None:
    path = tmp_path / f"seed{seed}.db"
    generate(path, seed=seed)

    with closing(sqlite3.connect(path)) as conn:
        cheapest_markup = conn.execute(
            "SELECT MIN(ph.price / p.unit_cost) FROM price_history ph JOIN products p USING (sku)"
        ).fetchone()[0]

    assert cheapest_markup > 1.0
    assert cheapest_markup >= PRICE_FLOOR_MARKUP - 0.05


def test_promo_days_match_the_promotions_table(db: sqlite3.Connection) -> None:
    flagged = db.execute("SELECT COUNT(*) FROM daily_sales WHERE on_promo = 1").fetchone()[0]
    scheduled = db.execute(
        "SELECT SUM(julianday(end_date) - julianday(start_date) + 1) FROM promotions"
    ).fetchone()[0]
    assert flagged == scheduled


def test_promotions_never_overlap_for_the_same_sku(db: sqlite3.Connection) -> None:
    overlaps = db.execute(
        """
        SELECT COUNT(*) FROM promotions a JOIN promotions b
          ON a.sku = b.sku AND a.promo_id < b.promo_id
         AND a.start_date <= b.end_date AND b.start_date <= a.end_date
        """
    ).fetchone()[0]
    assert overlaps == 0


def test_promo_depth_stays_within_the_margin_headroom(db: sqlite3.Connection) -> None:
    rows = db.execute(
        """
        SELECT pm.discount_pct, (1 - p.unit_cost / first.price) * 100
        FROM promotions pm
        JOIN products p USING (sku)
        JOIN price_history first ON first.sku = pm.sku AND first.effective_date = (
            SELECT MIN(effective_date) FROM price_history WHERE sku = pm.sku)
        """
    ).fetchall()

    assert rows
    for discount, margin_pct in rows:
        assert discount <= margin_pct - PROMO_MARGIN_BUFFER_PCT or discount == min(PROMO_DISCOUNTS)


def test_perishable_stock_cover_is_capped(db: sqlite3.Connection) -> None:
    cover = db.execute(
        """
        SELECT MAX(i.on_hand * 1.0 / (
            SELECT AVG(units) FROM daily_sales s
            WHERE s.sku = i.sku AND s.date > date(?, '-30 days')))
        FROM inventory i JOIN products p USING (sku) WHERE p.category = 'Dairy'
        """,
        (DEFAULT_END_DATE.isoformat(),),
    ).fetchone()[0]
    assert cover <= 30.5


def test_a_failed_regeneration_keeps_the_existing_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "retail.db"
    generate(path, seed=1)
    before = dump(path)

    def explode(*args, **kwargs):
        raise RuntimeError("simulation failed")

    monkeypatch.setattr("backend.data.generate_data.simulate_demand", explode)

    with pytest.raises(RuntimeError, match="simulation failed"):
        generate(path, seed=2)

    assert dump(path) == before
    assert list(tmp_path.iterdir()) == [path]


def test_regeneration_replaces_an_existing_database(tmp_path: Path) -> None:
    path = tmp_path / "retail.db"
    generate(path, seed=1)
    generate(path, seed=2)

    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT value FROM meta WHERE key = 'seed'").fetchone()[0] == "2"
    assert list(tmp_path.iterdir()) == [path]
