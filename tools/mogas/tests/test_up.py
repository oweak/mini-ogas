from __future__ import annotations

from types import SimpleNamespace

import pytest

from mogas.commands import up
from mogas.core.health import HealthProof
from mogas.core.process import ProcessError


def test_up_delegates_to_supervisor_launcher_and_verifies_session(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    session_token = "supervisor-session-20260718"
    (tmp_path / "miniogas-session-token.txt").write_text(session_token, encoding="ascii")
    monkeypatch.setattr(up.sys, "platform", "win32")
    monkeypatch.setattr(up, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(up.subprocess, "run", lambda command, **kwargs: captured.update(command=command, kwargs=kwargs) or SimpleNamespace(returncode=0))
    proof = HealthProof("ok", "central-api", session_token, 123, "2026-07-18T10:00:00+00:00")
    monkeypatch.setattr(up, "probe", lambda *_args, **_kwargs: proof)
    monkeypatch.setattr(up, "check", lambda *_args, **kwargs: kwargs["expected_session_token"] == session_token)

    up.run(all=True)

    command = captured["command"]
    assert str(up.PROJ_ROOT / "scripts" / "start-miniogas.ps1") in command
    assert "-RuntimeRoot" in command
    assert str(tmp_path) in command
    assert "-SessionToken" not in command


def test_up_rejects_missing_supervisor_session_proof(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(up.sys, "platform", "win32")
    monkeypatch.setattr(up, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(
        up.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )

    with pytest.raises(ProcessError, match="session proof is missing"):
        up.run()
