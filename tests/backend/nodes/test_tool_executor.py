from types import SimpleNamespace

from backend.nodes.tool_executor import run_tool
from tests.helpers import inventory_step, sales_step


def test_successful_call_is_keyed_by_index_and_tool_name() -> None:
    update = run_tool({"index": 2, "step": sales_step(category="Dairy", days=30)})

    result = update["tool_results"]["2_sales_summary"]
    assert result["index"] == 2
    assert result["tool"] == "sales_summary"
    assert result["args"] == {"category": "Dairy", "sku": None, "days": 30}
    assert result["error"] is None
    assert result["output"]["scope"]["category"] == "Dairy"


def test_recorded_arguments_are_the_effective_ones() -> None:
    result = run_tool({"index": 0, "step": sales_step(days=9999)})["tool_results"][
        "0_sales_summary"
    ]

    assert result["args"]["days"] == 365
    assert result["output"]["window"]["days"] == 365


def test_invalid_input_is_reported_as_an_error_result() -> None:
    step = inventory_step(category="Electronics")

    result = run_tool({"index": 0, "step": step})["tool_results"]["0_inventory_status"]

    assert result["output"] is None
    assert result["error"].startswith("Unknown category 'Electronics'. Valid categories: Beverages")


def test_unexpected_failures_are_contained_and_logged(monkeypatch, caplog) -> None:
    def explode(args: dict) -> None:
        raise RuntimeError("database offline")

    monkeypatch.setattr(
        "backend.nodes.tool_executor.TOOLS", {"sales_summary": SimpleNamespace(invoke=explode)}
    )

    result = run_tool({"index": 0, "step": sales_step()})["tool_results"]["0_sales_summary"]

    assert result["output"] is None
    assert result["error"] == "sales_summary failed unexpectedly."
    assert "database offline" in caplog.text
