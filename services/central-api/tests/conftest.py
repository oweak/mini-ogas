"""Hermetic test environment.

These variables are set before the FastAPI app (and its ``Settings``) are
imported, so the suite never depends on a developer's local ``.env`` and never
makes real network calls to DeepSeek or the optional microservices.
"""
import os

os.environ["MINI_OGAS_ENV"] = "test"
os.environ["API_ACCESS_TOKEN"] = "mini-ogas-dev-token"
os.environ["NODE_INGEST_TOKEN"] = "mini-ogas-dev-token"
os.environ["AI_ENABLED"] = "false"
os.environ["PERSIST_ENABLED"] = "false"
os.environ["MICROSERVICES_ENABLED"] = "false"
