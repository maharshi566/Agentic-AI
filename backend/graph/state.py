from typing import Annotated, Any, TypedDict

from backend.schemas.plan import Plan, PlanStep


class ToolResult(TypedDict):
    index: int
    tool: str
    args: dict[str, Any]
    output: dict[str, Any] | None
    error: str | None


class ToolTask(TypedDict):
    index: int
    step: PlanStep


def merge_tool_results(
    existing: dict[str, ToolResult], new: dict[str, ToolResult]
) -> dict[str, ToolResult]:
    return {**existing, **new}


class AgentState(TypedDict, total=False):
    question: str
    plan: Plan
    tool_results: Annotated[dict[str, ToolResult], merge_tool_results]
