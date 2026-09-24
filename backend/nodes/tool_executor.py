import logging

from backend.graph.state import ToolResult, ToolTask
from backend.tools import TOOLS
from backend.tools.common import ToolInputError

logger = logging.getLogger(__name__)


def run_tool(task: ToolTask) -> dict[str, dict[str, ToolResult]]:
    step = task["step"]
    args = step.args.model_dump()
    output = None
    error = None

    try:
        output = TOOLS[step.tool].invoke(args)
    except ToolInputError as exc:
        error = str(exc)
    except Exception:
        logger.exception("Tool %s failed", step.tool)
        error = f"{step.tool} failed unexpectedly."

    result = ToolResult(index=task["index"], tool=step.tool, args=args, output=output, error=error)
    return {"tool_results": {f"{task['index']}_{step.tool}": result}}
