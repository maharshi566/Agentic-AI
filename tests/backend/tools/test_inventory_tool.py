import sqlite3

import pytest

from backend.tools.inventory_tool import inventory_status


def test_statuses_cover_and_boundaries(small_db) -> None:
    result = inventory_status.invoke({"category": None, "sku": None})
    items = {item["sku"]: item for item in result["items"]}

    assert items["A-001"] == {
        "sku": "A-001",
        "name": "Star",
        "on_hand": 30,
        "avg_daily_units": 12.5,
        "days_of_cover": 2.4,
        "lead_time_days": 5,
        "status": "stockout_risk",
    }
    assert (items["A-002"]["days_of_cover"], items["A-002"]["status"]) == (100.0, "overstock")
    assert (items["A-003"]["days_of_cover"], items["A-003"]["status"]) == (30.0, "healthy")
    assert (items["A-004"]["days_of_cover"], items["A-004"]["status"]) == (None, "no_recent_demand")
    assert (items["B-002"]["days_of_cover"], items["B-002"]["status"]) == (3.0, "healthy")
    assert (items["B-003"]["days_of_cover"], items["B-003"]["status"]) == (60.0, "healthy")


def test_summary_lists_and_counts(small_db) -> None:
    result = inventory_status.invoke({"category": None, "sku": None})

    assert result["status_counts"] == {
        "healthy": 4,
        "stockout_risk": 1,
        "overstock": 1,
        "no_recent_demand": 1,
    }
    assert [item["sku"] for item in result["stockout_risk"]] == ["A-001"]
    assert [item["sku"] for item in result["overstock"]] == ["A-002"]
    assert result["as_of"] == "2026-01-31"
    assert result["demand_window_days"] == 30


def test_scope_limits_the_rows(small_db) -> None:
    result = inventory_status.invoke({"category": "Beta", "sku": None})

    assert result["scope"]["sku_count"] == 3
    assert result["stockout_risk"] == []
    assert result["overstock"] == []
    assert sorted(item["sku"] for item in result["items"]) == ["B-001", "B-002", "B-003"]


def test_item_detail_is_only_listed_for_small_scopes() -> None:
    assert "items" in inventory_status.invoke({"category": None, "sku": "DRY-001"})
    assert "items" not in inventory_status.invoke({"category": "Dairy", "sku": None})
    assert "items" not in inventory_status.invoke({"category": None, "sku": None})


def test_risk_lists_are_sorted_capped_and_respect_thresholds_on_generated_data() -> None:
    result = inventory_status.invoke({"category": None, "sku": None})

    at_risk = result["stockout_risk"]
    overstock = result["overstock"]
    assert 0 < len(at_risk) <= 10
    assert 0 < len(overstock) <= 10
    assert all(item["days_of_cover"] < item["lead_time_days"] for item in at_risk)
    assert all(item["days_of_cover"] > 60 for item in overstock)
    assert [i["days_of_cover"] for i in at_risk] == sorted(i["days_of_cover"] for i in at_risk)
    assert [i["days_of_cover"] for i in overstock] == sorted(
        (i["days_of_cover"] for i in overstock), reverse=True
    )


def test_days_of_cover_matches_raw_sql_on_generated_data(db: sqlite3.Connection) -> None:
    on_hand = db.execute("SELECT on_hand FROM inventory WHERE sku = 'DRY-001'").fetchone()[0]
    units = db.execute(
        "SELECT SUM(units) FROM daily_sales WHERE sku = 'DRY-001' "
        "AND date BETWEEN date('2026-08-31', '-29 days') AND '2026-08-31'"
    ).fetchone()[0]

    result = inventory_status.invoke({"category": None, "sku": "DRY-001"})

    assert result["items"][0]["days_of_cover"] == pytest.approx(on_hand / (units / 30), abs=0.05)


def test_overstock_begins_just_above_sixty_days_of_cover(edit_small_db) -> None:
    edit_small_db("UPDATE inventory SET on_hand = 305 WHERE sku = 'B-003'")

    result = inventory_status.invoke({"category": "Beta", "sku": None})

    item = next(i for i in result["items"] if i["sku"] == "B-003")
    assert (item["days_of_cover"], item["status"]) == (61.0, "overstock")
