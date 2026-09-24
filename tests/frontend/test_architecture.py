import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"

BACKEND_ONLY_LIBRARIES = {"streamlit", "pandas"}


def imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    """Return (module, imported names) for every import in a Python file."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend((alias.name, ()) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, tuple(alias.name for alias in node.names)))
    return found


def python_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*.py") if "__pycache__" not in p.parts)


def is_service_import(module: str, names: tuple[str, ...]) -> bool:
    return module == "backend.service" or (module == "backend" and set(names) == {"service"})


@pytest.mark.parametrize("path", python_files(FRONTEND), ids=lambda p: str(p.relative_to(ROOT)))
def test_frontend_reaches_the_backend_only_through_the_service(path: Path) -> None:
    for module, names in imports(path):
        if module.split(".")[0] == "backend":
            assert is_service_import(module, names), f"{module} imported in {path.name}"


@pytest.mark.parametrize("path", python_files(BACKEND), ids=lambda p: str(p.relative_to(ROOT)))
def test_backend_never_depends_on_the_frontend_or_ui_libraries(path: Path) -> None:
    for module, _ in imports(path):
        top_level = module.split(".")[0]
        assert top_level != "frontend", f"{module} imported in {path.name}"
        assert top_level not in BACKEND_ONLY_LIBRARIES, f"{module} imported in {path.name}"


def test_the_entry_points_live_with_their_group() -> None:
    assert (FRONTEND / "streamlit_app.py").is_file()
    assert (BACKEND / "agent.py").is_file()
    assert (BACKEND / "service.py").is_file()
    assert not (ROOT / "app").exists()
    assert not (ROOT / "ui").exists()
