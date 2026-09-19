"""
MCP Gateway — 設定管理モジュール
"""

from __future__ import annotations

import os

ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()
ALLOW_LOCAL_MCP_SERVERS = os.getenv(
    "ALLOW_LOCAL_MCP_SERVERS",
    "true" if ENVIRONMENT != "production" else "false",
).lower() in ("true", "1", "yes")
MOCK_EXTERNAL_APIS = os.getenv(
    "MOCK_EXTERNAL_APIS",
    "true" if ENVIRONMENT != "production" else "false",
).lower() in ("true", "1", "yes")
POSTGRES_URL = os.getenv(
    "POSTGRES_URL",
    "postgresql://postgres:password@postgres:5432/itcp_db",
).replace("postgresql+asyncpg://", "postgresql://")
ROOT_PATH = os.getenv("ROOT_PATH", "/gateway")
MAX_SERVERS_PER_TENANT = int(os.getenv("MAX_SERVERS_PER_TENANT", "50"))


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
INTERNAL_SERVICE_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", "itcp_internal_service_secret_key_888")

# Tollgate リバースプロキシ連携設定
ENFORCE_TOLLGATE_AUTH = os.getenv("ENFORCE_TOLLGATE_AUTH", "false").lower() in ("true", "1", "yes")
DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "tenant_default")

