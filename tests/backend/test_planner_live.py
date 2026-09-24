import pytest

from backend.config import Settings
from backend.graph.builder import build_graph
from backend.tools import TOOLS

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(Settings().openai_api_key is None, reason="OPENAI_API_KEY is not set"),
]


def test_promotion_question_produces_a_valid_executable_plan() -> None:
    state = build_graph().invoke({"question": "Should we run a promotion on Beverages next month?"})

    tools_planned = {step.tool for step in state["plan"].steps}
    assert tools_planned <= set(TOOLS)
    assert {"sales_summary", "promotion_history"} <= tools_planned
    assert all(result["error"] is None for result in state["tool_results"].values())


def test_off_topic_question_produces_no_steps() -> None:
    state = build_graph().invoke({"question": "Write me a poem about the ocean."})
    assert state["plan"].steps == []
