"""Ollama provider — local LLM via Ollama's OpenAI-compatible API."""

from __future__ import annotations

import json
import urllib.request

from ..base import AIProvider, DiagnosisResult


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3", timeout: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(self._base_url + "/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status != 200:
                    return False
                payload = json.loads(resp.read().decode("utf-8"))
                models = payload.get("models", [])
                return any(
                    str(item.get("name") or item.get("model") or "") == self._model
                    for item in models
                    if isinstance(item, dict)
                )
        except Exception:
            return False

    def diagnose(self, prompt: str, timeout: float | None = None) -> DiagnosisResult:
        system = (
            "你是 Mini-OGAS 分布式机械厂运维诊断助手。"
            "只输出 JSON：{\"root_cause\": \"...\", \"recommended_action\": \"...\", "
            "\"confidence\": 0.8, \"need_isolation\": false}"
        )
        try:
            raw = self._chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                timeout=timeout,
            )
            parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            return DiagnosisResult(
                root_cause=str(parsed.get("root_cause", raw[:200])),
                recommended_action=str(parsed.get("recommended_action", "人工复核")),
                confidence=float(parsed.get("confidence", 0.6)),
                need_isolation=bool(parsed.get("need_isolation", False)),
                raw_text=raw,
            )
        except Exception:
            return DiagnosisResult(
                root_cause="Ollama 诊断未能解析，请检查本地模型是否正常运行。",
                recommended_action="检查 Ollama 服务状态 (ollama list)，确认已拉取模型。",
                confidence=0.5,
                raw_text="ollama parse error",
            )

    def chat(self, messages: list[dict[str, str]], timeout: float | None = None) -> str:
        return self._chat(messages, timeout=timeout)

    def _chat(self, messages: list[dict[str, str]], timeout: float | None = None) -> str:
        body = json.dumps(
            {"model": self._model, "messages": messages, "stream": False},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            self._base_url + "/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout or self._timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return str(payload["choices"][0]["message"]["content"])
