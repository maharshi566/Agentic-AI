from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import Field

from backend.schemas.plan import InventoryStep, MarketStep, Plan, SalesStep
from backend.schemas.tools import InventoryArgs, MarketArgs, SalesArgs


class StubLLM(BaseChatModel):
    """Chat model whose structured output is a fixed Plan; records what it was asked."""

    plan: Plan
    requested_schema: Any = None
    received_messages: list[BaseMessage] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise NotImplementedError

    def with_structured_output(self, schema, **kwargs) -> Runnable:
        self.requested_schema = schema

        def respond(messages: list[BaseMessage]) -> Plan:
            self.received_messages = list(messages)
            return self.plan

        return RunnableLambda(respond)


def sales_step(
    category: str | None = "Beverages", sku: str | None = None, days: int = 30
) -> SalesStep:
    return SalesStep(
        rationale="Baseline demand",
        tool="sales_summary",
        args=SalesArgs(category=category, sku=sku, days=days),
    )


def inventory_step(category: str | None = "Beverages", sku: str | None = None) -> InventoryStep:
    return InventoryStep(
        rationale="Stock position",
        tool="inventory_status",
        args=InventoryArgs(category=category, sku=sku),
    )


def market_step(category: str | None = "Beverages", sku: str | None = None) -> MarketStep:
    return MarketStep(
        rationale="Competitor prices",
        tool="market_signals",
        args=MarketArgs(category=category, sku=sku),
    )
