import logging
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Overwrite

from backend.config import get_settings
from backend.db import as_of_date, connect, list_catalog
from backend.graph.state import AgentState
from backend.prompts import load_prompt
from backend.schemas.plan import Plan
from backend.tools import TOOLS

logger = logging.getLogger(__name__)


def render_system_prompt() -> str:
    with connect() as conn:
        as_of = as_of_date(conn)
        catalog = list_catalog(conn)

    tools = "\n".join(
        f"- {tool.name}: {' '.join(tool.description.split())}" for tool in TOOLS.values()
    )
    catalog_text = "\n".join(
        f"{category}: " + ", ".join(f"{sku} {name}" for sku, name in items)
        for category, items in catalog.items()
    )
    return load_prompt("planner").format(
        as_of_date=as_of.isoformat(),
        tools=tools,
        catalog=catalog_text,
        max_steps=get_settings().max_plan_steps,
    )


def make_planner_node(llm: BaseChatModel) -> Callable[[AgentState], dict[str, Any]]:
    structured_llm = llm.with_structured_output(Plan)

    def plan_question(state: AgentState) -> dict[str, Any]:
        plan = structured_llm.invoke(
            [SystemMessage(render_system_prompt()), HumanMessage(state["question"])]
        )
        max_steps = get_settings().max_plan_steps
        if len(plan.steps) > max_steps:
            logger.warning("Plan had %d steps; truncating to %d", len(plan.steps), max_steps)
            plan = plan.model_copy(update={"steps": plan.steps[:max_steps]})
        return {"plan": plan, "tool_results": Overwrite({})}

    return plan_question
