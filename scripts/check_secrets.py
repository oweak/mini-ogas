import json
import re
import sys
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    "node_modules", "dist", "__pycache__", ".git", ".venv",
    ".playwright-mcp", ".pytest_cache", ".runtime",
}
MAX_SCAN_BYTES = 500_000

PATTERNS = {
    "default_token": re.compile(r"mini-ogas-dev-token"),
    "secret_key": re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
}
SECRET_ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+|\$env:)?("
    r"OGAS_API_TOKEN|VITE_OGAS_TOKEN|"
    r"AI_API_KEY|OPENAI_API_KEY|DEEPSEEK_API_KEY|MINIOGAS_AI_API_KEY|"
    r"[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY)"
    r")\s*=\s*(.*?)\s*$",
)
TOKEN_PLACEHOLDER_PREFIXES = ("$", "%", "<", "{{")
TOKEN_READER_PREFIXES = ("env(", "os.getenv(", "process.env.", "import.meta.env.", "str(")
TOKEN_PLACEHOLDER_WORDS = {
    "replace_me",
    "replace-with-token",
    "replace-with-central-token",
    "replace-with-runtime-token",
    "your-token",
    "changeme",
    "token",
    "replace_me",
}
SECRET_FILE_NAMES = {"miniogas-token.txt"}

ALLOWLIST = {
    ("scripts/check_secrets.py", "default_token"),
    ("scripts/check_secrets.py", "secret_key"),
    ("scripts/check_secrets.py", "secret_assignment"),
}


def is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.relative_to(PROJECT_ROOT).parts)


def is_placeholder_token(value: str) -> bool:
    token = value.strip().strip('"').strip("'")
    lowered = token.lower()
    return (
        not token
        or token.startswith(TOKEN_PLACEHOLDER_PREFIXES)
        or lowered.startswith(TOKEN_READER_PREFIXES)
        or lowered in TOKEN_PLACEHOLDER_WORDS
        or "replace" in lowered
        or "example" in lowered
    )


def secret_assignment_kind(line: str) -> str | None:
    match = SECRET_ASSIGNMENT_RE.match(line)
    if not match:
        return None
    if is_placeholder_token(match.group(2)):
        return None
    return "secret_assignment"


def is_documentation_or_test(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    return (
        rel == ".env.example"
        or rel.endswith(".example")
        or rel.startswith("docs/")
        or rel.startswith("tests/")
        or "/tests/" in rel
        or "test_" in path.name
        or path.name in {"CODEX_ISSUES.md", "PROJECT_STATUS.md"}
    )


def line_secret_kinds(line: str) -> Iterable[str]:
    for kind, pattern in PATTERNS.items():
        if pattern.search(line):
            yield kind
    token_kind = secret_assignment_kind(line)
    if token_kind:
        yield token_kind


def redact(line: str) -> str:
    line = PATTERNS["secret_key"].sub("[REDACTED_SECRET_KEY]", line)
    line = PATTERNS["default_token"].sub("[REDACTED_DEFAULT_TOKEN]", line)
    line = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED_TOKEN]", line)
    return line.strip()


def allowed(path: Path, line: str, kind: str) -> bool:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    if kind == "default_token" and is_documentation_or_test(path):
        return True
    if kind == "secret_assignment" and is_documentation_or_test(path):
        return is_placeholder_token(SECRET_ASSIGNMENT_RE.match(line).group(2)) if SECRET_ASSIGNMENT_RE.match(line) else False
    return (rel, kind) in ALLOWLIST or any((rel, token) in ALLOWLIST for token in line.split())


def main() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8", errors="ignore")
    required_ignores = [
        "services/central-api/secrets/*.json",
        ".env",
        ".env.*",
        "**/.env.node",
        "**/.env.edge",
        "miniogas-token.txt",
        "**/miniogas-token.txt",
    ]
    missing_ignores = [entry for entry in required_ignores if entry not in gitignore]
    if missing_ignores:
        print(json.dumps({"ok": False, "missing_gitignore": missing_ignores}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    findings = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or is_skipped(path):
            continue
        if path.name in SECRET_FILE_NAMES:
            findings.append(
                {
                    "file": path.relative_to(PROJECT_ROOT).as_posix(),
                    "line": 1,
                    "kind": "runtime_secret_file",
                    "text": "[REDACTED_SECRET_FILE]",
                }
            )
            continue
        try:
            if path.stat().st_size > MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for kind in line_secret_kinds(line):
                if allowed(path, line, kind):
                    continue
                findings.append(
                    {
                        "file": path.relative_to(PROJECT_ROOT).as_posix(),
                        "line": line_number,
                        "kind": kind,
                        "text": redact(line),
                    }
                )

    if findings:
        print(json.dumps({"ok": False, "findings": findings}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print(json.dumps({"ok": True, "message": "secret scan passed"}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"secret scan failed: {exc}", file=sys.stderr)
        raise
