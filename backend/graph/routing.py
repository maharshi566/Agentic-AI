from langgraph.graph import END
from langgraph.types import Send

from backend.graph.state import AgentState


def route_to_tools(state: AgentState) -> list[Send] | str:
    steps = state["plan"].steps
    if not steps:
        return END
    return [Send("run_tool", {"index": index, "step": step}) for index, step in enumerate(steps)]
