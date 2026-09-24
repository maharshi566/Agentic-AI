import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx
import openai
import pytest
from streamlit.testing.v1 import AppTest

from backend.config import get_settings
from backend.schemas.plan import AssortmentStep, Plan
from backend.schemas.tools import AssortmentArgs
from backend.tools.inventory_tool import inventory_status
from frontend.forms import EXAMPLES
from frontend.labels import inr
from tests.frontend.conftest import TIMEOUT_SECONDS, button, load, metrics
from tests.helpers import inventory_step, market_step, sales_step

QUESTION_BOX = "question"


def promotion_plan() -> Plan:
    return Plan(
        objective="Decide whether a Beverages promotion would raise profit.",
        steps=[sales_step(days=90), inventory_step(), market_step()],
    )


def ask(at: AppTest, question: str) -> AppTest:
    at.text_area(key=QUESTION_BOX).set_value(question).run()
    button(at, "Ask").click().run()
    return at


def test_overview_shows_headline_figures_and_alerts(db: sqlite3.Connection) -> None:
    at = load("frontend/views/overview.py").run()
    revenue = db.execute("SELECT SUM(revenue) FROM daily_sales").fetchone()[0]
    at_risk = inventory_status.invoke({"category": None, "sku": None})["status_counts"]

    assert not at.exception
    figures = metrics(at)
    assert figures["Revenue"] == inr(revenue)
    assert figures["Products at risk of running out"] == str(at_risk["stockout_risk"])
    assert figures["Overstocked products"] == str(at_risk["overstock"])
    assert [s.value for s in at.subheader] == [
        "Needs attention",
        "Revenue by month and category",
        "Categories",
        "Busiest days of the week",
    ]
    assert len(at.dataframe) == 1


def test_overview_lists_products_about_to_run_out() -> None:
    at = load("frontend/views/overview.py").run()
    assert any("Running out before restock" in w.value for w in at.warning)


def test_explore_runs_an_analysis_for_the_whole_store() -> None:
    at = load("frontend/views/explore.py").run()
    assert not at.metric

    button(at, "Run analysis").click().run()

    assert not at.exception
    assert metrics(at)["Units per day"]
    assert any("Whole store (80 products)" in c.value for c in at.caption)


def test_explore_runs_an_analysis_for_one_product() -> None:
    at = load("frontend/views/explore.py").run()

    at.selectbox[0].select("pricing_info").run()
    at.radio[0].set_value("One product").run()
    at.selectbox[2].select("BEV-004").run()
    button(at, "Run analysis").click().run()

    assert not at.exception
    assert any("BEV-004 (Beverages)" in c.value for c in at.caption)


def test_explore_range_analysis_only_allows_a_category() -> None:
    at = load("frontend/views/explore.py").run()

    at.selectbox[0].select("assortment_analysis").run()

    assert len(at.radio) == 0
    assert any("always looks at one category" in c.value for c in at.caption)
    at.selectbox[1].select("Snacks").run()
    button(at, "Run analysis").click().run()
    assert not at.exception
    assert "Category revenue" in metrics(at)
    assert any("Snacks (14 products)" in c.value for c in at.caption)


def test_explore_disables_controls_that_do_not_apply() -> None:
    at = load("frontend/views/explore.py").run()

    assert at.selectbox[1].disabled
    assert at.selectbox[2].disabled
    assert not at.slider[0].disabled

    at.selectbox[0].select("inventory_status").run()
    assert at.slider[0].disabled


def test_explore_shows_tool_input_errors_as_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.service import ToolInputError

    def reject(tool: str, args: dict) -> None:
        raise ToolInputError("Unknown category 'Gamma'.")

    monkeypatch.setattr("backend.service.run_analysis", reject)
    at = load("frontend/views/explore.py").run()

    button(at, "Run analysis").click().run()

    assert [w.value for w in at.warning] == ["Unknown category 'Gamma'."]


def test_ask_page_explains_how_to_get_started_without_a_key(
    without_env_key: None,
) -> None:
    at = load("frontend/views/ask.py").run()

    assert any("Add your OpenAI API key" in i.value for i in at.info)
    assert button(at, "Ask").disabled


