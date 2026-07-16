import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

LOCAL_DEVELOPMENT_JWT_SECRET = "mini-ogas-local-development-jwt-secret"


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
    app_env: Literal["development", "test", "digital_twin", "staging", "pilot", "production"] = (
        os.getenv("APP_ENV", os.getenv("MINI_OGAS_ENV", "development")).strip().lower()
    )
    data_source: Literal["simulated", "replay", "shadow", "live"] = os.getenv(
        "DATA_SOURCE", "simulated"
    ).strip().lower()
    control_mode: Literal["read_only", "operator_assisted", "controlled_write"] = os.getenv(
        "CONTROL_MODE", "operator_assisted"
    ).strip().lower()
    demo_seed_enabled: bool = os.getenv("DEMO_SEED_ENABLED", "true").lower() in {
        "1", "true", "yes", "on",
    }
    physical_write_enabled: bool = os.getenv("PHYSICAL_WRITE_ENABLED", "false").lower() in {
        "1", "true", "yes", "on",
    }
    industrial_connector_enabled: bool = os.getenv("INDUSTRIAL_CONNECTOR_ENABLED", "false").lower() in {
        "1", "true", "yes", "on",
    }
    tenant_id: str = os.getenv("TENANT_ID", "tenant-local").strip()
    site_id: str = os.getenv("SITE_ID", "site-digital-twin").strip()
    simulation_min_interval_seconds: float = 0.8
    simulation_base_interval_seconds: float = 3.0
    heartbeat_timeout_seconds: int = int(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "30"))
    command_claim_timeout_seconds: int = int(os.getenv("COMMAND_CLAIM_TIMEOUT_SECONDS", "120"))
    # ---- AI multi-provider settings ----
    ai_enabled: bool = os.getenv("AI_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    ai_timeout_seconds: int = int(os.getenv("AI_TIMEOUT_SECONDS", "25"))
    ai_chat_max_tokens: int = int(os.getenv("AI_CHAT_MAX_TOKENS", "4096"))
    ai_rule_explanation_cache_seconds: int = int(os.getenv("AI_RULE_EXPLANATION_CACHE_SECONDS", "60"))
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
    node_credentials_json: str = os.getenv("NODE_CREDENTIALS_JSON", "").strip()
    auth_jwt_secret: str = os.getenv("JWT_SECRET", LOCAL_DEVELOPMENT_JWT_SECRET)
    auth_jwt_ttl_seconds: int = int(os.getenv("JWT_TTL_SECONDS", "28800"))
    auth_bootstrap_username: str = os.getenv("AUTH_BOOTSTRAP_USERNAME", "admin")
    auth_bootstrap_display_name: str = os.getenv("AUTH_BOOTSTRAP_DISPLAY_NAME", "车间主管")
    # Used only to create the first local administrator. Subsequent logins are
    # verified against the salted password hash stored in PostgreSQL/SQLite.
    auth_bootstrap_password: str = os.getenv("AUTH_BOOTSTRAP_PASSWORD", os.getenv("MINIOGAS_ADMIN_PASSWORD", ""))
    allow_legacy_api_token_auth: bool = os.getenv("ALLOW_LEGACY_API_TOKEN_AUTH", "false").lower() in {"1", "true", "yes", "on"}
    allow_legacy_node_token_auth: bool = os.getenv(
        "ALLOW_LEGACY_NODE_TOKEN_AUTH", "false"
    ).lower() in {"1", "true", "yes", "on"}
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "1200"))
    microservices_enabled: bool = os.getenv("MICROSERVICES_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
    persist_enabled: bool = os.getenv("PERSIST_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    database_auto_migrate: bool = os.getenv("DATABASE_AUTO_MIGRATE", "false").lower() in {
        "1", "true", "yes", "on",
    }
    persist_backend: str = os.getenv("PERSIST_BACKEND", "auto").strip().lower()
    central_fact_source: str = os.getenv("CENTRAL_FACT_SOURCE", "postgresql").strip().lower()
    postgres_dsn: str = os.getenv("POSTGRES_DSN", os.getenv("DATABASE_URL", "")).strip()
    central_db_path: str = os.getenv("CENTRAL_DB_PATH", str(PROJECT_ROOT / ".runtime" / "central.db"))
    heartbeat_shadow_retention_per_node: int = int(os.getenv("HEARTBEAT_SHADOW_RETENTION_PER_NODE", "2000"))
    telemetry_raw_retention_days: int = int(os.getenv("TELEMETRY_RAW_RETENTION_DAYS", "7"))
    telemetry_aggregate_retention_days: int = int(
        os.getenv("TELEMETRY_AGGREGATE_RETENTION_DAYS", "90")
    )
    telemetry_bootstrap_catalog_enabled: bool = os.getenv(
        "TELEMETRY_BOOTSTRAP_CATALOG_ENABLED",
        "false",
    ).lower() in {"1", "true", "yes", "on"}
    redis_enabled: bool = os.getenv("REDIS_ENABLED", "false").lower() in {
        "1", "true", "yes", "on",
    }
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    redis_socket_timeout_seconds: float = float(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "2"))
    object_storage_enabled: bool = os.getenv("OBJECT_STORAGE_ENABLED", "false").lower() in {
        "1", "true", "yes", "on",
    }
    object_storage_endpoint: str = os.getenv("OBJECT_STORAGE_ENDPOINT", "127.0.0.1:9000")
    object_storage_access_key: str = os.getenv("OBJECT_STORAGE_ACCESS_KEY", "")
    object_storage_secret_key: str = os.getenv("OBJECT_STORAGE_SECRET_KEY", "")
    object_storage_bucket: str = os.getenv("OBJECT_STORAGE_BUCKET", "miniogas-documents")
    object_storage_secure: bool = os.getenv("OBJECT_STORAGE_SECURE", "false").lower() in {
        "1", "true", "yes", "on",
    }
    object_storage_max_bytes: int = int(os.getenv("OBJECT_STORAGE_MAX_BYTES", str(25 * 1024 * 1024)))
    nats_enabled: bool = os.getenv("NATS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    nats_url: str = os.getenv("NATS_URL", "nats://127.0.0.1:4222")
    nats_auth_token: str = os.getenv("NATS_AUTH_TOKEN", "")
    nats_stream: str = os.getenv("NATS_STREAM", "OGAS_V3_SHADOW")
    nats_consumer: str = os.getenv("NATS_CONSUMER", "ogas-v3-postgres-worker")
    nats_connect_timeout_seconds: float = float(os.getenv("NATS_CONNECT_TIMEOUT_SECONDS", "2"))
    nats_publish_timeout_seconds: float = float(os.getenv("NATS_PUBLISH_TIMEOUT_SECONDS", "2"))
    nats_retry_seconds: float = float(os.getenv("NATS_RETRY_SECONDS", "5"))
    nats_stream_max_bytes: int = int(os.getenv("NATS_STREAM_MAX_BYTES", str(4 * 1024 * 1024 * 1024)))
    nats_reconciliation_grace_seconds: int = int(
        os.getenv("NATS_RECONCILIATION_GRACE_SECONDS", "15")
    )
    nats_reconciliation_window_messages: int = int(
        os.getenv("NATS_RECONCILIATION_WINDOW_MESSAGES", "100")
    )
    nats_reconciliation_min_samples: int = int(
        os.getenv("NATS_RECONCILIATION_MIN_SAMPLES", "100")
    )
    nats_min_receive_rate: float = float(os.getenv("NATS_MIN_RECEIVE_RATE", "0.999"))
    nats_max_duplicate_rate: float = float(os.getenv("NATS_MAX_DUPLICATE_RATE", "0.01"))
    nats_max_p95_latency_ms: float = float(os.getenv("NATS_MAX_P95_LATENCY_MS", "5000"))
    ai_dispatcher_url: str = os.getenv("AI_DISPATCHER_URL", "http://127.0.0.1:8081")
    market_simulator_url: str = os.getenv("MARKET_SIMULATOR_URL", "http://127.0.0.1:8082")
    production_planner_url: str = os.getenv("PRODUCTION_PLANNER_URL", "http://127.0.0.1:8083")
    background_worker_url: str = os.getenv(
        "BACKGROUND_WORKER_URL", "http://127.0.0.1:8084"
    )
    supervisor_url: str = os.getenv("SUPERVISOR_URL", "http://127.0.0.1:9099")
    service_probe_timeout_seconds: float = float(os.getenv("SERVICE_PROBE_TIMEOUT_SECONDS", "5"))
    expected_supervisor_processes: list[str] = _csv_env(
        "EXPECTED_SUPERVISOR_PROCESSES",
        "central-api,background-worker,ai-dispatcher,market-simulator,production-planner,dashboard,"
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

    @field_validator("tenant_id", "site_id")
    @classmethod
    def validate_scope_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", value):
            raise ValueError("scope IDs must use 2-64 lowercase letters, digits, '_' or '-'")
        return value

    @model_validator(mode="after")
    def validate_environment_boundary(self) -> "Settings":
        if self.database_auto_migrate:
            raise ValueError(
                "DATABASE_AUTO_MIGRATE is no longer supported; run python -m app.migrate before startup"
            )
        if self.telemetry_raw_retention_days < 1:
            raise ValueError("TELEMETRY_RAW_RETENTION_DAYS must be at least 1")
        if self.telemetry_aggregate_retention_days <= self.telemetry_raw_retention_days:
            raise ValueError(
                "TELEMETRY_AGGREGATE_RETENTION_DAYS must exceed raw retention"
            )
        if self.object_storage_max_bytes < 1:
            raise ValueError("OBJECT_STORAGE_MAX_BYTES must be positive")
        if self.nats_reconciliation_grace_seconds < 1:
            raise ValueError("NATS_RECONCILIATION_GRACE_SECONDS must be positive")
        if self.nats_reconciliation_window_messages < 1:
            raise ValueError("NATS_RECONCILIATION_WINDOW_MESSAGES must be positive")
        if self.nats_reconciliation_min_samples < 1:
            raise ValueError("NATS_RECONCILIATION_MIN_SAMPLES must be positive")
        if not 0 <= self.nats_min_receive_rate <= 1:
            raise ValueError("NATS_MIN_RECEIVE_RATE must be between 0 and 1")
        if not 0 <= self.nats_max_duplicate_rate <= 1:
            raise ValueError("NATS_MAX_DUPLICATE_RATE must be between 0 and 1")
        if self.nats_max_p95_latency_ms <= 0:
            raise ValueError("NATS_MAX_P95_LATENCY_MS must be positive")
        if self.demo_seed_enabled and self.data_source != "simulated":
            raise ValueError("DEMO_SEED_ENABLED=true requires DATA_SOURCE=simulated")

        if self.control_mode == "controlled_write":
            if self.app_env not in {"pilot", "production"}:
                raise ValueError("CONTROL_MODE=controlled_write is limited to pilot or production")
            if not self.industrial_connector_enabled or not self.physical_write_enabled:
                raise ValueError(
                    "CONTROL_MODE=controlled_write requires an enabled industrial connector "
                    "and PHYSICAL_WRITE_ENABLED=true"
                )

        if self.physical_write_enabled and self.control_mode != "controlled_write":
            raise ValueError("PHYSICAL_WRITE_ENABLED=true requires CONTROL_MODE=controlled_write")

        if self.app_env == "production":
            problems: list[str] = []
            if self.data_source not in {"shadow", "live"}:
                problems.append("DATA_SOURCE must be shadow or live")
            if self.demo_seed_enabled:
                problems.append("Demo Seed must be disabled")
            if not self.persist_enabled or self.persist_backend not in {"postgres", "postgresql"}:
                problems.append("PostgreSQL persistence must be enabled")
            if not self.postgres_dsn.startswith("postgresql://"):
                problems.append("POSTGRES_DSN must be configured")
            if self.auth_jwt_secret == LOCAL_DEVELOPMENT_JWT_SECRET or len(self.auth_jwt_secret) < 32:
                problems.append("JWT_SECRET must be a non-default secret of at least 32 characters")
            try:
                node_credentials = json.loads(self.node_credentials_json)
            except json.JSONDecodeError:
                node_credentials = None
            if not isinstance(node_credentials, dict):
                problems.append("NODE_CREDENTIALS_JSON must be a JSON object")
            else:
                missing_nodes = sorted(set(self.expected_production_nodes) - set(node_credentials))
                tokens = [str(node_credentials.get(node, "")) for node in self.expected_production_nodes]
                if missing_nodes:
                    problems.append(
                        "NODE_CREDENTIALS_JSON is missing nodes: " + ", ".join(missing_nodes)
                    )
                if any(len(token) < 32 for token in tokens):
                    problems.append("every production node credential must be at least 32 characters")
                if len(set(tokens)) != len(tokens):
                    problems.append("production node credentials must be unique per node")
                placeholder_markers = ("replace", "changeme", "example", "your-token")
                if any(
                    marker in token.lower()
                    for token in tokens
                    for marker in placeholder_markers
                ):
                    problems.append(
                        "production node credentials must not use placeholder values"
                    )
            if self.allow_legacy_api_token_auth:
                problems.append("legacy API token authentication must be disabled")
            if self.allow_legacy_node_token_auth:
                problems.append("legacy shared node token authentication must be disabled")
            if self.telemetry_bootstrap_catalog_enabled:
                problems.append("digital-twin telemetry catalog bootstrap must be disabled")
            if self.tenant_id == "tenant-local" or self.site_id == "site-digital-twin":
                problems.append("TENANT_ID and SITE_ID must be explicitly configured")
            if problems:
                raise ValueError("invalid production configuration: " + "; ".join(problems))
        return self

    def runtime_source_class(self, runtime: dict[str, Any] | None) -> str:
        payload = runtime or {}
        source = str(payload.get("runtime_source") or "").strip().lower()
        engine = str(payload.get("simulation_engine") or "").strip().lower()
        deployment = str(payload.get("deployment_mode") or "").strip().lower()
        if source == "replay":
            return "replay"
        if source in {"simulated", "fixture", "node-agent"} or engine in {"simple", "simpy"}:
            return "simulated"
        if source == "live" or engine == "physical" or deployment == "physical":
            return "live"
        if self.data_source == "simulated" and self.app_env in {"development", "test", "digital_twin"}:
            return "simulated"
        return "unknown"

    def validate_runtime_source(self, runtime: dict[str, Any] | None) -> str:
        actual = self.runtime_source_class(runtime)
        allowed = {
            "simulated": {"simulated"},
            "replay": {"replay"},
            "shadow": {"live"},
            "live": {"live"},
        }[self.data_source]
        if actual not in allowed:
            raise ValueError(
                f"runtime data source {actual!r} is incompatible with configured "
                f"DATA_SOURCE={self.data_source}"
            )
        return actual

    def environment_status(self) -> dict[str, object]:
        return {
            "app_env": self.app_env,
            "data_source": self.data_source,
            "control_mode": self.control_mode,
            "demo_seed_enabled": self.demo_seed_enabled,
            "industrial_connector_enabled": self.industrial_connector_enabled,
            "physical_write_enabled": self.physical_write_enabled,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
        }


settings = Settings()
