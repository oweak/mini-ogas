from __future__ import annotations

from pathlib import Path

from app.core.outbox import OutboxRepository
from app.repositories.execution import ExecutionRepository
from app.repositories.quality import QualityRepository

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_execution_and_quality_repositories_hold_no_process_local_fact_state() -> None:
    assert ExecutionRepository().__dict__ == {}
    assert QualityRepository().__dict__ == {}


def test_execution_and_quality_routes_do_not_depend_on_memory_store() -> None:
    for domain in ("execution", "quality"):
        router_source = (APP_ROOT / "routers" / f"{domain}.py").read_text(
            encoding="utf-8"
        )
        repository_source = (APP_ROOT / "repositories" / f"{domain}.py").read_text(
            encoding="utf-8"
        )

        assert "MemoryStore" not in router_source
        assert "from ..store import" not in router_source
        assert f"repositories.{domain}" in router_source
        assert "MemoryStore" not in repository_source
        assert "enqueue_in_transaction" in repository_source


def test_memory_store_does_not_own_transport_or_object_store_adapters() -> None:
    store_source = (APP_ROOT / "store.py").read_text(encoding="utf-8")

    for forbidden_import in (
        ".core.nats_publisher",
        ".core.redis_projection",
        ".core.object_storage",
    ):
        assert forbidden_import not in store_source
    assert OutboxRepository().__dict__ == {}
