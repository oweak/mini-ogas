"""DeepSeek provider — OpenAI-compatible /chat/completions endpoint."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from ..base import AIProvider, DiagnosisResult


class DeepSeekProvider(AIProvider):
    name = "deepseek"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: int = 25) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self._api_key) and self._api_key not in {
            "replace-with-your-key",
            "replace_me",
            "",
        }

    def diagnose(self, prompt: str, timeout: float | None = None) -> DiagnosisResult:
        content = self._call(
            system=(
                "你是 Mini-OGAS 分布式机械厂运维诊断助手。"
                "只输出 JSON，不要输出 Markdown。字段为 "
                "root_cause, recommended_action, confidence, need_isolation。"
                "confidence 是 0 到 1 的数字，need_isolation 是布尔值。"
            ),
            user=prompt,
            temperature=0.2,
            max_tokens=600,
            json_mode=True,
            timeout=timeout,
        )
        parsed = self._parse_json_content(content)
        return DiagnosisResult(
            root_cause=str(parsed.get("root_cause") or "DeepSeek 返回内容未包含明确根因。"),
            recommended_action=str(parsed.get("recommended_action") or "建议人工复核日志、指标和节点连接状态。"),
            confidence=self._bounded_float(parsed.get("confidence"), 0.65),
            need_isolation=bool(parsed.get("need_isolation", False)),
            raw_text=content,
        )

    def chat(self, messages: list[dict[str, str]], timeout: float | None = None) -> str:
        body = {
            "model": self._model,
            "temperature": 0.3,
            "max_tokens": 400,
            "messages": messages,
        }
        return self._raw_call(body, timeout=timeout)

    # ------------------------------------------------------------------
    # Internal helpers (extracted from the old deepseek_client.py)
    # ------------------------------------------------------------------

    def _call(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
        timeout: float | None = None,
    ) -> str:
        body: dict = {
            "model": self._model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return self._raw_call(body, timeout=timeout)

    def _raw_call(self, body: dict, timeout: float | None = None) -> str:
        url = self._base_url + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail[:400]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DeepSeek network error: {exc.reason}") from exc
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            error_detail = str(payload.get("error", payload))[:400]
            raise RuntimeError(f"DeepSeek API error response: {error_detail}") from exc

    @staticmethod
    def _parse_json_content(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                return {"root_cause": text}
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            return {"root_cause": text}
        return parsed

    @staticmethod
    def _bounded_float(value: object, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, number))
