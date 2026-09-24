import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from backend import service
from backend.config import Settings, get_settings
from backend.schemas.plan import Plan
from backend.tools import TOOLS
from tests.helpers import StubLLM, sales_step


def test_the_frontend_facing_names_are_all_defined() -> None:
    for name in service.__all__:
        assert hasattr(service, name), name


def test_analysis_names_are_the_registered_tools() -> None:
    assert service.analysis_names() == list(TOOLS)


def test_run_analysis_returns_the_tool_output() -> None:
    args = {"category": "Dairy", "sku": None, "days": 30}

    result = service.run_analysis("sales_summary", args)

    assert result == TOOLS["sales_summary"].invoke(args)
    assert result["scope"]["category"] == "Dairy"


def test_run_analysis_surfaces_invalid_input_as_the_public_error_type() -> None:
    with pytest.raises(service.ToolInputError, match="Unknown category 'Gamma'"):
        service.run_analysis("inventory_status", {"category": "Gamma", "sku": None})


def test_attention_summary_combines_stock_and_promotion_findings(small_db) -> None:
    result = service.attention_summary()

    assert result["status_counts"] == {
        "healthy": 4,
        "stockout_risk": 1,
        "overstock": 1,
        "no_recent_demand": 1,
    }
    assert [item["sku"] for item in result["stockout_risk"]] == ["A-001"]
    assert result["profitable_promo_share_pct"] == 50.0


def test_ask_builds_the_model_from_the_supplied_key_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received = {}

    def capture(api_key: str | None = None, model: str | None = None) -> StubLLM:
        received.update(api_key=api_key, model=model)
        return StubLLM(plan=Plan(objective="Check sales", steps=[sales_step()]))

    monkeypatch.setattr("backend.service.get_llm", capture)

    state = service.ask("Should we promote beverages?", api_key="sk-typed", model="gpt-4o")

    assert received == {"api_key": "sk-typed", "model": "gpt-4o"}
    assert state["plan"].objective == "Check sales"
    assert set(state["tool_results"]) == {"0_sales_summary"}


def test_ask_without_a_key_raises_the_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, openai_api_key=None)
    monkeypatch.setattr("backend.llm.get_settings", lambda: settings)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        service.ask("Anything")


def test_environment_key_and_default_model_come_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = Settings(_env_file=None, openai_api_key="sk-env", openai_model="gpt-4o")
    monkeypatch.setattr("backend.service.get_settings", lambda: configured)
    assert service.environment_key_configured() is True
    assert service.default_model() == "gpt-4o"

    missing = Settings(_env_file=None, openai_api_key=None)
    monkeypatch.setattr("backend.service.get_settings", lambda: missing)
    assert service.environment_key_configured() is False


def test_verify_api_key_delegates_to_the_llm_module(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    monkeypatch.setattr("backend.service._verify_api_key", seen.append)

    service.verify_api_key("sk-typed")

    assert seen == ["sk-typed"]


def test_data_status_describes_the_database(small_db: Path) -> None:
    status = service.data_status()

    assert status["path"] == str(small_db)
    assert status["as_of"] == "2026-01-31"
    assert status["size_mb"] == pytest.approx(small_db.stat().st_size / 1e6)
    assert status["free_gb"] > 0


def test_regenerate_data_replaces_the_configured_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "regenerated.db"
    monkeypatch.setenv("DB_PATH", str(target))
    get_settings.cache_clear()

    service.regenerate_data(seed=3)

    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT value FROM meta WHERE key = 'seed'").fetchone()[0] == "3"
        assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 80


def test_the_reporting_functions_are_the_analytics_functions() -> None:
    from backend import analytics

    assert service.headline is analytics.headline
    assert service.category_summary is analytics.category_summary
    assert service.product_catalog is analytics.product_catalog
