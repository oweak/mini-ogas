from __future__ import annotations

from types import SimpleNamespace

import pytest

from mogas.commands import down
from mogas.core.process import ProcessError


def test_down_delegates_to_supervisor_shutdown(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(down.sys, "platform", "win32")
    monkeypatch.setattr(
        down.subprocess,
        "run",
        lambda command, **kwargs: captured.update(command=command, kwargs=kwargs)
        or SimpleNamespace(returncode=0),
    )

    down.run()

    command = captured["command"]
    assert str(down.PROJ_ROOT / "scripts" / "stop-all.ps1") in command
    assert captured["kwargs"]["cwd"] == down.PROJ_ROOT


def test_down_rejects_failed_shutdown(monkeypatch) -> None:
    monkeypatch.setattr(down.sys, "platform", "win32")
    monkeypatch.setattr(
        down.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=7),
    )

    with pytest.raises(ProcessError, match="exit code 7"):
        down.run()
