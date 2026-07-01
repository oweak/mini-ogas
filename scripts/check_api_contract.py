from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = ROOT / "services" / "central-api" / "app"
FRONTEND_SRC = ROOT / "services" / "dashboard" / "src"


ROUTE_RE = re.compile(r"""@(app|router)\.(get|post|put|delete|patch)\(["']([^"']+)["']\)""")
ROUTER_PREFIX_RE = re.compile(r"""router\s*=\s*APIRouter\(prefix=["']([^"']+)["']""")
APIFETCH_RE = re.compile(r"""apiFetch\(\s*([`'"])(.+?)\1""", re.DOTALL)


def normalize_path(path: str) -> str:
    path = path.split("?", 1)[0]
    path = re.sub(r"\$\{[^}]+\}", "{}", path)
    path = re.sub(r"\{[^}/]+\}", "{}", path)
    return path.rstrip("/") or "/"


def route_matches(frontend_path: str, backend_path: str) -> bool:
    front_segments = normalize_path(frontend_path).strip("/").split("/")
    back_segments = normalize_path(backend_path).strip("/").split("/")
    if front_segments == [""]:
        front_segments = []
    if back_segments == [""]:
        back_segments = []
    if len(front_segments) != len(back_segments):
        return False
    for front, back in zip(front_segments, back_segments):
        if front == "{}" or back == "{}":
            continue
        if front != back:
            return False
    return True


def backend_routes() -> set[str]:
    """Collect router handlers as their public `/api` compatibility paths."""
    routes: set[str] = set()
    for source in BACKEND_SRC.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        prefix_match = ROUTER_PREFIX_RE.search(text)
        prefix = prefix_match.group(1) if prefix_match else ""
        for target, _, path in ROUTE_RE.findall(text):
            full_path = path if target == "app" or path.startswith("/api/") else f"{prefix}{path}"
            routes.add(full_path if full_path.startswith("/api/") else f"/api{full_path}")

    return routes


def frontend_api_calls() -> dict[str, set[str]]:
    calls: dict[str, set[str]] = {}
    for path in FRONTEND_SRC.glob("*"):
        if path.suffix not in {".ts", ".vue"}:
            continue
        if path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        for _, call_path in APIFETCH_RE.findall(text):
            if call_path.startswith("/api/"):
                calls.setdefault(call_path, set()).add(str(path.relative_to(ROOT)))
    return calls


def main() -> int:
    routes = backend_routes()
    calls = frontend_api_calls()
    missing: list[tuple[str, list[str]]] = []
    for call_path, sources in sorted(calls.items()):
        if not any(route_matches(call_path, route) for route in routes):
            missing.append((call_path, sorted(sources)))

    print(f"backend_routes={len(routes)} frontend_api_calls={len(calls)}")
    if missing:
        print("Missing backend routes for frontend calls:")
        for call_path, sources in missing:
            print(f"- {call_path} <- {', '.join(sources)}")
        return 1
    print("API contract check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
