import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_secrets


REQUIRED_GITIGNORE = "\n".join(
    [
        "services/central-api/secrets/*.json",
        ".env",
        ".env.*",
        "**/.env.node",
        "**/.env.edge",
        "miniogas-token.txt",
        "**/miniogas-token.txt",
    ]
)


class SecretScanTests(unittest.TestCase):
    def run_scan(self, files: dict[str, str]) -> int:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".gitignore").write_text(REQUIRED_GITIGNORE, encoding="utf-8")
            for relative_path, contents in files.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding="utf-8")
            with patch.object(check_secrets, "PROJECT_ROOT", root):
                try:
                    check_secrets.main()
                except SystemExit as exc:
                    return int(exc.code or 0)
                return 0

    def test_allows_runtime_token_placeholders(self) -> None:
        exit_code = self.run_scan(
            {
                "deploy/env.node.example": "OGAS_API_TOKEN=replace_me\n",
                "deploy/env.central.example": "DEEPSEEK_API_KEY=replace_me\n",
                "deploy/template.ps1": "OGAS_API_TOKEN=$OgasApiToken\n",
                "deploy/reset-ai-vault.ps1": "$env:MINIOGAS_AI_API_KEY = $apiKey\n",
                "services/node-agent/simulator.py": 'OGAS_API_TOKEN = env("OGAS_API_TOKEN", "")\n',
            }
        )
        self.assertEqual(exit_code, 0)

    def test_rejects_committed_runtime_token_assignment(self) -> None:
        exit_code = self.run_scan({"deploy/.env.node": "OGAS_API_TOKEN=real-runtime-token-123\n"})
        self.assertEqual(exit_code, 1)

    def test_rejects_committed_ai_api_key_assignments(self) -> None:
        for variable in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "MINIOGAS_AI_API_KEY", "CUSTOM_ACCESS_TOKEN"):
            with self.subTest(variable=variable):
                exit_code = self.run_scan({".env": f"{variable}=real-secret-token-1234567890\n"})
                self.assertEqual(exit_code, 1)

    def test_ignores_python_local_secret_variable_names(self) -> None:
        exit_code = self.run_scan(
            {
                "services/central-api/auth_runtime.py": (
                    'api_key = os.environ["MINIOGAS_AI_API_KEY"]\n'
                    'return {"unlocked_api_key": api_key}\n'
                )
            }
        )
        self.assertEqual(exit_code, 0)

    def test_rejects_generated_token_file(self) -> None:
        exit_code = self.run_scan({"miniogas-token.txt": "real-runtime-token-123\n"})
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
