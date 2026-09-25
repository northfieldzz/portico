"""
MCP Gateway — 設定管理モジュール
"""

from __future__ import annotations

import os
import secrets

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
INTERNAL_SERVICE_SECRET = os.getenv("INTERNAL_SERVICE_SECRET", secrets.token_hex(32))

# ── Gateway 共有シークレット認証設定 (Kura 準拠) ─────────────────────────
# 認証ゲートウェイ (Tollgate / Proxy 等) からのアクセスを相互信頼確認する共有シークレット
GATEWAY_SHARED_SECRET = os.getenv("GATEWAY_SHARED_SECRET")
GATEWAY_SHARED_SECRET_PREVIOUS = os.getenv("GATEWAY_SHARED_SECRET_PREVIOUS")
GATEWAY_SECRET_HEADER = os.getenv("GATEWAY_SECRET_HEADER", "X-Gateway-Secret")
INSECURE_NO_GATEWAY_AUTH = os.getenv("INSECURE_NO_GATEWAY_AUTH", "false").lower() in ("true", "1", "yes")
DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "tenant_default")


def get_valid_gateway_secrets() -> list[str]:
    """現在有効な Gateway 共有シークレット一覧（新旧ローテーション対応）を返す。"""
    secrets_list: list[str] = []
    if GATEWAY_SHARED_SECRET and GATEWAY_SHARED_SECRET.strip():
        secrets_list.append(GATEWAY_SHARED_SECRET.strip())
    if GATEWAY_SHARED_SECRET_PREVIOUS and GATEWAY_SHARED_SECRET_PREVIOUS.strip():
        secrets_list.append(GATEWAY_SHARED_SECRET_PREVIOUS.strip())
    return secrets_list


def validate_gateway_auth_config() -> None:
    """
    起動時に Gateway 共有シークレット設定を検証する (Fail-Fast)。
    INSECURE_NO_GATEWAY_AUTH=false かつシークレット未設定の場合は起動を拒否する。
    """
    if INSECURE_NO_GATEWAY_AUTH:
        return

    valid_secrets = get_valid_gateway_secrets()
    if not valid_secrets:
        if ENVIRONMENT == "production":
            raise RuntimeError("GATEWAY_SHARED_SECRET must be set in production (or enable INSECURE_NO_GATEWAY_AUTH=true for local dev)")
    else:
        for s in valid_secrets:
            if len(s) < 32 and ENVIRONMENT == "production":
                raise RuntimeError("GATEWAY_SHARED_SECRET must be at least 32 characters long in production")


# 外部 MCP サーバー連携・キャッシュ設定
TOOL_CACHE_TTL_SECONDS = int(os.getenv("TOOL_CACHE_TTL_SECONDS", "60"))
EXTERNAL_MCP_TIMEOUT_SECONDS = float(os.getenv("EXTERNAL_MCP_TIMEOUT_SECONDS", "5.0"))
