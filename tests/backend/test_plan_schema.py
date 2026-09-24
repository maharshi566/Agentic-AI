import json
import typing

import pytest
from openai import pydantic_function_tool
from pydantic import ValidationError

from backend.schemas.plan import Plan, PlanStep
from backend.schemas.tools import AssortmentArgs, SalesArgs
from backend.tools import TOOLS

STEP_ARGS = {
    "sales_summary": {"category": "Beverages", "sku": None, "days": 30},
    "inventory_status": {"category": None, "sku": "BEV-001"},
    "pricing_info": {"category": "Dairy", "sku": None},
    "assortment_analysis": {"category": "Snacks", "days": 90},
    "promotion_history": {"category": None, "sku": None},
    "market_signals": {"category": "Household", "sku": None},
}


def test_every_step_type_matches_a_registered_tool() -> None:
    step_tools = {
        typing.get_args(step.model_fields["tool"].annotation)[0]
        for step in typing.get_args(PlanStep)
    }
    assert step_tools == set(TOOLS)


def test_each_tool_step_parses_into_its_own_model() -> None:
    payload = {
        "objective": "Check everything",
        "steps": [
            {"rationale": f"Use {tool}", "tool": tool, "args": args}
            for tool, args in STEP_ARGS.items()
        ],
    }

    plan = Plan.model_validate(payload)

    assert [type(step).__name__ for step in plan.steps] == [
        "SalesStep",
        "InventoryStep",
        "PricingStep",
        "AssortmentStep",
        "PromotionStep",
        "MarketStep",
    ]
    assert [step.args.model_dump() for step in plan.steps] == list(STEP_ARGS.values())


def test_step_missing_required_arguments_fails_validation() -> None:
    incomplete = {"rationale": "r", "tool": "sales_summary", "args": {"category": None}}

    with pytest.raises(ValidationError):
        Plan.model_validate({"objective": "x", "steps": [incomplete]})


def test_unknown_tool_name_fails_validation() -> None:
    unknown = {
        "rationale": "r",
        "tool": "weather_forecast",
        "args": {"category": None, "sku": None},
    }

    with pytest.raises(ValidationError):
        Plan.model_validate({"objective": "x", "steps": [unknown]})


@pytest.mark.parametrize(
    ("requested", "effective"),
    [(9999, 365), (365, 365), (30, 30), (7, 7), (1, 7), (-5, 7), ("45", 45)],
)
def test_lookback_days_are_clamped_when_arguments_are_validated(
    requested: object, effective: int
) -> None:
    assert SalesArgs(category=None, sku=None, days=requested).days == effective
    assert AssortmentArgs(category="Dairy", days=requested).days == effective


def test_schema_is_compatible_with_openai_strict_mode() -> None:
    schema = pydantic_function_tool(Plan)["function"]["parameters"]
    serialised = json.dumps(schema)

    assert schema["additionalProperties"] is False
    assert '"oneOf"' not in serialised
    assert '"default"' not in serialised
    assert '"minimum"' not in serialised
    assert '"maximum"' not in serialised
