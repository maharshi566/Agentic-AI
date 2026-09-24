from backend.tools.promotion_tool import promotion_history

STAR_PROMO = {
    "promo_id": 1,
    "sku": "A-001",
    "name": "Star",
    "start_date": "2026-01-10",
    "end_date": "2026-01-14",
    "discount_pct": 20.0,
    "unit_uplift_pct": 150.0,
    "daily_profit_change_pct": 25.0,
}
MID_PROMO = {
    "promo_id": 2,
    "sku": "A-002",
    "name": "Mid",
    "start_date": "2026-01-20",
    "end_date": "2026-01-22",
    "discount_pct": 10.0,
    "unit_uplift_pct": 0.0,
    "daily_profit_change_pct": -50.0,
}


def test_uplift_and_profit_change_are_measured_against_the_pre_promo_baseline(small_db) -> None:
    result = promotion_history.invoke({"category": None, "sku": "A-001"})

    assert result["promotion_count"] == 1
    assert result["most_recent"] == [STAR_PROMO]


def test_a_deeper_discount_without_uplift_destroys_profit(small_db) -> None:
    result = promotion_history.invoke({"category": None, "sku": "A-002"})
    assert result["most_recent"] == [MID_PROMO]


def test_store_wide_summary(small_db) -> None:
    result = promotion_history.invoke({"category": None, "sku": None})

    assert result["promotion_count"] == 2
    assert result["avg_discount_pct"] == 15.0
    assert result["avg_unit_uplift_pct"] == 75.0
    assert result["profitable_promo_share_pct"] == 50.0
    assert result["most_profitable"] == [STAR_PROMO, MID_PROMO]
    assert result["least_profitable"] == []
    assert result["most_recent"] == [MID_PROMO, STAR_PROMO]


def test_promotion_without_baseline_history_is_excluded(small_db) -> None:
    result = promotion_history.invoke({"category": "Beta", "sku": None})

    assert result["promotion_count"] == 0
    assert result["avg_unit_uplift_pct"] is None


def test_promotion_ending_after_the_as_of_date_is_excluded(small_db) -> None:
    result = promotion_history.invoke({"category": None, "sku": "A-003"})
    assert result["promotion_count"] == 0


def test_sku_without_promotions_returns_an_empty_summary(small_db) -> None:
    result = promotion_history.invoke({"category": None, "sku": "A-004"})

    assert result["promotion_count"] == 0
    assert result["avg_discount_pct"] is None
    assert result["profitable_promo_share_pct"] is None
    assert result["most_profitable"] == []
    assert result["most_recent"] == []


def test_rankings_on_generated_data_are_ordered_by_profit_change() -> None:
    result = promotion_history.invoke({"category": None, "sku": None})
    best = [p["daily_profit_change_pct"] for p in result["most_profitable"]]
    worst = [p["daily_profit_change_pct"] for p in result["least_profitable"]]

    assert len(best) == len(worst) == 3
    assert best == sorted(best, reverse=True)
    assert worst == sorted(worst)
    assert min(best) >= max(worst)
    assert 0 < result["profitable_promo_share_pct"] < 100


def test_baseline_ignores_days_that_were_themselves_on_promotion(edit_small_db) -> None:
    edit_small_db(
        "UPDATE daily_sales SET units = 50, on_promo = 1 "
        "WHERE sku = 'A-001' AND date IN ('2026-01-05', '2026-01-06')"
    )

    result = promotion_history.invoke({"category": None, "sku": "A-001"})

    assert result["most_recent"][0]["unit_uplift_pct"] == 150.0


def test_baseline_spans_exactly_the_28_days_before_the_promotion(edit_small_db) -> None:
    edit_small_db(
        "UPDATE daily_sales SET units = 20 "
        "WHERE sku = 'A-001' AND date BETWEEN '2025-12-13' AND '2025-12-31'"
    )

    result = promotion_history.invoke({"category": None, "sku": "A-001"})

    assert result["most_recent"][0]["unit_uplift_pct"] == 48.9
