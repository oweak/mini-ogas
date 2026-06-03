import os
import sys
from pathlib import Path

from pydantic import BaseModel


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Docker: /app/app/core/config.py → parents[3] = /app
# Local:  .../services/central-api/app/core/config.py → parents[4] = project root
# PyInstaller: sys._MEIPASS is the temp extraction directory
_path = Path(__file__).resolve()

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    try:
        PROJECT_ROOT = _path.parents[4]
    except IndexError:
        PROJECT_ROOT = _path.parents[3]

_load_env_file(PROJECT_ROOT / ".env")
_load_env_file(PROJECT_ROOT / "services" / "central-api" / ".env")

# When frozen, also try loading .env from the executable's directory
if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).parent
    _load_env_file(exe_dir / ".env")


class Settings(BaseModel):
    app_name: str = "Mini-OGAS Central API"
    version: str = "0.3.0"
    simulation_min_interval_seconds: float = 0.8
    simulation_base_interval_seconds: float = 3.0
    heartbeat_timeout_seconds: int = int(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "30"))
    # ---- AI multi-provider settings ----
    ai_enabled: bool = os.getenv("AI_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    ai_timeout_seconds: int = int(os.getenv("AI_TIMEOUT_SECONDS", "25"))
    ai_provider_chain: list[str] = _csv_env(
        "AI_PROVIDER_CHAIN", "deepseek,ollama,lm_studio,groq"
    )
    # DeepSeek
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    # Ollama
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")
    # LM Studio
    lm_studio_base_url: str = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234")
    # Groq
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")
    # WARNING: Default tokens below are for local dev only.
    # Override API_ACCESS_TOKEN and NODE_INGEST_TOKEN in production.
    api_access_token: str = os.getenv("API_ACCESS_TOKEN", "mini-ogas-dev-token")
    node_ingest_token: str = os.getenv("NODE_INGEST_TOKEN", os.getenv("API_ACCESS_TOKEN", "mini-ogas-dev-token"))
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "180"))
    microservices_enabled: bool = os.getenv("MICROSERVICES_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    persist_enabled: bool = os.getenv("PERSIST_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    central_db_path: str = os.getenv("CENTRAL_DB_PATH", str(PROJECT_ROOT / ".runtime" / "central.db"))
    ai_dispatcher_url: str = os.getenv("AI_DISPATCHER_URL", "http://127.0.0.1:8081")
    market_simulator_url: str = os.getenv("MARKET_SIMULATOR_URL", "http://127.0.0.1:8082")
    production_planner_url: str = os.getenv("PRODUCTION_PLANNER_URL", "http://127.0.0.1:8083")
    service_probe_timeout_seconds: float = float(os.getenv("SERVICE_PROBE_TIMEOUT_SECONDS", "5"))
    cors_origins: list[str] = _csv_env(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173",
    )


settings = Settings()
