import pytest

from backend.tools.assortment_tool import _abc_class, assortment_analysis
from backend.tools.common import ToolInputError


@pytest.mark.parametrize(
    ("cumulative_share_before", "expected"),
    [(0.0, "A"), (0.69, "A"), (0.70, "B"), (0.89, "B"), (0.90, "C"), (1.0, "C")],
)
def test_abc_class_boundaries(cumulative_share_before: float, expected: str) -> None:
    assert _abc_class(cumulative_share_before) == expected


def test_category_analysis_has_exact_totals_and_classes(small_db) -> None:
    result = assortment_analysis.invoke({"category": "Alpha", "days": 30})

    assert result["category"] == "Alpha"
    assert result["window"] == {"start": "2026-01-02", "end": "2026-01-31", "days": 30}
    assert result["sku_count"] == 4
    assert result["category_revenue"] == 41540.0
    assert result["category_gross_profit"] == 13790.0
    assert result["gross_margin_pct"] == 33.2
    assert result["class_summary"] == {
        "A": {"sku_count": 1, "revenue_share_pct": 84.3},
        "B": {"sku_count": 1, "revenue_share_pct": 14.3},
        "C": {"sku_count": 2, "revenue_share_pct": 1.4},
    }


def test_top_and_tail_skus_carry_profit_and_velocity(small_db) -> None:
    result = assortment_analysis.invoke({"category": "Alpha", "days": 30})

    assert result["top_skus"][0] == {
        "sku": "A-001",
        "name": "Star",
        "abc_class": "A",
        "revenue_share_pct": 84.3,
        "gross_profit": 12500.0,
        "units_per_day": 12.5,
    }
    assert [(row["sku"], row["gross_profit"]) for row in result["tail_skus"]] == [
        ("A-004", 0.0),
        ("A-003", 150.0),
    ]
    assert all(row["abc_class"] == "C" for row in result["tail_skus"])


def test_only_skus_with_no_units_are_reported_as_zero_sales(small_db) -> None:
    result = assortment_analysis.invoke({"category": "Alpha", "days": 30})
    assert result["zero_sales_skus"] == ["A-004"]


def test_category_is_required(small_db) -> None:
    with pytest.raises(ToolInputError, match="requires a category"):
        assortment_analysis.invoke({"category": "  ", "days": 30})


def test_unknown_category_is_rejected(small_db) -> None:
    with pytest.raises(ToolInputError, match="Unknown category 'Gamma'"):
        assortment_analysis.invoke({"category": "Gamma", "days": 30})


def test_generated_category_is_fully_classified() -> None:
    result = assortment_analysis.invoke({"category": "Snacks", "days": 90})
    summary = result["class_summary"]

    assert sum(summary[label]["sku_count"] for label in "ABC") == result["sku_count"] == 14
    assert sum(summary[label]["revenue_share_pct"] for label in "ABC") == pytest.approx(
        100, abs=0.5
    )
    assert summary["A"]["revenue_share_pct"] >= 70


def test_a_sku_with_a_trickle_of_sales_is_not_reported_as_zero_sales(edit_small_db) -> None:
    edit_small_db(
        "UPDATE daily_sales SET units = 0, revenue = 0 WHERE sku = 'A-003' AND date <> '2026-01-31'"
    )

    result = assortment_analysis.invoke({"category": "Alpha", "days": 30})

    assert result["zero_sales_skus"] == ["A-004"]
