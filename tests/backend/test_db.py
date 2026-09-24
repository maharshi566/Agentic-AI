import shutil
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from backend.config import get_settings
from backend.db import as_of_date, connect, first_sales_date, list_catalog, list_categories


def test_metadata_helpers_read_the_small_dataset(small_db) -> None:
    with connect() as conn:
        assert as_of_date(conn) == date(2026, 1, 31)
        assert first_sales_date(conn) == date(2025, 12, 3)
        assert list_categories(conn) == ["Alpha", "Beta"]
        assert list_catalog(conn)["Beta"] == [
            ("B-001", "Base"),
            ("B-002", "Edge Cover"),
            ("B-003", "Edge Overstock"),
        ]


def test_missing_database_names_the_generation_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DB_PATH", str(tmp_path / "absent.db"))
    get_settings.cache_clear()

    with pytest.raises(FileNotFoundError, match="python -m backend.data.generate_data"), connect():
        pass


def test_relative_database_path_is_resolved_against_the_working_directory(
    small_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    shutil.copy(small_db, tmp_path / "local.db")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DB_PATH", "local.db")
    get_settings.cache_clear()

    with connect() as conn:
        assert as_of_date(conn) == date(2026, 1, 31)


def test_connection_is_read_only(small_db) -> None:
    with connect() as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM products")
