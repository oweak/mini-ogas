"""Unit tests for mogas core components."""

import pytest

from mogas.core.services import (
    ALL,
    AGENTS,
    CORE,
    DASHBOARD,
    MICROSERVICES,
    Service,
    by_role,
    get,
)


def test_service_registry_is_non_empty():
    assert len(ALL) > 0
    assert len(CORE) >= 1
    assert len(AGENTS) >= 3
    assert len(MICROSERVICES) >= 1
    assert len(DASHBOARD) >= 0


def test_core_services_have_ports():
    for svc in CORE:
        assert svc.port > 0, f"{svc.name} should have a port"


def test_background_worker_is_a_single_core_service_owned_after_central():
    workers = [service for service in CORE if service.name == "background-worker"]

    assert len(workers) == 1
    assert workers[0].port == 8084
    assert workers[0].depends_on == ("central-api",)
    assert "app.worker:app" in workers[0].command


def test_agents_have_no_ports():
    for svc in AGENTS:
        assert svc.port == 0, f"{svc.name} should not have a port"


def test_get_returns_service():
    svc = get("central-api")
    assert isinstance(svc, Service)
    assert svc.name == "central-api"
    assert svc.role == "core"


def test_get_raises_keyerror_for_unknown():
    with pytest.raises(KeyError):
        get("nonexistent")


def test_by_role_filtering():
    core = by_role("core")
    assert all(s.role == "core" for s in core)
    agents = by_role("agent")
    assert all(s.role == "agent" for s in agents)


def test_service_immutability():
    svc = get("central-api")
    with pytest.raises(Exception):
        svc.name = "hacked"


def test_every_service_has_command():
    for svc in ALL:
        assert len(svc.command) > 0, f"{svc.name} must have a command"


def test_agents_depend_on_core():
    for svc in AGENTS:
        assert "central-api" in svc.depends_on


def test_dashboard_depends_on_core():
    for svc in DASHBOARD:
        assert "central-api" in svc.depends_on
