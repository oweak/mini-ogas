"""``mogas setup`` — interactive .env configuration wizard."""

from __future__ import annotations

from ..core.services import PROJ_ROOT


def run() -> None:
    print()
    env_path = PROJ_ROOT / ".env"
    example_path = PROJ_ROOT / ".env.example"

    if env_path.exists():
        ans = input("  .env already exists. Overwrite? [y/N]: ").strip().lower()
        if ans != "y":
            print("  Aborted.")
            print()
            return

    if not example_path.exists():
        print(f"  ERROR: {example_path} not found.")
        print()
        return

    content = example_path.read_text(encoding="utf-8")

    ollama = input("  Enable Ollama local model? [y/N]: ").strip().lower()
    if ollama != "y":
        content = content.replace(
            "AI_PROVIDER_CHAIN=deepseek,ollama,lm_studio,groq",
            "AI_PROVIDER_CHAIN=deepseek,lm_studio,groq",
        )
        print("    -> Ollama removed from chain")

    env_path.write_text(content, encoding="utf-8")
    print(f"\n  .env written to {env_path}")
    print("  Cloud model keys are not written here. Use deploy/reset-ai-vault.ps1.")
    print("  Run 'mogas doctor' to verify your environment.")
    print()
