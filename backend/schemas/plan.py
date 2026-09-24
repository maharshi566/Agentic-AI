from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.tools import (
    AssortmentArgs,
    InventoryArgs,
    MarketArgs,
    PricingArgs,
    PromotionArgs,
    SalesArgs,
)


class _Step(BaseModel):
    rationale: str = Field(
        description="One sentence on why this call is needed to answer the question."
    )


class SalesStep(_Step):
    tool: Literal["sales_summary"]
    args: SalesArgs


class InventoryStep(_Step):
    tool: Literal["inventory_status"]
    args: InventoryArgs


class PricingStep(_Step):
    tool: Literal["pricing_info"]
    args: PricingArgs


class AssortmentStep(_Step):
    tool: Literal["assortment_analysis"]
    args: AssortmentArgs


class PromotionStep(_Step):
    tool: Literal["promotion_history"]
    args: PromotionArgs


class MarketStep(_Step):
    tool: Literal["market_signals"]
    args: MarketArgs


PlanStep = SalesStep | InventoryStep | PricingStep | AssortmentStep | PromotionStep | MarketStep


class Plan(BaseModel):
    objective: str = Field(
        description="The business decision the question asks for, in one sentence."
    )
    steps: list[PlanStep] = Field(
        description="Independent tool calls that gather the evidence needed."
    )
