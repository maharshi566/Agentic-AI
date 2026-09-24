import argparse
import json
import logging
import sys

from backend.errors import EXPECTED_ERRORS, describe_error
from backend.graph.builder import build_graph
from backend.graph.state import AgentState, ToolResult


def _render_output(item: ToolResult) -> str:
    if item["error"]:
        return f"ERROR: {item['error']}"
    return json.dumps(item["output"], indent=2)


def format_report(state: AgentState) -> str:
    plan = state["plan"]
    lines = [f"Objective: {plan.objective}", "", "Plan"]
    for number, step in enumerate(plan.steps, start=1):
        lines.append(f"  {number}. {step.tool}: {step.rationale}")
        lines.append(f"     args: {json.dumps(step.args.model_dump())}")

    lines += ["", "Results"]
    for item in sorted(state.get("tool_results", {}).values(), key=lambda r: r["index"]):
        lines.append(f"  [{item['index'] + 1}] {item['tool']}")
        lines.extend(f"      {line}" for line in _render_output(item).splitlines())
    return "\n".join(lines)


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask the retail merchandising agent a question.")
    parser.add_argument(
        "question", help="Business question, e.g. 'Should we promote beverages next month?'"
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Print the raw result as JSON."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        state = build_graph().invoke({"question": args.question})
    except EXPECTED_ERRORS as exc:
        return _fail(describe_error(exc))

    if args.as_json:
        payload = {
            "plan": state["plan"].model_dump(),
            "tool_results": state.get("tool_results", {}),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
