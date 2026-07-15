from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
ALLOWED_ROUTER_DEPENDENCIES = {
    ("ai", "demo"),
    ("compat", "ai"),
    ("compat", "audit"),
    ("compat", "demo"),
    ("demo", "compat"),
    ("ops", "control"),
    ("reports", "demo"),
}


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            found.append((node.lineno, prefix + (node.module or "")))
    return found


def test_core_and_persistence_layers_do_not_depend_on_http_routers() -> None:
    protected = list((APP_ROOT / "core").rglob("*.py"))
    protected.extend(
        [APP_ROOT / "models.py", APP_ROOT / "store.py", APP_ROOT / "persistence_repository.py"]
    )
    violations = []
    for path in protected:
        for line, imported in _imports(path):
            if "routers" in imported:
                violations.append(f"{path.relative_to(APP_ROOT)}:{line} -> {imported}")
    assert violations == []


def test_router_to_router_legacy_dependencies_are_frozen() -> None:
    observed: set[tuple[str, str]] = set()
    for path in (APP_ROOT / "routers").glob("*.py"):
        source = path.stem
        for _, imported in _imports(path):
            target = ""
            if imported.startswith(".") and not imported.startswith(".."):
                target = imported.lstrip(".").split(".")[0]
            elif imported.startswith("..routers."):
                target = imported.split(".")[-1]
            if target and target not in {"__future__"}:
                observed.add((source, target))
    assert observed == ALLOWED_ROUTER_DEPENDENCIES
