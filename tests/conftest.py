import shutil
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path

import pytest

from backend.config import get_settings
from backend.data.generate_data import generate
from tests.small_db import build_small_db


def _use_database(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv("DB_PATH", str(path))
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def retail_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("retail") / "retail.db"
    generate(path)
    return path


@pytest.fixture(scope="session")
def small_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("small") / "small.db"
    build_small_db(path)
    return path


@pytest.fixture(autouse=True)
def use_generated_db(retail_db: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _use_database(monkeypatch, retail_db)
    yield
    get_settings.cache_clear()


@pytest.fixture
def small_db(small_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _use_database(monkeypatch, small_db_path)
    return small_db_path


@pytest.fixture
def db(retail_db: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(f"{retail_db.as_uri()}?mode=ro", uri=True)
    yield conn
    conn.close()


@pytest.fixture
def edit_small_db(
    small_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., None]:
    """Point the app at a private copy of the small dataset and return a SQL runner for it."""
    path = tmp_path / "edited.db"
    shutil.copy(small_db_path, path)
    _use_database(monkeypatch, path)

    def run(*statements: str) -> None:
        with closing(sqlite3.connect(path)) as conn, conn:
            for statement in statements:
                conn.execute(statement)

    return run