def test_ask_button_needs_a_question(stub_assistant) -> None:
    stub_assistant(promotion_plan())
    at = load("frontend/views/ask.py").run()

    assert button(at, "Ask").disabled
    at.text_area(key=QUESTION_BOX).set_value("Should we promote beverages?").run()
    assert not button(at, "Ask").disabled


def test_choosing_an_example_fills_in_the_question(stub_assistant) -> None:
    stub_assistant(promotion_plan())
    at = load("frontend/views/ask.py").run()

    at.pills[0].set_value(EXAMPLES[1]).run()

    assert at.text_area(key=QUESTION_BOX).value == EXAMPLES[1]


def test_ask_shows_the_plan_and_the_evidence(stub_assistant) -> None:
    stub_assistant(promotion_plan())

    at = ask(load("frontend/views/ask.py").run(), "Should we promote beverages?")

    assert not at.exception
    assert [s.value for s in at.subheader] == [
        "What the assistant set out to do",
        "Evidence gathered",
    ]
    text = [m.value for m in at.markdown]
    assert "**Question:** Should we promote beverages?" in text
    assert any(t.startswith("1. **Sales performance** (Beverages · last 90 days)") for t in text)
    assert any(t.startswith("3. **Market and competitors** (Beverages)") for t in text)
    titles = [e.label for e in at.expander]
    assert titles[0] == "1. Sales performance · Beverages · last 90 days"
    assert titles[-1] == "Technical details"
    assert len(titles) == 4
    assert "Revenue" in metrics(at)


def test_the_first_evidence_section_is_open_and_the_rest_are_closed(stub_assistant) -> None:
    stub_assistant(promotion_plan())

    at = ask(load("frontend/views/ask.py").run(), "Should we promote beverages?")

    assert [e.proto.expanded for e in at.expander][:3] == [True, False, False]


def test_a_failed_analysis_step_is_opened_and_explained(stub_assistant) -> None:
    plan = Plan(
        objective="Mixed",
        steps=[
            sales_step(),
            AssortmentStep(
                rationale="Bad category",
                tool="assortment_analysis",
                args=AssortmentArgs(category="Electronics", days=90),
            ),
        ],
    )
    stub_assistant(plan)

    at = ask(load("frontend/views/ask.py").run(), "Anything")

    assert not at.exception
    assert [e.proto.expanded for e in at.expander][:2] == [True, True]
    assert len(at.warning) == 1
    assert at.warning[0].value.startswith("Unknown category 'Electronics'")


def test_off_topic_questions_get_a_helpful_message(stub_assistant) -> None:
    stub_assistant(Plan(objective="Not retail", steps=[]))

    at = ask(load("frontend/views/ask.py").run(), "Tell me a joke")

    assert any("does not look like a merchandising question" in i.value for i in at.info)
    assert not at.subheader


def test_openai_failures_are_shown_in_plain_language(
    monkeypatch: pytest.MonkeyPatch, stub_assistant
) -> None:
    stub_assistant(promotion_plan())
    rejected = openai.AuthenticationError(
        "bad key",
        response=httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com")),
        body=None,
    )

    def fail(api_key: str | None = None, model: str | None = None) -> None:
        raise rejected

    monkeypatch.setattr("backend.service.get_llm", fail)

    at = ask(load("frontend/views/ask.py").run(), "Should we promote beverages?")

    assert [e.value for e in at.error] == [
        "OpenAI rejected the API key. Update it on the Settings page."
    ]
    assert not at.exception


def test_the_previous_answer_stays_visible_when_the_page_reruns(stub_assistant) -> None:
    stub_assistant(promotion_plan())

    at = ask(load("frontend/views/ask.py").run(), "Should we promote beverages?")
    at.run()

    assert any(m.value == "**Question:** Should we promote beverages?" for m in at.markdown)


def test_settings_reports_a_key_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.service.environment_key_configured", lambda: True)

    at = load("frontend/views/settings.py").run()

    assert any("OPENAI_API_KEY environment setting" in i.value for i in at.info)


