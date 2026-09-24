from datetime import timedelta

from backend.tools.pricing_tool import pricing_info
from tests.small_db import AS_OF


def test_single_sku_margin_and_history(small_db) -> None:
    result = pricing_info.invoke({"category": None, "sku": "A-001"})

    assert result["lowest_margin_skus"] == [
        {
            "sku": "A-001",
            "name": "Star",
            "price": 100.0,
            "unit_cost": 60.0,
            "margin_pct": 40.0,
            "last_change_date": None,
            "last_change_pct": None,
        }
    ]
    assert result["price_history"] == [{"effective_date": "2025-12-03", "price": 100.0}]


def test_price_change_uses_current_price_for_margin(small_db) -> None:
    result = pricing_info.invoke({"category": None, "sku": "A-004"})
    row = result["lowest_margin_skus"][0]

    assert (row["price"], row["margin_pct"]) == (33.0, 39.4)
    assert (row["last_change_date"], row["last_change_pct"]) == ("2026-01-10", 10.0)
    assert result["price_history"] == [
        {"effective_date": "2025-12-03", "price": 30.0},
        {"effective_date": "2026-01-10", "price": 33.0},
    ]
    assert result["repriced_last_90_days"] == 1


def test_category_summary_is_sorted_by_margin(small_db) -> None:
    result = pricing_info.invoke({"category": "Alpha", "sku": None})

    assert [row["sku"] for row in result["lowest_margin_skus"]] == [
        "A-002",
        "A-003",
        "A-004",
        "A-001",
    ]
    assert result["avg_margin_pct"] == 31.1
    assert result["min_margin_pct"] == 20.0
    assert result["max_margin_pct"] == 40.0
    assert result["repriced_last_90_days"] == 1
    assert "price_history" not in result


def test_margin_list_is_capped_at_ten_lowest_on_generated_data() -> None:
    result = pricing_info.invoke({"category": None, "sku": None})
    margins = [row["margin_pct"] for row in result["lowest_margin_skus"]]

    assert len(margins) == 10
    assert margins == sorted(margins)
    assert margins[0] == result["min_margin_pct"]


def test_repricing_window_covers_exactly_ninety_days(edit_small_db) -> None:
    inside = (AS_OF - timedelta(days=89)).isoformat()
    outside = (AS_OF - timedelta(days=90)).isoformat()
    edit_small_db(
        f"UPDATE price_history SET effective_date = '{inside}' WHERE sku = 'A-003'",
        "INSERT INTO price_history (sku, effective_date, price) "
        "VALUES ('A-003', '2025-10-01', 19.0)",
        f"UPDATE price_history SET effective_date = '{outside}' WHERE sku = 'A-002'",
        "INSERT INTO price_history (sku, effective_date, price) "
        "VALUES ('A-002', '2025-10-01', 45.0)",
    )

    result = pricing_info.invoke({"category": "Alpha", "sku": None})

    assert result["repriced_last_90_days"] == 2
