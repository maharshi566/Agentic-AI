import sqlite3

import pytest

from backend.tools.common import ToolInputError
from backend.tools.sales_tool import sales_summary


def test_single_sku_totals_and_previous_period(small_db) -> None:
    result = sales_summary.invoke({"category": None, "sku": "B-001", "days": 30})

    assert result["window"] == {"start": "2026-01-02", "end": "2026-01-31", "days": 30}
    assert result["revenue"] == 1500.0
    assert result["units"] == 150
    assert result["avg_daily_units"] == 5.0
    assert result["promo_units_share_pct"] == 0.0
    assert result["revenue_change_pct_vs_previous_period"] == -0.8
    assert result["units_change_pct_vs_previous_period"] == -2.0


def test_growth_is_omitted_when_the_previous_period_is_not_fully_covered(small_db) -> None:
    result = sales_summary.invoke({"category": None, "sku": "B-001", "days": 31})

    assert result["revenue_change_pct_vs_previous_period"] is None
    assert result["units_change_pct_vs_previous_period"] is None


def test_promo_days_are_counted_in_totals_and_promo_share(small_db) -> None:
    result = sales_summary.invoke({"category": None, "sku": "A-001", "days": 30})

    assert result["units"] == 375
    assert result["revenue"] == 35000.0
    assert result["promo_units_share_pct"] == 33.3


def test_category_rankings_include_every_sku_when_the_category_is_small(small_db) -> None:
    result = sales_summary.invoke({"category": "Alpha", "sku": None, "days": 30})

    assert [r["sku"] for r in result["top_skus"]] == ["A-001", "A-002", "A-003", "A-004"]
    assert result["bottom_skus"] == []
    assert result["top_skus"][0] == {
        "sku": "A-001",
        "name": "Star",
        "revenue": 35000.0,
        "units": 375,
    }


def test_store_wide_rankings_break_revenue_ties_by_sku(small_db) -> None:
    result = sales_summary.invoke({"category": None, "sku": None, "days": 30})

    assert [r["sku"] for r in result["top_skus"]] == ["A-001", "A-002", "B-001", "B-002", "B-003"]
    assert [r["sku"] for r in result["bottom_skus"]] == ["A-004", "A-003"]


def test_category_match_is_case_insensitive(small_db) -> None:
    result = sales_summary.invoke({"category": "aLpHa", "sku": None, "days": 30})
    assert result["scope"] == {"category": "Alpha", "sku": None, "sku_count": 4}


def test_sku_can_be_given_as_code_in_any_case_or_as_product_name(small_db) -> None:
    by_code = sales_summary.invoke({"category": None, "sku": "a-001", "days": 30})
    by_name = sales_summary.invoke({"category": None, "sku": "star", "days": 30})

    assert by_code == by_name
    assert by_code["scope"] == {"category": "Alpha", "sku": "A-001", "sku_count": 1}


@pytest.mark.parametrize(("requested", "effective"), [(5000, 365), (1, 7), (7, 7), (365, 365)])
def test_window_is_clamped_to_the_supported_range(requested: int, effective: int) -> None:
    result = sales_summary.invoke({"category": None, "sku": None, "days": requested})
    assert result["window"]["days"] == effective


def test_unknown_category_lists_valid_options(small_db) -> None:
    with pytest.raises(ToolInputError, match="Valid categories: Alpha, Beta"):
        sales_summary.invoke({"category": "Gamma", "sku": None, "days": 30})


def test_unknown_sku_is_rejected(small_db) -> None:
    with pytest.raises(ToolInputError, match="Unknown SKU 'ZZZ-999'"):
        sales_summary.invoke({"category": None, "sku": "ZZZ-999", "days": 30})


def test_sku_from_a_different_category_is_rejected(small_db) -> None:
    with pytest.raises(ToolInputError, match="A-001 belongs to Alpha, not 'Beta'"):
        sales_summary.invoke({"category": "Beta", "sku": "A-001", "days": 30})


def test_category_totals_match_raw_sql_on_generated_data(db: sqlite3.Connection) -> None:
    result = sales_summary.invoke({"category": "Beverages", "sku": None, "days": 30})
    revenue, units = db.execute(
        """
        SELECT SUM(s.revenue), SUM(s.units)
        FROM daily_sales s JOIN products p USING (sku)
        WHERE p.category = 'Beverages'
          AND s.date BETWEEN date('2026-08-31', '-29 days') AND '2026-08-31'
        """
    ).fetchone()

    assert result["revenue"] == pytest.approx(revenue, abs=0.01)
    assert result["units"] == units


@pytest.mark.parametrize("days", [30, 90, 182])
def test_growth_matches_raw_sql_on_generated_data(db: sqlite3.Connection, days: int) -> None:
    result = sales_summary.invoke({"category": "Dairy", "sku": None, "days": days})
    current, previous = (
        db.execute(
            """
            SELECT SUM(s.revenue)
            FROM daily_sales s JOIN products p USING (sku)
            WHERE p.category = 'Dairy'
              AND s.date BETWEEN date('2026-08-31', ?) AND date('2026-08-31', ?)
            """,
            (f"-{start} days", f"-{end} days"),
        ).fetchone()[0]
        for start, end in ((days - 1, 0), (2 * days - 1, days))
    )

    assert result["revenue_change_pct_vs_previous_period"] == round(
        (current - previous) / previous * 100, 1
    )


def test_growth_is_never_reported_beyond_half_the_history() -> None:
    for days in (183, 250, 364, 365):
        result = sales_summary.invoke({"category": "Dairy", "sku": None, "days": days})
        assert result["revenue_change_pct_vs_previous_period"] is None
