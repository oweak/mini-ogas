from __future__ import annotations

import json
from unittest.mock import patch

from mogas.core import health


class _Response:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_probe_requires_process_identity() -> None:
    payload = {"status": "ok", "service": "central-api", "session_token": "run-1"}
    with patch("urllib.request.urlopen", return_value=_Response(payload)):
        assert health.probe(8080) is None


def test_check_requires_expected_launch_session() -> None:
    payload = {
        "status": "ok", "service": "central-api", "session_token": "run-1",
        "process_id": 123, "process_started_at": "2026-06-22T10:00:00+00:00",
    }
    with patch("urllib.request.urlopen", return_value=_Response(payload)):
        assert health.check(8080, expected_session_token="run-1")
    with patch("urllib.request.urlopen", return_value=_Response(payload)):
        assert not health.check(8080, expected_session_token="run-2")
