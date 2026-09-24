import json

import httpx
import pytest
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import OpenAIRefusalError
from pydantic import ValidationError

from backend.nodes.planner import make_planner_node
from backend.schemas.plan import MarketStep, SalesStep

PLAN_REPLY = {
    "objective": "Decide whether to promote beverages",
    "steps": [
        {
            "rationale": "Recent demand",
            "tool": "sales_summary",
            "args": {"category": "Beverages", "sku": None, "days": 30},
        },
        {
            "rationale": "Competitor prices",
            "tool": "market_signals",
            "args": {"category": "Beverages", "sku": None},
        },
    ],
}


def completion(content: str | None, refusal: str | None = None) -> httpx.Response:
    message = {"role": "assistant", "content": content, "refusal": refusal}
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def planner_for(reply: httpx.Response, requests: list[dict] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(json.loads(request.content))
        return reply

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key="sk-test",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return make_planner_node(llm)


def test_request_asks_for_strict_json_schema_output() -> None:
    requests: list[dict] = []
    planner_for(completion(json.dumps(PLAN_REPLY)), requests)({"question": "Promote beverages?"})

    body = requests[0]
    assert body["model"] == "gpt-4o-mini"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "Plan"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][1]["content"] == "Promote beverages?"
    assert "BEV-004 Cola 750ml" in body["messages"][0]["content"]


def test_reply_is_parsed_into_typed_steps() -> None:
    plan = planner_for(completion(json.dumps(PLAN_REPLY)))({"question": "?"})["plan"]

    assert [type(step) for step in plan.steps] == [SalesStep, MarketStep]
    assert plan.steps[0].args.days == 30


def test_out_of_range_lookback_in_a_reply_is_clamped() -> None:
    reply = json.loads(json.dumps(PLAN_REPLY))
    reply["steps"][0]["args"]["days"] = 5000

    plan = planner_for(completion(json.dumps(reply)))({"question": "?"})["plan"]

    assert plan.steps[0].args.days == 365


def test_refusal_is_raised() -> None:
    with pytest.raises(OpenAIRefusalError):
        planner_for(completion(None, refusal="I can't help with that."))({"question": "?"})


def test_reply_with_missing_arguments_fails_validation() -> None:
    reply = json.loads(json.dumps(PLAN_REPLY))
    del reply["steps"][0]["args"]["days"]

    with pytest.raises(ValidationError):
        planner_for(completion(json.dumps(reply)))({"question": "?"})
