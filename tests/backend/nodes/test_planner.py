from langgraph.types import Overwrite

from backend.nodes.planner import make_planner_node, render_system_prompt
from backend.schemas.plan import Plan
from tests.helpers import StubLLM, sales_step


def tools_section(prompt: str) -> list[str]:
    section = prompt.split("## Tools\n", 1)[1].split("## Catalog", 1)[0]
    return [line for line in section.splitlines() if line.strip()]


def test_system_prompt_states_the_data_date_and_limits() -> None:
    prompt = render_system_prompt()

    assert "Data is current as of 2026-08-31." in prompt
    assert "Use at most 6 steps." in prompt
    assert "{" not in prompt


def test_system_prompt_lists_every_tool_on_a_single_line() -> None:
    lines = tools_section(render_system_prompt())

    assert [line.split(":")[0] for line in lines] == [
        "- sales_summary",
        "- inventory_status",
        "- pricing_info",
        "- assortment_analysis",
        "- promotion_history",
        "- market_signals",
    ]
    assert all("  " not in line for line in lines)
    assert lines[0].startswith(
        "- sales_summary: Revenue, units, growth versus the previous period,"
    )


def test_system_prompt_lists_the_catalog_by_category() -> None:
    prompt = render_system_prompt()

    assert "Beverages: BEV-001 Assam Tea 500g, BEV-002 Filter Coffee Powder 200g," in prompt
    assert "Personal Care: PCR-001 Herbal Shampoo 340ml" in prompt
    assert prompt.count("HHD-") == 12


def test_planner_requests_a_plan_and_forwards_the_question() -> None:
    plan = Plan(objective="Decide on promo", steps=[sales_step()])
    llm = StubLLM(plan=plan)

    result = make_planner_node(llm)({"question": "Should we promote beverages?"})

    assert llm.requested_schema is Plan
    assert result["plan"] == plan
    system_message, human_message = llm.received_messages
    assert "merchandising" in system_message.content
    assert human_message.content == "Should we promote beverages?"


def test_planner_clears_results_from_a_previous_question() -> None:
    result = make_planner_node(StubLLM(plan=Plan(objective="x", steps=[sales_step()])))(
        {"question": "?"}
    )

    assert isinstance(result["tool_results"], Overwrite)
    assert result["tool_results"].value == {}


def test_planner_truncates_plans_over_the_step_limit(monkeypatch) -> None:
    monkeypatch.setenv("MAX_PLAN_STEPS", "2")
    from backend.config import get_settings

    get_settings.cache_clear()
    steps = [sales_step(days=days) for days in (7, 14, 30, 90)]

    result = make_planner_node(StubLLM(plan=Plan(objective="Too broad", steps=steps)))(
        {"question": "?"}
    )

    assert [step.args.days for step in result["plan"].steps] == [7, 14]


def test_planner_keeps_an_empty_plan_for_off_topic_questions() -> None:
    llm = StubLLM(plan=Plan(objective="Not retail", steps=[]))
    assert make_planner_node(llm)({"question": "Tell a joke"})["plan"].steps == []
