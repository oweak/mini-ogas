"""Hermetic test environment.

These variables are set before the FastAPI app (and its ``Settings``) are
imported, so the suite never depends on a developer's local ``.env`` and never
makes real network calls to DeepSeek or the optional microservices.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_DB_PATH = PROJECT_ROOT / ".runtime" / "test-central.db"
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
TEST_DB_PATH.unlink(missing_ok=True)

os.environ["MINI_OGAS_ENV"] = "test"
os.environ["APP_ENV"] = "test"
os.environ["DATA_SOURCE"] = "simulated"
os.environ["CONTROL_MODE"] = "operator_assisted"
os.environ["DEMO_SEED_ENABLED"] = "true"
os.environ["TENANT_ID"] = "tenant-test"
os.environ["SITE_ID"] = "site-test"
os.environ["API_ACCESS_TOKEN"] = "mini-ogas-dev-token"
os.environ["NODE_INGEST_TOKEN"] = "mini-ogas-dev-token"
os.environ["AUTH_BOOTSTRAP_PASSWORD"] = "mini-ogas-dev-token"
os.environ["CENTRAL_DB_PATH"] = str(TEST_DB_PATH)
os.environ["AI_ENABLED"] = "false"
os.environ["PERSIST_ENABLED"] = "false"
os.environ["PERSIST_BACKEND"] = "sqlite"
os.environ["MICROSERVICES_ENABLED"] = "false"
os.environ["NATS_ENABLED"] = "false"
# Existing endpoint tests use the legacy machine header. Production defaults to
# bearer JWT only; focused migration tests exercise that path directly.
os.environ["ALLOW_LEGACY_API_TOKEN_AUTH"] = "true"
os.environ["ALLOW_LEGACY_NODE_TOKEN_AUTH"] = "true"
os.environ["JWT_SECRET"] = "mini-ogas-test-jwt-secret"
