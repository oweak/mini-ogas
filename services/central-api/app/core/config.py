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
    command_claim_timeout_seconds: int = int(os.getenv("COMMAND_CLAIM_TIMEOUT_SECONDS", "120"))
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
    api_access_token: str = os.getenv("API_ACCESS_TOKEN", "")
    node_ingest_token: str = os.getenv("NODE_INGEST_TOKEN", os.getenv("API_ACCESS_TOKEN", ""))
    auth_jwt_secret: str = os.getenv("JWT_SECRET", "mini-ogas-local-development-jwt-secret")
    auth_jwt_ttl_seconds: int = int(os.getenv("JWT_TTL_SECONDS", "28800"))
    auth_bootstrap_username: str = os.getenv("AUTH_BOOTSTRAP_USERNAME", "admin")
    auth_bootstrap_display_name: str = os.getenv("AUTH_BOOTSTRAP_DISPLAY_NAME", "车间主管")
    # Used only to create the first local administrator. Subsequent logins are
    # verified against the salted password hash stored in PostgreSQL/SQLite.
    auth_bootstrap_password: str = os.getenv("AUTH_BOOTSTRAP_PASSWORD", os.getenv("MINIOGAS_ADMIN_PASSWORD", ""))
    allow_legacy_api_token_auth: bool = os.getenv("ALLOW_LEGACY_API_TOKEN_AUTH", "false").lower() in {"1", "true", "yes", "on"}
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "1200"))
    microservices_enabled: bool = os.getenv("MICROSERVICES_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    persist_enabled: bool = os.getenv("PERSIST_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    persist_backend: str = os.getenv("PERSIST_BACKEND", "auto").strip().lower()
    central_fact_source: str = os.getenv("CENTRAL_FACT_SOURCE", "postgresql").strip().lower()
    postgres_dsn: str = os.getenv("POSTGRES_DSN", os.getenv("DATABASE_URL", "")).strip()
    central_db_path: str = os.getenv("CENTRAL_DB_PATH", str(PROJECT_ROOT / ".runtime" / "central.db"))
    heartbeat_shadow_retention_per_node: int = int(os.getenv("HEARTBEAT_SHADOW_RETENTION_PER_NODE", "2000"))
    ai_dispatcher_url: str = os.getenv("AI_DISPATCHER_URL", "http://127.0.0.1:8081")
    market_simulator_url: str = os.getenv("MARKET_SIMULATOR_URL", "http://127.0.0.1:8082")
    production_planner_url: str = os.getenv("PRODUCTION_PLANNER_URL", "http://127.0.0.1:8083")
    supervisor_url: str = os.getenv("SUPERVISOR_URL", "http://127.0.0.1:9099")
    service_probe_timeout_seconds: float = float(os.getenv("SERVICE_PROBE_TIMEOUT_SECONDS", "5"))
    expected_supervisor_processes: list[str] = _csv_env(
        "EXPECTED_SUPERVISOR_PROCESSES",
        "central-api,ai-dispatcher,market-simulator,production-planner,dashboard,"
        "turning-simpy-node,milling-simpy-node,grinding-simpy-node",
    )
    expected_production_nodes: list[str] = _csv_env(
        "EXPECTED_PRODUCTION_NODES",
        "turning-workshop-01,milling-workshop-01,grinding-workshop-01",
    )
    cors_origins: list[str] = _csv_env(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:5174,http://localhost:5174,"
        "http://127.0.0.1:5175,http://localhost:5175,"
        "http://127.0.0.1:5176,http://localhost:5176,"
        "http://127.0.0.1:5177,http://localhost:5177,"
        "http://127.0.0.1:4173,http://localhost:4173,"
        "http://127.0.0.1:3000,http://localhost:3000",
    )


settings = Settings()
