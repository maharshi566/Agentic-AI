import pytest

from backend.config import BACKEND_DIR, PROJECT_ROOT, Settings
from backend.data.generate_data import DEFAULT_DB_PATH


def test_the_default_database_is_the_one_the_generator_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DB_PATH", raising=False)

    assert Settings(_env_file=None).db_path == DEFAULT_DB_PATH
    assert BACKEND_DIR / "data" / "retail.db" == DEFAULT_DB_PATH


def test_environment_file_lives_at_the_project_root() -> None:
    assert BACKEND_DIR.parent == PROJECT_ROOT
    assert (PROJECT_ROOT / ".env.example").is_file()


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("MAX_PLAN_STEPS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.openai_model == "gpt-4o-mini"
    assert settings.max_plan_steps == 6
