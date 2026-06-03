"""Groq Cloud provider — fast inference via OpenAI-compatible API (free tier)."""

from __future__ import annotations

import json
import urllib.request

from ..base import AIProvider, DiagnosisResult


class GroqProvider(AIProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str = "mixtral-8x7b-32768", timeout: int = 20) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = "https://api.groq.com/openai"
        self._timeout = timeout

    def is_available(self) -> bool:
        return bool(self._api_key) and self._api_key not in {"", "replace-with-your-key", "replace_me"}

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
                temperature=0.2,
                max_tokens=600,
                timeout=timeout,
            )
            parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            return DiagnosisResult(
                root_cause=str(parsed.get("root_cause", raw[:200])),
                recommended_action=str(parsed.get("recommended_action", "人工复核")),
                confidence=float(parsed.get("confidence", 0.65)),
                need_isolation=bool(parsed.get("need_isolation", False)),
                raw_text=raw,
            )
        except Exception:
            return DiagnosisResult(
                root_cause="Groq 诊断未能解析，请检查 API Key 和网络连通性。",
                recommended_action="检查 GROQ_API_KEY 配置，确认网络可访问 api.groq.com。",
                confidence=0.5,
                raw_text="groq parse error",
            )

    def chat(self, messages: list[dict[str, str]], timeout: float | None = None) -> str:
        return self._chat(messages, temperature=0.3, max_tokens=400, timeout=timeout)

    def _chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 400,
        timeout: float | None = None,
    ) -> str:
        body = json.dumps(
            {
                "model": self._model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": messages,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            self._base_url + "/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout or self._timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return str(payload["choices"][0]["message"]["content"])
