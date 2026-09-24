from langgraph.checkpoint.memory import InMemorySaver

from backend.graph.builder import build_graph
from backend.schemas.plan import Plan
from tests.helpers import StubLLM, inventory_step, market_step, sales_step


def three_step_plan() -> Plan:
    return Plan(
        objective="Decide whether to promote beverages",
        steps=[sales_step(days=90), inventory_step(), market_step()],
    )


def thread(name: str) -> dict:
    return {"configurable": {"thread_id": name}}


def test_graph_runs_every_planned_tool_and_merges_results() -> None:
    graph = build_graph(llm=StubLLM(plan=three_step_plan()))

    state = graph.invoke({"question": "Should we promote beverages?"})

    assert set(state["tool_results"]) == {
        "0_sales_summary",
        "1_inventory_status",
        "2_market_signals",
    }
    assert all(result["error"] is None for result in state["tool_results"].values())
    assert state["tool_results"]["1_inventory_status"]["output"]["scope"]["category"] == "Beverages"


def test_graph_ends_without_tool_calls_for_an_empty_plan() -> None:
    graph = build_graph(llm=StubLLM(plan=Plan(objective="Off topic", steps=[])))

    state = graph.invoke({"question": "Tell me a joke"})

    assert state["plan"].steps == []
    assert state["tool_results"] == {}


def test_a_failing_tool_does_not_block_the_others() -> None:
    plan = Plan(
        objective="Mixed",
        steps=[sales_step(), inventory_step(category="Electronics"), market_step()],
    )

    results = build_graph(llm=StubLLM(plan=plan)).invoke({"question": "?"})["tool_results"]

    assert results["1_inventory_status"]["error"]
    assert results["0_sales_summary"]["output"] is not None
    assert results["2_market_signals"]["output"] is not None


def test_state_survives_checkpointing() -> None:
    plan = three_step_plan()
    graph = build_graph(llm=StubLLM(plan=plan), checkpointer=InMemorySaver())

    graph.invoke({"question": "Should we promote beverages?"}, thread("t1"))
    saved = graph.get_state(thread("t1")).values

    assert saved["plan"] == plan
    assert saved["question"] == "Should we promote beverages?"
    assert len(saved["tool_results"]) == 3


def test_a_follow_up_question_on_the_same_thread_starts_with_fresh_results() -> None:
    llm = StubLLM(plan=three_step_plan())
    graph = build_graph(llm=llm, checkpointer=InMemorySaver())
    config = thread("conversation")

    graph.invoke({"question": "first"}, config)
    llm.plan = Plan(objective="Follow-up", steps=[sales_step(category="Dairy")])
    second = graph.invoke({"question": "second"}, config)
    llm.plan = Plan(objective="Off topic", steps=[])
    third = graph.invoke({"question": "third"}, config)

    assert set(second["tool_results"]) == {"0_sales_summary"}
    assert second["tool_results"]["0_sales_summary"]["output"]["scope"]["category"] == "Dairy"
    assert third["tool_results"] == {}
