import pytest
from streamlit.testing.v1 import AppTest

from backend.tools import TOOLS
from frontend.labels import inr
from tests.frontend.conftest import TIMEOUT_SECONDS, metrics

SCRIPT = (
    "from backend.tools import TOOLS\n"
    "from frontend.components import render_output\n"
    "render_output({tool!r}, TOOLS[{tool!r}].invoke({args!r}))\n"
)

CASES = {
    "sales_summary": (
        {"category": "Beverages", "sku": None, "days": 30},
        {"Revenue", "Units sold", "Units per day", "Sold on promotion"},
    ),
    "inventory_status": (
        {"category": None, "sku": None},
        {"Healthy", "Stockout risk", "Overstocked", "No recent demand"},
    ),
    "pricing_info": (
        {"category": None, "sku": "BEV-004"},
        {"Average margin", "Lowest margin", "Highest margin", "Repriced in last 90 days"},
    ),
    "assortment_analysis": (
        {"category": "Snacks", "days": 90},
        {"Category revenue", "Gross profit", "Gross margin", "Products"},
    ),
    "promotion_history": (
        {"category": None, "sku": None},
        {
            "Promotions measured",
            "Average discount",
            "Average unit uplift",
            "Increased daily profit",
        },
    ),
    "market_signals": (
        {"category": "Dairy", "sku": None},
        {"Demand trend (30 days)", "Search interest (0-100)"},
    ),
}


def render(tool: str, args: dict) -> AppTest:
    script = SCRIPT.format(tool=tool, args=args)
    return AppTest.from_string(script, default_timeout=TIMEOUT_SECONDS).run()


def markdown(at: AppTest) -> list[str]:
    return [m.value for m in at.markdown]


def test_cases_cover_every_tool() -> None:
    assert set(CASES) == set(TOOLS)


@pytest.mark.parametrize("tool", list(CASES))
def test_each_analysis_renders_its_key_figures(tool: str) -> None:
    args, expected_labels = CASES[tool]

    at = render(tool, args)

    assert not at.exception
    assert expected_labels <= set(metrics(at))
    assert len(at.dataframe) >= 1


def test_sales_metrics_show_the_tool_figures_and_growth() -> None:
    args = {"category": "Beverages", "sku": None, "days": 30}
    output = TOOLS["sales_summary"].invoke(args)

    at = render("sales_summary", args)

    revenue = next(m for m in at.metric if m.label == "Revenue")
    assert revenue.value == inr(output["revenue"])
    assert revenue.delta == f"{output['revenue_change_pct_vs_previous_period']:+.1f}%"
    assert next(m for m in at.metric if m.label == "Units sold").value == f"{output['units']:,}"


def test_sales_explains_why_growth_is_missing() -> None:
    at = render("sales_summary", {"category": "Dairy", "sku": None, "days": 365})

    assert any("previous period is not fully covered" in c.value for c in at.caption)
    assert not next(m for m in at.metric if m.label == "Revenue").delta


def test_inventory_lists_all_products_for_a_single_sku() -> None:
    at = render("inventory_status", {"category": None, "sku": "DRY-001"})

    assert "**Products**" in markdown(at)
    assert len(at.dataframe) == 1


def test_inventory_lists_risk_groups_for_a_wide_scope() -> None:
    at = render("inventory_status", {"category": None, "sku": None})

    assert "**Products likely to run out before restocking**" in markdown(at)
    assert "**Overstocked products**" in markdown(at)


def test_pricing_for_one_product_includes_price_history() -> None:
    at = render("pricing_info", {"category": None, "sku": "BEV-004"})
    assert "**Price history**" in markdown(at)


def test_pricing_for_a_category_has_no_price_history() -> None:
    at = render("pricing_info", {"category": "Dairy", "sku": None})
    assert "**Price history**" not in markdown(at)


def test_missing_price_changes_are_shown_as_a_dash(small_db) -> None:
    unchanged = render("pricing_info", {"category": None, "sku": "A-001"})
    changed = render("pricing_info", {"category": None, "sku": "A-004"})

    assert unchanged.dataframe[0].value["Last price change"].tolist() == ["-"]
    assert changed.dataframe[0].value["Last price change"].tolist() == ["2026-01-10"]


def test_promotions_without_history_show_a_message(small_db) -> None:
    at = render("promotion_history", {"category": None, "sku": "A-004"})

    assert any("No completed promotions" in i.value for i in at.info)
    assert not at.metric


def test_range_analysis_warns_about_products_with_no_sales(small_db) -> None:
    at = render("assortment_analysis", {"category": "Alpha", "days": 30})

    assert [w.value for w in at.warning] == ["No sales in this period: A-004"]


def test_market_uses_metrics_for_one_category_and_a_table_for_many() -> None:
    single = render("market_signals", {"category": "Dairy", "sku": None})
    many = render("market_signals", {"category": None, "sku": None})

    assert "Demand trend (30 days)" in metrics(single)
    assert not many.metric
    assert "**Demand by category**" in markdown(many)
