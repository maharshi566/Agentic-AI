import pytest

from backend.db import connect
from backend.tools.common import ToolInputError, pct_change, resolve_scope, top_and_bottom


def test_top_and_bottom_do_not_overlap_and_list_worst_first() -> None:
    assert top_and_bottom(list(range(1, 11)), 3) == ([1, 2, 3], [10, 9, 8])


def test_top_and_bottom_with_fewer_rows_than_twice_the_count() -> None:
    assert top_and_bottom([1, 2, 3, 4], 3) == ([1, 2, 3], [4])
    assert top_and_bottom([1, 2], 3) == ([1, 2], [])
    assert top_and_bottom([], 3) == ([], [])


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [(110, 100, 10.0), (90, 100, -10.0), (100, 100, 0.0), (5, 0, None), (5, -1, None)],
)
def test_pct_change(current: float, previous: float, expected: float | None) -> None:
    assert pct_change(current, previous) == expected


def test_blank_arguments_widen_the_scope_to_the_whole_store(small_db) -> None:
    with connect() as conn:
        scope = resolve_scope(conn, "  ", "")

    assert scope.describe() == {"category": None, "sku": None, "sku_count": 7}


def test_sku_takes_precedence_and_matching_category_is_accepted(small_db) -> None:
    with connect() as conn:
        scope = resolve_scope(conn, "ALPHA", "A-002")

    assert scope.skus == ("A-002",)
    assert scope.category == "Alpha"


def test_contradicting_category_is_rejected(small_db) -> None:
    with connect() as conn, pytest.raises(ToolInputError, match="A-002 belongs to Alpha"):
        resolve_scope(conn, "Beta", "A-002")


def test_scope_json_is_a_json_array_of_skus(small_db) -> None:
    with connect() as conn:
        scope = resolve_scope(conn, "Beta", None)

    assert scope.skus_json == '["B-001", "B-002", "B-003"]'
