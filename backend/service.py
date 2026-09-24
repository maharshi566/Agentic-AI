"""The only backend module the frontend imports; a future HTTP API can expose the same functions."""

import shutil
from typing import Any

from backend import analytics
from backend.config import get_settings
from backend.data.generate_data import DEFAULT_SEED, generate
from backend.db import as_of_date, connect
from backend.errors import EXPECTED_ERRORS, describe_error
from backend.graph.builder import build_graph
from backend.graph.state import AgentState
from backend.llm import get_llm
from backend.llm import verify_api_key as _verify_api_key
from backend.tools import TOOLS
from backend.tools.common import ToolInputError

__all__ = [
    "DEFAULT_DATA_SEED",
    "AgentState",
    "EXPECTED_ERRORS",
    "ToolInputError",
    "analysis_names",
    "ask",
    "attention_summary",
    "category_summary",
    "data_signature",
    "data_status",
    "default_model",
    "describe_error",
    "environment_key_configured",
    "headline",
    "product_catalog",
    "regenerate_data",
    "revenue_by_month",
    "run_analysis",
    "verify_api_key",
    "weekday_demand",
]

headline = analytics.headline
revenue_by_month = analytics.revenue_by_month
weekday_demand = analytics.weekday_demand
category_summary = analytics.category_summary
product_catalog = analytics.product_catalog
data_signature = analytics.data_signature

DEFAULT_DATA_SEED = DEFAULT_SEED
BYTES_PER_MB = 1e6
BYTES_PER_GB = 1e9


def ask(question: str, api_key: str | None = None, model: str | None = None) -> AgentState:
    graph = build_graph(llm=get_llm(api_key=api_key, model=model))
    return graph.invoke({"question": question})


def analysis_names() -> list[str]:
    return list(TOOLS)


def run_analysis(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    return TOOLS[tool].invoke(args)


def attention_summary() -> dict[str, Any]:
    stock = run_analysis("inventory_status", {"category": None, "sku": None})
    promotions = run_analysis("promotion_history", {"category": None, "sku": None})
    return {
        "status_counts": stock["status_counts"],
        "stockout_risk": stock["stockout_risk"],
        "profitable_promo_share_pct": promotions["profitable_promo_share_pct"],
    }


def default_model() -> str:
    return get_settings().openai_model


def environment_key_configured() -> bool:
    return get_settings().openai_api_key is not None


def verify_api_key(api_key: str | None = None) -> None:
    _verify_api_key(api_key)


def data_status() -> dict[str, Any]:
    path = get_settings().db_path
    with connect() as conn:
        as_of = as_of_date(conn).isoformat()
    return {
        "path": str(path),
        "as_of": as_of,
        "size_mb": path.stat().st_size / BYTES_PER_MB,
        "free_gb": shutil.disk_usage(path.parent).free / BYTES_PER_GB,
    }


def regenerate_data(seed: int) -> None:
    generate(get_settings().db_path, seed=seed)
