"""AI runtime facade owned by the external AI Dispatcher control plane."""

from __future__ import annotations

from typing import Any

from .dispatcher import DispatcherError, dispatcher_client


def vault_present() -> bool:
    return bool(dispatcher_client.status().get("vault_present"))


def unlock_ai_runtime(password: str) -> dict[str, Any]:
    try:
        result = dispatcher_client.unlock(password)
    except DispatcherError as exc:
        raise ValueError(exc.detail or exc.code) from exc
    return {
        "provider": str(result.get("provider") or ""),
        "model": str(result.get("model") or ""),
        "provider_model": str(result.get("provider_model") or ""),
        "egress_origin": str(result.get("egress_origin") or ""),
    }


def runtime_status(*, verified_provider: str | None = None) -> dict[str, Any]:
    del verified_provider
    return dispatcher_client.status()
