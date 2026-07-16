from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from app import main
from app.contracts import InferenceRequest, TaskType, TokenUsage
from app.runtime import AiRuntime, ProviderConfig
from app.vault import encrypt_vault_payload
from fastapi.testclient import TestClient


def test_env_loader_tolerates_shallow_container_layout(monkeypatch, tmp_path: Path) -> None:
    module_path = tmp_path / "app" / "app" / "main.py"
    module_path.parent.mkdir(parents=True)
    monkeypatch.delenv("OGAS_ENV_FILE", raising=False)

    main._load_project_env(module_path)


def test_env_loader_finds_marked_project_root(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    module_path = project_root / "services" / "ai-dispatcher" / "app" / "main.py"
    module_path.parent.mkdir(parents=True)
    (project_root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (project_root / ".env").write_text("AI_DISPATCHER_ENV_PROBE=loaded\n", encoding="utf-8")
    monkeypatch.delenv("OGAS_ENV_FILE", raising=False)
    monkeypatch.delenv("AI_DISPATCHER_ENV_PROBE", raising=False)

    main._load_project_env(module_path)

    assert main.os.environ["AI_DISPATCHER_ENV_PROBE"] == "loaded"


def _request(content: str = "diagnose the live metrics") -> InferenceRequest:
    return InferenceRequest(
        task_type=TaskType.diagnosis,
        messages=[{"role": "user", "content": content}],
        response_format="json_object",
        max_tokens=500,
        correlation_id="test-correlation",
    )


def _config(name: str, *, base_url: str | None = None) -> ProviderConfig:
    defaults = {
        "deepseek": ("deepseek-chat", "https://api.deepseek.com", "sk-test-value"),
        "ollama": ("llama3", "http://localhost:11434", ""),
        "groq": ("groq-test", "https://api.groq.com/openai/v1", "sk-test-value"),
    }
    model, default_url, key = defaults[name]
    return ProviderConfig(name=name, model=model, base_url=base_url or default_url, api_key=key)


def _success_payload(provider: str) -> tuple[str, dict[str, object], TokenUsage]:
    structured = {
        "root_cause": f"{provider} root cause",
        "recommended_action": "reduce intake rate",
        "need_isolation": False,
        "summary": f"{provider} served the request",
    }
    return json.dumps(structured), structured, TokenUsage(
        prompt_tokens=100,
        completion_tokens=25,
        total_tokens=125,
    )


def test_chain_uses_next_provider_after_first_provider_fails(monkeypatch) -> None:
    runtime = AiRuntime()
    monkeypatch.setenv("AI_PROVIDER_RETRIES", "0")
    monkeypatch.setattr(runtime, "provider_chain", lambda: ["deepseek", "ollama"])
    monkeypatch.setattr(runtime, "provider_config", lambda name: _config(name))

    async def fake_call(_client, config, **_kwargs):
        if config.name == "deepseek":
            raise ValueError("simulated invalid provider response")
        return _success_payload(config.name)

    monkeypatch.setattr(runtime, "_call_provider", fake_call)
    result = asyncio.run(runtime.infer(_request()))

    assert result.provenance.provider == "ollama"
    assert result.provenance.provider_model == "ollama/llama3"
    assert result.provenance.fallback_used is True
    assert [item.provider for item in result.provenance.attempts] == ["deepseek", "ollama"]
    assert result.provenance.attempts[0].error_class == "invalid_response"


def test_chain_reaches_rule_fallback_only_after_all_providers_fail(monkeypatch) -> None:
    runtime = AiRuntime()
    monkeypatch.setenv("AI_PROVIDER_RETRIES", "0")
    monkeypatch.setattr(runtime, "provider_chain", lambda: ["deepseek", "groq"])
    monkeypatch.setattr(runtime, "provider_config", lambda name: _config(name))

    async def failing_call(_client, config, **_kwargs):
        raise httpx.ConnectError(f"{config.name} unavailable")

    monkeypatch.setattr(runtime, "_call_provider", failing_call)
    result = asyncio.run(runtime.infer(_request()))

    assert result.provenance.source == "rule_fallback"
    assert result.provenance.provider_model == "rule_fallback/deterministic-rules"
    assert len(result.provenance.attempts) == 2
    assert {item.error_class for item in result.provenance.attempts} == {"transport"}


def test_retriable_transport_failure_retries_same_provider(monkeypatch) -> None:
    runtime = AiRuntime()
    monkeypatch.setenv("AI_PROVIDER_RETRIES", "1")
    monkeypatch.setattr(runtime, "provider_chain", lambda: ["deepseek"])
    monkeypatch.setattr(runtime, "provider_config", lambda _name: _config("deepseek"))
    calls = 0

    async def flaky_call(_client, config, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary failure")
        return _success_payload(config.name)

    monkeypatch.setattr(runtime, "_call_provider", flaky_call)
    result = asyncio.run(runtime.infer(_request()))

    assert calls == 2
    assert [item.status for item in result.provenance.attempts] == ["failed", "succeeded"]
    assert result.provenance.attempts[0].error_class == "transport"


def test_data_is_redacted_before_provider_egress(monkeypatch) -> None:
    runtime = AiRuntime()
    monkeypatch.setenv("AI_PROVIDER_RETRIES", "0")
    monkeypatch.setattr(runtime, "provider_chain", lambda: ["deepseek"])
    monkeypatch.setattr(runtime, "provider_config", lambda _name: _config("deepseek"))
    observed_messages: list[dict[str, str]] = []

    async def capture_call(_client, config, **kwargs):
        observed_messages.extend(kwargs["messages"])
        return _success_payload(config.name)

    monkeypatch.setattr(runtime, "_call_provider", capture_call)
    sensitive_key = "s" + "k-sensitive-12345678"
    result = asyncio.run(
        runtime.infer(_request(f'api_key="{sensitive_key}" Bearer token-value-12345678'))
    )

    assert "sk-sensitive" not in observed_messages[0]["content"]
    assert "token-value" not in observed_messages[0]["content"]
    assert observed_messages[0]["content"].count("[REDACTED]") == 2
    assert result.provenance.redaction.applied is True
    assert result.provenance.redaction.replacement_count == 2


def test_non_allowlisted_provider_url_never_reaches_http_client(monkeypatch) -> None:
    runtime = AiRuntime()
    monkeypatch.setattr(runtime, "provider_chain", lambda: ["deepseek"])
    monkeypatch.setattr(
        runtime,
        "provider_config",
        lambda _name: _config("deepseek", base_url="https://untrusted.example"),
    )

    async def forbidden_call(*_args, **_kwargs):
        raise AssertionError("HTTP call must not happen for denied egress")

    monkeypatch.setattr(runtime, "_call_provider", forbidden_call)
    result = asyncio.run(runtime.infer(_request()))

    assert result.provenance.source == "rule_fallback"
    assert result.provenance.attempts[0].error_class == "policy_denied"
    assert result.provenance.attempts[0].error_code == "egress_not_allowlisted"


def test_global_token_limit_clamps_caller_request(monkeypatch) -> None:
    runtime = AiRuntime()
    monkeypatch.setenv("AI_MAX_TOKENS", "128")
    monkeypatch.setattr(runtime, "provider_chain", lambda: ["deepseek"])
    monkeypatch.setattr(runtime, "provider_config", lambda _name: _config("deepseek"))
    observed_max_tokens = 0

    async def capture_call(_client, config, **kwargs):
        nonlocal observed_max_tokens
        observed_max_tokens = kwargs["max_tokens"]
        return _success_payload(config.name)

    monkeypatch.setattr(runtime, "_call_provider", capture_call)
    result = asyncio.run(runtime.infer(_request()))

    assert observed_max_tokens == 128
    assert result.provenance.max_tokens == 128


def test_cost_is_estimated_from_usage_and_configured_rate(monkeypatch) -> None:
    runtime = AiRuntime()
    monkeypatch.setenv(
        "AI_COST_RATES_JSON",
        json.dumps(
            {
                "deepseek/deepseek-chat": {
                    "input_per_million_usd": 1.0,
                    "output_per_million_usd": 2.0,
                }
            }
        ),
    )
    monkeypatch.setattr(runtime, "provider_chain", lambda: ["deepseek"])
    monkeypatch.setattr(runtime, "provider_config", lambda _name: _config("deepseek"))

    async def success(_client, config, **_kwargs):
        return _success_payload(config.name)

    monkeypatch.setattr(runtime, "_call_provider", success)
    result = asyncio.run(runtime.infer(_request()))

    assert result.provenance.cost.amount == 0.00015
    assert result.provenance.cost.estimated is True
    assert result.provenance.cost.pricing_source == "AI_COST_RATES_JSON"


def test_vault_unlock_keeps_provider_secret_inside_dispatcher(monkeypatch, tmp_path: Path) -> None:
    vault_path = tmp_path / "ai-vault.json"
    vault_path.write_text(
        json.dumps(
            encrypt_vault_payload(
                {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "base_url": "https://api.deepseek.com",
                    "api_key": "provider-vault-test-secret-12345678",
                },
                "test-password",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_VAULT_PATH", str(vault_path))
    runtime = AiRuntime()

    unlocked = runtime.unlock("test-password")
    status = runtime.status()

    assert unlocked == {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "provider_model": "deepseek/deepseek-chat",
        "egress_origin": "https://api.deepseek.com",
    }
    assert status["vault_unlocked"] is True
    assert "api_key" not in unlocked
    assert "api_key" not in status


def test_runtime_status_endpoint_requires_service_token(monkeypatch) -> None:
    monkeypatch.setenv("AI_DISPATCHER_TOKEN", "service-token")
    monkeypatch.setenv("API_ACCESS_TOKEN", "different-api-token")
    client = TestClient(main.app)

    assert client.get("/runtime/status").status_code == 401
    response = client.get("/runtime/status", headers={"X-OGAS-Token": "service-token"})

    assert response.status_code == 200
    assert "providers" in response.json()


def test_dispatcher_token_takes_precedence_over_api_token(monkeypatch) -> None:
    monkeypatch.setenv("AI_DISPATCHER_TOKEN", "dispatcher-only-token")
    monkeypatch.setenv("API_ACCESS_TOKEN", "external-api-token")
    client = TestClient(main.app)

    denied = client.get(
        "/runtime/status",
        headers={"X-OGAS-Token": "external-api-token"},
    )
    allowed = client.get(
        "/runtime/status",
        headers={"X-OGAS-Token": "dispatcher-only-token"},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 200