def test_settings_warns_when_no_key_is_available(without_env_key: None) -> None:
    at = load("frontend/views/settings.py").run()

    assert any("No API key is set" in w.value for w in at.warning)


def test_settings_keeps_a_typed_key_and_model_for_the_session(without_env_key: None) -> None:
    at = load("frontend/views/settings.py").run()

    at.text_input[0].set_value("sk-typed").run()
    at.selectbox[0].select("gpt-4o").run()
    button(at, "Use this key and model").click().run()

    assert at.session_state["api_key"] == "sk-typed"
    assert at.session_state["model"] == "gpt-4o"
    assert any("entered on the Settings page" in i.value for i in at.info)


def test_settings_connection_test_reports_success(
    monkeypatch: pytest.MonkeyPatch, without_env_key: None
) -> None:
    checked = []
    monkeypatch.setattr("backend.service.verify_api_key", checked.append)
    at = load("frontend/views/settings.py").run()

    at.text_input[0].set_value("sk-typed").run()
    button(at, "Test the connection").click().run()

    assert checked == ["sk-typed"]
    assert [s.value for s in at.success] == ["Connected to OpenAI."]


def test_settings_connection_test_reports_a_rejected_key(
    monkeypatch: pytest.MonkeyPatch, without_env_key: None
) -> None:
    def reject(key: str | None) -> None:
        raise openai.AuthenticationError(
            "bad key",
            response=httpx.Response(401, request=httpx.Request("GET", "https://api.openai.com")),
            body=None,
        )

    monkeypatch.setattr("backend.service.verify_api_key", reject)
    at = load("frontend/views/settings.py").run()

    button(at, "Test the connection").click().run()

    assert [e.value for e in at.error] == ["OpenAI rejected the API key. Enter a valid key above."]


def test_settings_regenerates_the_demo_data_only_after_confirmation(
    small_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "regenerated.db"
    shutil.copy(small_db_path, target)
    monkeypatch.setenv("DB_PATH", str(target))
    get_settings.cache_clear()
    at = load("frontend/views/settings.py").run()

    assert button(at, "Regenerate").disabled
    at.number_input[0].set_value(7).run()
    at.checkbox[0].check().run()
    assert not button(at, "Regenerate").disabled
    button(at, "Regenerate").click().run()

    assert not at.exception
    assert any("regenerated with seed 7" in s.value for s in at.success)
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT value FROM meta WHERE key = 'seed'").fetchone()[0] == "7"
        assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 80


def test_the_session_key_and_model_are_passed_to_the_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.helpers import StubLLM

    received = {}

    def capture(api_key: str | None = None, model: str | None = None) -> StubLLM:
        received.update(api_key=api_key, model=model)
        return StubLLM(plan=Plan(objective="Captured", steps=[]))

    monkeypatch.setattr("backend.service.get_llm", capture)
    script = "\n".join(
        [
            "import streamlit as st",
            "from frontend import session",
            "st.session_state['api_key'] = 'sk-typed'",
            "st.session_state['model'] = 'gpt-4o'",
            "st.write(session.ask('Anything')['plan'].objective)",
        ]
    )

    at = AppTest.from_string(script, default_timeout=TIMEOUT_SECONDS).run()

    assert not at.exception
    assert at.markdown[0].value == "Captured"
    assert received == {"api_key": "sk-typed", "model": "gpt-4o"}


def test_the_full_app_starts_on_the_ask_page() -> None:
    at = load("frontend/streamlit_app.py").run()

    assert not at.exception
    assert [t.value for t in at.title] == ["Ask the assistant"]


def test_overview_refreshes_after_the_database_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.data.generate_data import generate

    target = tmp_path / "replaced.db"
    generate(target, seed=1)
    monkeypatch.setenv("DB_PATH", str(target))
    get_settings.cache_clear()

    at = load("frontend/views/overview.py").run()
    first = metrics(at)["Revenue"]
    generate(target, seed=2)
    at.run()

    assert not at.exception
    assert metrics(at)["Revenue"] != first
