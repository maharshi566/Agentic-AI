from typing import Any

import streamlit as st

EXAMPLES = (
    "Should we run a promotion on Beverages next month?",
    "Which Dairy products are at risk of running out of stock?",
    "Which Snacks should we consider removing from the range?",
    "Are our Household prices competitive?",
)

QUESTION = "question"
EXAMPLE = "example"

WHOLE_STORE = "Whole store"
CATEGORY = "One category"
PRODUCT = "One product"

DAYS_TOOLS = {"sales_summary", "assortment_analysis"}
CATEGORY_ONLY_TOOLS = {"assortment_analysis"}
DEFAULT_LOOKBACK_DAYS = 90
MIN_DAYS = 7
MAX_DAYS = 365


def use_example() -> None:
    if st.session_state.get(EXAMPLE):
        st.session_state[QUESTION] = st.session_state[EXAMPLE]


def build_arguments(
    tool: str, scope: str, category: str, product: str, days: int
) -> dict[str, Any]:
    if tool in CATEGORY_ONLY_TOOLS:
        return {"category": category, "days": days}
    args: dict[str, Any] = {
        "category": category if scope == CATEGORY else None,
        "sku": product if scope == PRODUCT else None,
    }
    if tool in DAYS_TOOLS:
        args["days"] = days
    return args
