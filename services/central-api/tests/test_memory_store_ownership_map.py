from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GENERATOR = PROJECT_ROOT / "tools" / "memory_store_ownership.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("memory_store_ownership", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_memory_store_inventory_is_complete_and_classified() -> None:
    module = _load_generator()
    document = module.build_document()

    assert "Inventory: 48 instance fields and 115 methods." in document
    assert "unclassified" not in document
    assert "CommandRepository / CommandService" in document
    assert "NodeRepository / NodeService" in document


def test_committed_memory_store_ownership_map_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
