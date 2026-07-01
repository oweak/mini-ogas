from __future__ import annotations

from types import SimpleNamespace

from mogas.commands import up
from mogas.core.health import HealthProof
from mogas.core.process import SESSION_TOKEN


def test_up_delegates_to_strict_launcher_and_verifies_session(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(up.sys, "platform", "win32")
    monkeypatch.setattr(up.subprocess, "run", lambda command, **kwargs: captured.update(command=command, kwargs=kwargs) or SimpleNamespace(returncode=0))
    proof = HealthProof("ok", "central-api", SESSION_TOKEN, 123, "2026-06-22T10:00:00+00:00")
    monkeypatch.setattr(up, "probe", lambda *_args, **_kwargs: proof)
    monkeypatch.setattr(up, "check", lambda *_args, **kwargs: kwargs["expected_session_token"] == SESSION_TOKEN)

    up.run(all=True)

    assert "-SessionToken" in captured["command"]
    assert SESSION_TOKEN in captured["command"]
