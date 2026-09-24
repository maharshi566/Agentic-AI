import pytest

from backend.tools import TOOLS
from frontend.forms import CATEGORY, PRODUCT, WHOLE_STORE, build_arguments
from frontend.labels import (
    TOOL_LABELS,
    TOOL_QUESTIONS,
    describe_arguments,
    describe_scope,
    inr,
    pct,
    signed_pct,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "₹0"),
        (999.6, "₹1,000"),
        (54321, "₹54,321"),
        (100_000, "₹1.0 lakh"),
        (6_810_000, "₹68.1 lakh"),
        (10_000_000, "₹1.00 crore"),
        (126_500_000, "₹12.65 crore"),
        (-250_000, "₹-2.5 lakh"),
    ],
)
def test_inr_uses_lakh_and_crore(value: float, expected: str) -> None:
    assert inr(value) == expected


def test_percent_helpers_handle_missing_values() -> None:
    assert pct(12.34) == "12.3%"
    assert pct(None) == "n/a"
    assert signed_pct(5.0) == "+5.0%"
    assert signed_pct(-1.7) == "-1.7%"
    assert signed_pct(None) is None


def test_scope_descriptions() -> None:
    whole = {"category": None, "sku": None, "sku_count": 80}
    category = {"category": "Dairy", "sku": None, "sku_count": 13}
    product = {"category": "Dairy", "sku": "DRY-001", "sku_count": 1}

    assert describe_scope(whole) == "Whole store (80 products)"
    assert describe_scope(category) == "Dairy (13 products)"
    assert describe_scope(product) == "DRY-001 (Dairy)"


def test_argument_descriptions_prefer_the_most_specific_scope() -> None:
    assert describe_arguments({"category": "Dairy", "sku": None, "days": 30}) == (
        "Dairy · last 30 days"
    )
    assert describe_arguments({"category": None, "sku": "DRY-001"}) == "DRY-001"
    assert describe_arguments({"category": None, "sku": None}) == "Whole store"


def test_every_tool_has_a_business_label_and_question() -> None:
    assert set(TOOL_LABELS) == set(TOOLS) == set(TOOL_QUESTIONS)


@pytest.mark.parametrize(
    ("tool", "scope", "expected"),
    [
        ("sales_summary", WHOLE_STORE, {"category": None, "sku": None, "days": 60}),
        ("sales_summary", CATEGORY, {"category": "Dairy", "sku": None, "days": 60}),
        ("sales_summary", PRODUCT, {"category": None, "sku": "DRY-001", "days": 60}),
        ("pricing_info", PRODUCT, {"category": None, "sku": "DRY-001"}),
        ("inventory_status", CATEGORY, {"category": "Dairy", "sku": None}),
        ("assortment_analysis", WHOLE_STORE, {"category": "Dairy", "days": 60}),
    ],
)
def test_form_values_become_tool_arguments(tool: str, scope: str, expected: dict) -> None:
    assert build_arguments(tool, scope, "Dairy", "DRY-001", 60) == expected


def test_every_built_argument_set_is_accepted_by_its_tool() -> None:
    for tool in TOOLS:
        for scope in (WHOLE_STORE, CATEGORY, PRODUCT):
            args = build_arguments(tool, scope, "Dairy", "DRY-001", 60)
            TOOLS[tool].args_schema.model_validate(args)
