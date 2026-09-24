from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.graph.routing import route_to_tools
from backend.graph.state import AgentState
from backend.llm import get_llm
from backend.nodes.planner import make_planner_node
from backend.nodes.tool_executor import run_tool


def build_graph(
    llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("planner", make_planner_node(llm or get_llm()))
    graph.add_node("run_tool", run_tool)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_to_tools, ["run_tool", END])
    graph.add_edge("run_tool", END)

    return graph.compile(checkpointer=checkpointer)
