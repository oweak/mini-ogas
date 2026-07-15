from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import LOCAL_DEVELOPMENT_JWT_SECRET, Settings, settings
from app.store import MemoryStore


SERVICE_ROOT = Path(__file__).resolve().parents[1]


def production_settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "data_source": "live",
        "control_mode": "read_only",
        "demo_seed_enabled": False,
        "physical_write_enabled": False,
        "industrial_connector_enabled": False,
        "persist_enabled": True,
        "persist_backend": "postgres",
        "postgres_dsn": "postgresql://miniogas:secret@127.0.0.1:5432/miniogas",
        "auth_jwt_secret": "j" * 48,
        "node_ingest_token": "n" * 48,
        "allow_legacy_api_token_auth": False,
        "tenant_id": "tenant-production",
        "site_id": "site-production-01",
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_read_only_production_environment_is_explicit() -> None:
    configured = production_settings()

    assert configured.environment_status() == {
        "app_env": "production",
        "data_source": "live",
        "control_mode": "read_only",
        "demo_seed_enabled": False,
        "industrial_connector_enabled": False,
        "physical_write_enabled": False,
        "tenant_id": "tenant-production",
        "site_id": "site-production-01",
    }


def test_app_env_alias_dev_is_rejected_instead_of_silent_coercion() -> None:
    with pytest.raises(ValidationError, match="app_env"):
        Settings(app_env="dev")


def test_direct_runtime_dependencies_are_declared_for_clean_install() -> None:
    requirements = {
        line.split("==", 1)[0].strip().lower()
        for line in (SERVICE_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "psutil" in requirements


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"data_source": "simulated"}, "DATA_SOURCE must be shadow or live"),
        ({"demo_seed_enabled": True, "data_source": "simulated"}, "Demo Seed must be disabled"),
        ({"auth_jwt_secret": LOCAL_DEVELOPMENT_JWT_SECRET}, "JWT_SECRET"),
        ({"node_ingest_token": "short"}, "NODE_INGEST_TOKEN"),
        ({"allow_legacy_api_token_auth": True}, "legacy API token"),
    ],
)
def test_invalid_production_boundaries_fail_fast(overrides: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        production_settings(**overrides)


def test_controlled_write_requires_pilot_or_production_connector_and_write_flags() -> None:
    with pytest.raises(ValidationError, match="limited to pilot or production"):
        Settings(
            app_env="digital_twin",
            data_source="simulated",
            control_mode="controlled_write",
            demo_seed_enabled=True,
        )

    with pytest.raises(ValidationError, match="requires an enabled industrial connector"):
        production_settings(control_mode="controlled_write")

    enabled = production_settings(
        control_mode="controlled_write",
        industrial_connector_enabled=True,
        physical_write_enabled=True,
    )
    assert enabled.control_mode == "controlled_write"


def test_runtime_source_must_match_configured_data_source() -> None:
    simulated = Settings(
        app_env="digital_twin",
        data_source="simulated",
        demo_seed_enabled=True,
    )
    live = production_settings()

    assert simulated.validate_runtime_source({"simulation_engine": "simpy"}) == "simulated"
    assert live.validate_runtime_source({
        "simulation_engine": "physical",
        "deployment_mode": "physical",
        "runtime_source": "live",
    }) == "live"
    with pytest.raises(ValueError, match="incompatible"):
        live.validate_runtime_source({"simulation_engine": "simpy"})


def test_demo_seed_can_be_disabled_without_creating_fake_master_data(monkeypatch) -> None:
    monkeypatch.setattr(settings, "persist_enabled", False)
    monkeypatch.setattr(settings, "demo_seed_enabled", False)
    isolated = MemoryStore()

    assert isolated.nodes == {}
    assert isolated.machines == []
    assert isolated.market_signals == []
    assert isolated.inventory == []
    assert isolated.production_plans == []
    assert isolated.dispatch_tasks == []
    assert isolated.management_snapshot()["data_source"] == settings.data_source
