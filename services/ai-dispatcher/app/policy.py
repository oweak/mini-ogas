from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .contracts import CostRecord, RedactionReport, TokenUsage

DEFAULT_EGRESS_ALLOWLIST = ",".join(
    (
        "https://api.deepseek.com",
        "https://api.groq.com",
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://127.0.0.1:1234",
        "http://localhost:1234",
    )
)
SENSITIVE_FIELD = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|credential)"
)
TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "sensitive_field",
        re.compile(
            r'''(?ix)(["']?(?:password|passwd|secret|token|api[_-]?key|authorization|credential)["']?\s*[:=]\s*)(["']?)[^\s,;"'}]+\2'''
        ),
    ),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{8,}")),
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")),
)


class EgressPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class PricingRate:
    input_per_million_usd: float
    output_per_million_usd: float


def bounded_float(name: str, default: float, lower: float, upper: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(upper, max(lower, value))


def bounded_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(upper, max(lower, value))


def origin_for(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EgressPolicyError("provider URL must use http or https with a hostname")
    if parsed.username or parsed.password:
        raise EgressPolicyError("provider URL must not contain user information")
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port or default_port
    suffix = "" if port == default_port else f":{port}"
    return f"{parsed.scheme}://{parsed.hostname.lower()}{suffix}"


def allowed_origins() -> frozenset[str]:
    raw = os.getenv("AI_EGRESS_ALLOWLIST", DEFAULT_EGRESS_ALLOWLIST)
    origins: set[str] = set()
    for item in raw.split(","):
        candidate = item.strip()
        if candidate:
            origins.add(origin_for(candidate))
    return frozenset(origins)


def require_allowed_egress(url: str) -> str:
    origin = origin_for(url)
    if origin not in allowed_origins():
        raise EgressPolicyError(f"egress origin is not allowlisted: {origin}")
    return origin


def _redact_text(value: str, categories: set[str]) -> tuple[str, int]:
    result = value
    replacements = 0
    for category, pattern in TEXT_PATTERNS:
        if category == "sensitive_field":
            result, count = pattern.subn(lambda match: match.group(1) + "[REDACTED]", result)
        else:
            result, count = pattern.subn("[REDACTED]", result)
        if count:
            categories.add(category)
            replacements += count
    return result, replacements


def redact_payload(value: Any) -> tuple[Any, RedactionReport]:
    categories: set[str] = set()
    replacements = 0

    def visit(item: Any) -> Any:
        nonlocal replacements
        if isinstance(item, dict):
            output: dict[str, Any] = {}
            for key, child in item.items():
                if SENSITIVE_FIELD.search(str(key)):
                    output[str(key)] = "[REDACTED]"
                    categories.add("sensitive_field")
                    replacements += 1
                else:
                    output[str(key)] = visit(child)
            return output
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, str):
            redacted, count = _redact_text(item, categories)
            replacements += count
            return redacted
        return item

    redacted = visit(value)
    return redacted, RedactionReport(
        applied=replacements > 0,
        replacement_count=replacements,
        categories=sorted(categories),
    )


def pricing_rates() -> dict[str, PricingRate]:
    raw = os.getenv("AI_COST_RATES_JSON", "{}").strip() or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, PricingRate] = {}
    for provider_model, value in parsed.items():
        if not isinstance(value, dict):
            continue
        try:
            input_rate = max(0.0, float(value["input_per_million_usd"]))
            output_rate = max(0.0, float(value["output_per_million_usd"]))
        except (KeyError, TypeError, ValueError):
            continue
        result[str(provider_model)] = PricingRate(input_rate, output_rate)
    return result


def estimate_cost(provider_model: str, usage: TokenUsage) -> CostRecord:
    rate = pricing_rates().get(provider_model)
    if rate is None or usage.prompt_tokens is None or usage.completion_tokens is None:
        return CostRecord()
    amount = (
        usage.prompt_tokens * rate.input_per_million_usd
        + usage.completion_tokens * rate.output_per_million_usd
    ) / 1_000_000
    return CostRecord(
        estimated=True,
        amount=round(amount, 8),
        pricing_source="AI_COST_RATES_JSON",
    )
