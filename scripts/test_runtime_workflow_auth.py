from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

import pytest

SCRIPT = Path(__file__).with_name("check_runtime_workflow.py")


def _load_workflow_module():
    name = f"check_runtime_workflow_test_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_workflow_provisions_a_node_bound_principal_credential(monkeypatch) -> None:
    module = _load_workflow_module()
    calls: list[tuple[str, str, str]] = []

    def fake_request(method, path, _body=None, _params=None, auth="bearer"):
        calls.append((method, path, auth))
        return {"node_code": module.NODE_CODE, "token": "temporary-node-token"}

    monkeypatch.setattr(module, "request", fake_request)
    module.provision_workflow_node_credential()

    assert module.NODE_TOKEN == "temporary-node-token"
    assert module.NODE_CREDENTIAL_ISSUED is True
    assert calls == [
        (
            "POST",
            f"/api/security/node-credentials/{module.NODE_CODE}/rotate",
            "bearer",
        )
    ]


def test_workflow_revokes_and_forgets_temporary_credential(monkeypatch) -> None:
    module = _load_workflow_module()
    calls: list[tuple[str, str, str]] = []
    module.ACCESS_TOKEN = "administrator-jwt"
    module.NODE_TOKEN = "temporary-node-token"
    module.NODE_CREDENTIAL_ISSUED = True

    def fake_request(method, path, _body=None, _params=None, auth="bearer"):
        calls.append((method, path, auth))
        return {"accepted": True, "revoked_credentials": 1}

    monkeypatch.setattr(module, "request", fake_request)
    module.revoke_workflow_node_credential()

    assert module.NODE_TOKEN == ""
    assert module.NODE_CREDENTIAL_ISSUED is False
    assert calls == [
        (
            "POST",
            f"/api/security/node-credentials/{module.NODE_CODE}/revoke",
            "bearer",
        )
    ]


def test_node_request_rejects_missing_temporary_credential() -> None:
    module = _load_workflow_module()
    module.NODE_TOKEN = ""

    with pytest.raises(RuntimeError, match="temporary node credential is not initialized"):
        module.request("POST", "/api/node-heartbeats", {}, auth="node")
