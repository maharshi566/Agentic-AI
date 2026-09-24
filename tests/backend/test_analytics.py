import sqlite3
from pathlib import Path

import pytest

from backend import analytics
from backend.config import get_settings
from backend.data.generate_data import generate


def test_headline_matches_the_raw_sums(db: sqlite3.Connection) -> None:
    revenue, units, first, last = db.execute(
        "SELECT SUM(revenue), SUM(units), MIN(date), MAX(date) FROM daily_sales"
    ).fetchone()

    result = analytics.headline()

    assert result["revenue"] == pytest.approx(revenue)
    assert result["units"] == units
    assert (result["first_date"], result["last_date"]) == (first, last)
    assert result["products"] == 80


def test_headline_on_the_small_dataset_has_exact_values(small_db) -> None:
    result = analytics.headline()

    assert result["products"] == 7
    assert (result["first_date"], result["last_date"]) == ("2025-12-03", "2026-01-31")
    assert result["revenue"] == pytest.approx(87_152.0)
    assert result["units"] == 1_878
    assert result["gross_margin_pct"] == pytest.approx(28_025 / 87_152 * 100)
    assert result["promo_share_pct"] == pytest.approx(155 / 1_878 * 100)


def test_monthly_revenue_has_one_row_per_month_and_category() -> None:
    rows = analytics.revenue_by_month()

    assert len(rows) == 12 * 6
    assert rows == sorted(rows, key=lambda r: (r["month"], r["category"]))
    assert rows[0]["month"] == "2025-09"
    assert rows[-1]["month"] == "2026-08"


def test_monthly_revenue_matches_the_raw_sql(db: sqlite3.Connection) -> None:
    expected = db.execute(
        """
        SELECT SUM(s.revenue) / 100000.0 FROM daily_sales s JOIN products p USING (sku)
        WHERE p.category = 'Beverages' AND substr(s.date, 1, 7) = '2026-05'
        """
    ).fetchone()[0]

    row = next(
        r
        for r in analytics.revenue_by_month()
        if (r["month"], r["category"]) == ("2026-05", "Beverages")
    )

    assert row["revenue_lakh"] == pytest.approx(expected)


def test_monthly_revenue_on_the_small_dataset_is_split_by_month(small_db) -> None:
    rows = {(r["month"], r["category"]): r["revenue_lakh"] for r in analytics.revenue_by_month()}

    assert set(rows) == {
        ("2025-12", "Alpha"),
        ("2025-12", "Beta"),
        ("2026-01", "Alpha"),
        ("2026-01", "Beta"),
    }
    assert sum(v for (month, cat), v in rows.items() if cat == "Alpha") == pytest.approx(0.7814)
    assert sum(v for (month, cat), v in rows.items() if cat == "Beta") == pytest.approx(0.09012)


def test_weekday_demand_starts_on_monday_and_matches_the_raw_average(
    db: sqlite3.Connection,
) -> None:
    rows = analytics.weekday_demand()
    raw = dict(
        db.execute(
            "SELECT strftime('%w', date), AVG(units) FROM daily_sales GROUP BY strftime('%w', date)"
        ).fetchall()
    )
    by_day = {r["day"]: r["avg_units"] for r in rows}

    assert [r["day"] for r in rows] == [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    assert by_day["Sunday"] == pytest.approx(raw["0"])
    assert by_day["Monday"] == pytest.approx(raw["1"])
    assert by_day["Saturday"] == pytest.approx(raw["6"])


def test_category_summary_on_the_small_dataset_has_exact_values(small_db) -> None:
    alpha, beta = analytics.category_summary()

    assert (alpha["category"], alpha["products"], alpha["promotions"]) == ("Alpha", 4, 3)
    assert alpha["revenue_lakh"] == pytest.approx(0.7814)
    assert alpha["gross_margin_pct"] == pytest.approx(27_140 / 78_140 * 100)
    assert alpha["average_price"] == pytest.approx(50.75)
    assert (beta["category"], beta["products"], beta["promotions"]) == ("Beta", 3, 1)
    assert beta["revenue_lakh"] == pytest.approx(0.09012)
    assert beta["average_price"] == pytest.approx(10.0)


def test_category_summary_on_generated_data_is_sorted_by_revenue() -> None:
    rows = analytics.category_summary()
    revenues = [r["revenue_lakh"] for r in rows]

    assert len(rows) == 6
    assert revenues == sorted(revenues, reverse=True)
    assert all(r["promotions"] > 0 for r in rows)


def test_product_catalog_lists_every_sku_in_order() -> None:
    rows = analytics.product_catalog()

    assert len(rows) == 80
    assert [r["sku"] for r in rows] == sorted(r["sku"] for r in rows)
    assert rows[0] == {"sku": "BEV-001", "name": "Assam Tea 500g", "category": "Beverages"}


def test_data_signature_changes_when_the_database_file_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "signature.db"
    monkeypatch.setenv("DB_PATH", str(target))
    get_settings.cache_clear()
    generate(target, seed=1)
    before = analytics.data_signature()

    generate(target, seed=2)
    after = analytics.data_signature()

    assert before[0] == after[0] == str(target.resolve())
    assert before[1] != after[1]
