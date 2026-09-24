from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

MIN_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 365

CATEGORY_DESCRIPTION = "Product category name exactly as listed in the catalog, or null."
SKU_DESCRIPTION = "SKU code (for example 'BEV-001') from the catalog, or null."
DAYS_DESCRIPTION = "Lookback window in days, between 7 and 365."


def _clamp_days(value: object) -> int:
    return max(MIN_WINDOW_DAYS, min(int(value), MAX_WINDOW_DAYS))


LookbackDays = Annotated[int, BeforeValidator(_clamp_days)]


class SalesArgs(BaseModel):
    category: str | None = Field(description=CATEGORY_DESCRIPTION)
    sku: str | None = Field(description=SKU_DESCRIPTION)
    days: LookbackDays = Field(description=DAYS_DESCRIPTION)


class InventoryArgs(BaseModel):
    category: str | None = Field(description=CATEGORY_DESCRIPTION)
    sku: str | None = Field(description=SKU_DESCRIPTION)


class PricingArgs(BaseModel):
    category: str | None = Field(description=CATEGORY_DESCRIPTION)
    sku: str | None = Field(description=SKU_DESCRIPTION)


class AssortmentArgs(BaseModel):
    category: str = Field(description="Product category name exactly as listed in the catalog.")
    days: LookbackDays = Field(description=DAYS_DESCRIPTION)


class PromotionArgs(BaseModel):
    category: str | None = Field(description=CATEGORY_DESCRIPTION)
    sku: str | None = Field(description=SKU_DESCRIPTION)


class MarketArgs(BaseModel):
    category: str | None = Field(description=CATEGORY_DESCRIPTION)
    sku: str | None = Field(description=SKU_DESCRIPTION)
