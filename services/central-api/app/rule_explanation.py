from __future__ import annotations

import json
import re
from collections.abc import Callable
from hashlib import sha1
from typing import Any


ChatFn = Callable[[list[dict[str, str]]], str]


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _conclusions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    items = snapshot.get("rule_conclusions")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _run(snapshot: dict[str, Any]) -> dict[str, Any]:
    run = snapshot.get("run")
    return run if isinstance(run, dict) else {}


def _digest(conclusions: list[dict[str, Any]], run: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "run_id": run.get("run_id"),
            "scenario_id": run.get("scenario_id"),
            "conclusions": [
                {
                    "id": item.get("conclusion_id"),
                    "severity": item.get("severity"),
                    "evidence": item.get("evidence", []),
                }
                for item in conclusions
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha1(payload.encode("utf-8")).hexdigest()[:12].upper()


def _evidence_lines(conclusions: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for conclusion in conclusions:
        node = _text(conclusion.get("node_code"), "unknown-node")
        rule_id = _text(conclusion.get("rule_id"), "unknown-rule")
        evidence = conclusion.get("evidence", [])
        if not isinstance(evidence, list):
            continue
        for item in evidence[:3]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"{node}/{rule_id}: {item.get('field')} {item.get('operator')} "
                f"{item.get('threshold')}, current={item.get('value')}."
            )
    return lines[:8]


def _recommended_actions(conclusions: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for conclusion in conclusions:
        raw_actions = conclusion.get("recommended_actions", [])
        if not isinstance(raw_actions, list):
            continue
        for action in raw_actions:
            text = _text(action).strip()
            if text and text not in actions:
                actions.append(text)
    return actions[:6]


def _local_explanation(snapshot: dict[str, Any], *, status: str, source: str, reason: str = "") -> dict[str, Any]:
    conclusions = _conclusions(snapshot)
    run = _run(snapshot)
    actions = _recommended_actions(conclusions)
    if not conclusions:
        return {
            "schema_version": "2.2",
            "status": "steady",
            "source": "steady-state",
            "provider": source,
            "model": "",
            "used_live_ai": False,
            "rule_count": 0,
            "prompt_digest": _digest([], run),
            "summary": "当前规则引擎未发现瓶颈或输入饥饿，AI 保持监测，不创建处置命令。",
            "reasoning": [
                "三个生产节点的 snapshot 仍来自 live heartbeat。",
                "没有 rule_conclusions，说明当前 WIP、产速和利用率未达到处置阈值。",
                "系统应继续运行并等待下一轮真实心跳，而不是人为制造报警。",
            ],
            "recommended_actions": ["保持生产运行；仅在规则结论出现或人工触发时调用深度诊断。"],
            "evidence": [],
            "conclusion_ids": [],
        }
    highest = conclusions[0]
    return {
        "schema_version": "2.2",
        "status": status,
        "source": "rule-fallback",
        "provider": source,
        "model": "",
        "used_live_ai": False,
        "rule_count": len(conclusions),
        "prompt_digest": _digest(conclusions, run),
        "summary": reason or f"规则引擎发现 {len(conclusions)} 条流程异常，最高风险为 {highest.get('risk_level')}。",
        "reasoning": [
            "AI 后端未用于本次解释，系统使用规则结论和证据生成本地说明。",
            f"首要关注节点：{highest.get('node_code')} / {highest.get('machine_code')}。",
            "该结果仍是只读判断；执行隔离、重排或维修动作前需要进入处置模块。",
        ],
        "recommended_actions": actions or ["复核规则证据并刷新下一轮心跳。"],
        "evidence": _evidence_lines(conclusions),
        "conclusion_ids": [_text(item.get("conclusion_id")) for item in conclusions],
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return {}
        parsed = json.loads(match.group(0))
    return parsed if isinstance(parsed, dict) else {}


def _normalize_ai_response(
    raw_text: str,
    *,
    snapshot: dict[str, Any],
    provider: str,
    model: str,
) -> dict[str, Any]:
    conclusions = _conclusions(snapshot)
    run = _run(snapshot)
    parsed = _parse_json_object(raw_text)
    reasoning = parsed.get("reasoning", [])
    actions = parsed.get("recommended_actions", [])
    evidence = parsed.get("evidence", [])
    return {
        "schema_version": "2.2",
        "status": "explained",
        "source": "api",
        "provider": provider,
        "model": model,
        "used_live_ai": True,
        "rule_count": len(conclusions),
        "prompt_digest": _digest(conclusions, run),
        "summary": _text(parsed.get("summary"), raw_text[:240] or "AI 已读取规则证据。"),
        "reasoning": [str(item) for item in reasoning[:5]] if isinstance(reasoning, list) else [str(reasoning)],
        "recommended_actions": [str(item) for item in actions[:6]] if isinstance(actions, list) else [str(actions)],
        "evidence": [str(item) for item in evidence[:8]] if isinstance(evidence, list) else _evidence_lines(conclusions),
        "conclusion_ids": [_text(item.get("conclusion_id")) for item in conclusions],
        "raw_text": raw_text,
    }


def build_rule_explanation_prompt(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    conclusions = _conclusions(snapshot)
    run = _run(snapshot)
    compact = {
        "run": run,
        "data_source": snapshot.get("data_source"),
        "system": snapshot.get("system"),
        "conclusions": conclusions,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是 Mini-OGAS 工业管理系统的 AI 协调员。"
                "你只能解释规则结论和建议人工/脚本处置方向，不能假装已经执行动作。"
                "只输出 JSON，不要 Markdown。字段：summary, reasoning, recommended_actions, evidence。"
                "reasoning/recommended_actions/evidence 都是中文字符串数组。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请基于以下 dashboard snapshot 规则结论生成操作员可读解释。"
                "说明 AI 依据了哪些证据、建议先做什么、哪些动作需要人工确认。\n"
                f"{json.dumps(compact, ensure_ascii=False)}"
            ),
        },
    ]


def explain_rule_conclusions(
    snapshot: dict[str, Any],
    *,
    use_live_ai: bool,
    chat_fn: ChatFn | None = None,
    provider: str = "rule_fallback",
    model: str = "",
) -> dict[str, Any]:
    conclusions = _conclusions(snapshot)
    if not conclusions:
        return _local_explanation(snapshot, status="steady", source=provider)
    if not use_live_ai or chat_fn is None:
        return _local_explanation(snapshot, status="fallback", source=provider)
    try:
        raw_text = chat_fn(build_rule_explanation_prompt(snapshot))
        return _normalize_ai_response(raw_text, snapshot=snapshot, provider=provider, model=model)
    except Exception as exc:
        return _local_explanation(
            snapshot,
            status="fallback",
            source=provider,
            reason=f"AI 解释调用失败，已使用规则回退：{exc}",
        )
