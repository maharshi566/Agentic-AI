from collections.abc import Callable
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60


def load(page: str) -> AppTest:
    return AppTest.from_file(str(ROOT / page), default_timeout=TIMEOUT_SECONDS)


def button(at: AppTest, label: str) -> Button:
    return next(b for b in at.button if b.label == label)


def metrics(at: AppTest) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


@pytest.fixture
def without_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the UI believe no OPENAI_API_KEY is configured in the environment."""
    monkeypatch.setattr("backend.service.environment_key_configured", lambda: False)


@pytest.fixture
def stub_assistant(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Answer questions with a fixed plan instead of calling OpenAI."""
    from tests.helpers import StubLLM

    def install(plan) -> None:
        monkeypatch.setattr(
            "backend.service.get_llm", lambda api_key=None, model=None: StubLLM(plan=plan)
        )
        monkeypatch.setattr("backend.service.environment_key_configured", lambda: True)

    return install
