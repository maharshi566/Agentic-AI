import random
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol


@dataclass(frozen=True)
class ProductRef:
    """`reference_price` anchors the mock market; a real provider would ignore it."""

    sku: str
    name: str
    our_price: float
    reference_price: float


@dataclass(frozen=True)
class CompetitorPrice:
    sku: str
    avg_price: float
    min_price: float
    max_price: float
    competitor_count: int


@dataclass(frozen=True)
class CategoryDemand:
    category: str
    trend_pct_30d: float
    search_interest_index: int


class MarketDataClient(Protocol):
    source: str

    def competitor_prices(self, products: Sequence[ProductRef]) -> dict[str, CompetitorPrice]: ...

    def category_demand(self, category: str) -> CategoryDemand: ...


def _seeded(key: str) -> random.Random:
    return random.Random(zlib.crc32(key.encode()))


class MockMarketDataClient:
    """Deterministic stand-in for an external market data provider."""

    source = "mock"

    def competitor_prices(self, products: Sequence[ProductRef]) -> dict[str, CompetitorPrice]:
        result = {}
        for product in products:
            rng = _seeded(f"price:{product.sku}")
            prices = [
                round(product.reference_price * rng.uniform(0.88, 1.12), 2)
                for _ in range(rng.randint(3, 6))
            ]
            result[product.sku] = CompetitorPrice(
                sku=product.sku,
                avg_price=round(sum(prices) / len(prices), 2),
                min_price=min(prices),
                max_price=max(prices),
                competitor_count=len(prices),
            )
        return result

    def category_demand(self, category: str) -> CategoryDemand:
        rng = _seeded(f"demand:{category.lower()}")
        return CategoryDemand(
            category=category,
            trend_pct_30d=round(rng.uniform(-8, 15), 1),
            search_interest_index=rng.randint(35, 90),
        )


@lru_cache
def get_market_client() -> MarketDataClient:
    return MockMarketDataClient()
