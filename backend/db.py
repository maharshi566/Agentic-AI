import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from backend.config import get_settings


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    db_path = get_settings().db_path
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found at {db_path}. "
            "Generate it with: python -m backend.data.generate_data"
        )
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def as_of_date(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT value FROM meta WHERE key = 'as_of_date'").fetchone()
    return date.fromisoformat(row["value"])


def first_sales_date(conn: sqlite3.Connection) -> date:
    row = conn.execute("SELECT MIN(date) AS first_date FROM daily_sales").fetchone()
    return date.fromisoformat(row["first_date"])


def list_categories(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    return [row["category"] for row in rows]


def list_catalog(conn: sqlite3.Connection) -> dict[str, list[tuple[str, str]]]:
    rows = conn.execute(
        "SELECT category, sku, name FROM products ORDER BY category, sku"
    ).fetchall()
    catalog: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        catalog.setdefault(row["category"], []).append((row["sku"], row["name"]))
    return catalog
