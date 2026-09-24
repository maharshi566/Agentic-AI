from collections.abc import Mapping, Sequence

import pytest

from backend.integrations.market_api import (
    CategoryDemand,
    CompetitorPrice,
    MockMarketDataClient,
    ProductRef,
)
from backend.tools.common import ToolInputError
from backend.tools.market_tool import market_signals


class FixedIndexClient:
    """Market client that quotes a competitor price giving each SKU a chosen price index."""

    source = "fixed"

    def __init__(self, indices: Mapping[str, float]) -> None:
        self.indices = indices

    def competitor_prices(self, products: Sequence[ProductRef]) -> dict[str, CompetitorPrice]:
        return {
            p.sku: CompetitorPrice(p.sku, p.our_price * 100 / self.indices[p.sku], 0.0, 0.0, 3)
            for p in products
        }

    def category_demand(self, category: str) -> CategoryDemand:
        return CategoryDemand(category, 1.5, 50)


def test_price_position_buckets_respect_the_parity_band(small_db, monkeypatch) -> None:
    indices = {
        "A-001": 120.0,
        "A-002": 105.0,
        "A-003": 95.0,
        "A-004": 80.0,
        "B-001": 100.0,
        "B-002": 100.0,
        "B-003": 100.0,
    }
    monkeypatch.setattr(
        "backend.tools.market_tool.get_market_client", lambda: FixedIndexClient(indices)
    )

    result = market_signals.invoke({"category": None, "sku": None})

    assert result["source"] == "fixed"
    assert result["price_position"] == {"above_market": 1, "at_parity": 5, "below_market": 1}
    assert (
        result["highest_price_index"][0]["sku"],
        result["highest_price_index"][0]["price_index"],
    ) == (
        "A-001",
        120.0,
    )
    assert (
        result["lowest_price_index"][0]["sku"],
        result["lowest_price_index"][0]["price_index"],
    ) == (
        "A-004",
        80.0,
    )
    assert len(result["highest_price_index"]) == 5
    assert len(result["lowest_price_index"]) == 2


def test_rows_use_the_current_price_and_anchor_competitors_to_the_first_price(small_db) -> None:
    result = market_signals.invoke({"category": None, "sku": "A-004"})
    row = result["highest_price_index"][0]
    quote = MockMarketDataClient().competitor_prices([ProductRef("A-004", "Dead", 33.0, 30.0)])[
        "A-004"
    ]

    assert row["our_price"] == 33.0
    assert row["competitor_avg_price"] == quote.avg_price
    assert row["price_index"] == round(33.0 / quote.avg_price * 100, 1)


def test_category_demand_is_listed_once_per_category_in_scope(small_db) -> None:
    assert len(market_signals.invoke({"category": "Alpha", "sku": None})["category_demand"]) == 1
    both = market_signals.invoke({"category": None, "sku": None})["category_demand"]
    assert [entry["category"] for entry in both] == ["Alpha", "Beta"]


def test_output_is_deterministic(small_db) -> None:
    args = {"category": "Alpha", "sku": None}
    assert market_signals.invoke(args) == market_signals.invoke(args)


def test_unknown_category_is_rejected(small_db) -> None:
    with pytest.raises(ToolInputError, match="Unknown category 'Gamma'"):
        market_signals.invoke({"category": "Gamma", "sku": None})


def test_mock_competitor_quotes_do_not_move_with_our_price() -> None:
    client = MockMarketDataClient()
    low = client.competitor_prices([ProductRef("X-1", "Item", 60.0, 100.0)])["X-1"]
    high = client.competitor_prices([ProductRef("X-1", "Item", 140.0, 100.0)])["X-1"]

    assert low == high
    assert 88 <= low.min_price <= low.avg_price <= low.max_price <= 112
    assert 3 <= low.competitor_count <= 6


def test_mock_category_demand_is_stable_and_bounded() -> None:
    client = MockMarketDataClient()
    first = client.category_demand("Dairy")

    assert (first.trend_pct_30d, first.search_interest_index) == (
        client.category_demand("dairy").trend_pct_30d,
        client.category_demand("dairy").search_interest_index,
    )
    assert -8 <= first.trend_pct_30d <= 15
    assert 35 <= first.search_interest_index <= 90
