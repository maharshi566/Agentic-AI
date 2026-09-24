import json
import os
import sqlite3
import subprocess
import sys

import httpx
import openai
import pytest
from langchain_openai.chat_models.base import OpenAIRefusalError
from pydantic import ValidationError

from backend import agent
from backend.graph.builder import build_graph
from backend.schemas.plan import Plan
from tests.helpers import StubLLM, inventory_step, sales_step

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def use_plan(monkeypatch: pytest.MonkeyPatch, plan: Plan) -> None:
    graph = build_graph(llm=StubLLM(plan=plan))
    monkeypatch.setattr(agent, "build_graph", lambda: graph)


def use_failure(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    class Failing:
        def invoke(self, _: dict) -> None:
            raise error

    monkeypatch.setattr(agent, "build_graph", lambda: Failing())


def invalid_plan_error() -> ValidationError:
    try:
        Plan.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a validation error")


def test_report_lists_the_plan_and_each_result_in_order(monkeypatch, capsys) -> None:
    plan = Plan(
        objective="Decide on a beverage promotion",
        steps=[sales_step(days=30), inventory_step(category="Electronics")],
    )
    use_plan(monkeypatch, plan)

    assert agent.main(["Should we promote beverages?"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("Objective: Decide on a beverage promotion")
    assert "1. sales_summary: Baseline demand" in out
    assert '     args: {"category": "Beverages", "sku": null, "days": 30}' in out
    assert "[1] sales_summary" in out
    assert "[2] inventory_status\n      ERROR: Unknown category 'Electronics'" in out
    assert out.index("[1] sales_summary") < out.index("[2] inventory_status")


def test_json_flag_prints_plan_and_results(monkeypatch, capsys) -> None:
    use_plan(monkeypatch, Plan(objective="Check sales", steps=[sales_step()]))

    assert agent.main(["question", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["plan"]["objective"] == "Check sales"
    assert payload["tool_results"]["0_sales_summary"]["output"]["scope"]["category"] == "Beverages"


def test_empty_plan_prints_only_the_objective(monkeypatch, capsys) -> None:
    use_plan(monkeypatch, Plan(objective="Not a retail question", steps=[]))

    assert agent.main(["Tell me a joke"]) == 0

    out = capsys.readouterr().out
    assert "Objective: Not a retail question" in out
    assert "[1]" not in out


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (RuntimeError("OPENAI_API_KEY is not set."), "OPENAI_API_KEY is not set."),
        (FileNotFoundError("Database not found at x.db."), "Database not found at x.db."),
        (
            openai.AuthenticationError(
                "bad key", response=httpx.Response(401, request=REQUEST), body=None
            ),
            "OpenAI rejected the API key. Check OPENAI_API_KEY.",
        ),
        (openai.APIConnectionError(request=REQUEST), "OpenAI request failed: Connection error."),
        (OpenAIRefusalError("The model refused."), "OpenAI request failed: The model refused."),
        (invalid_plan_error(), "The planner returned a plan that failed validation."),
        (sqlite3.DatabaseError("file is not a database"), "Database error: file is not a database"),
    ],
)
def test_known_failures_print_one_line_and_exit_with_one(
    monkeypatch, capsys, error, message
) -> None:
    use_failure(monkeypatch, error)

    assert agent.main(["question"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"error: {message}\n"


def test_report_is_printable_when_stdout_is_not_utf8() -> None:
    script = "\n".join(
        [
            "from backend import agent",
            "from backend.graph.builder import build_graph",
            "from backend.schemas.plan import Plan",
            "from tests.helpers import StubLLM",
            "plan = Plan(objective='Keep basket above \u20b9500', steps=[])",
            "graph = build_graph(llm=StubLLM(plan=plan))",
            "agent.build_graph = lambda: graph",
            "raise SystemExit(agent.main(['question']))",
        ]
    )
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONPATH": os.getcwd()}

    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, env=env, timeout=120, check=False
    )

    assert completed.returncode == 0, completed.stderr.decode()
    assert "\u20b9500" in completed.stdout.decode("utf-8")
