"""
MCP Gateway — API ルーター統合モジュール
新統一パス体系:
- サービス提供用: /api/v1/mcp/...
- 内部サービス専用: /api/v1/mcp/internal/...
- ヘルスチェック: /api/mcp/health, /api/health
"""

from __future__ import annotations

from fastapi import APIRouter

from mcp_gateway.api.routes import internal, ops, servers, tools

gateway_router = APIRouter()

# ヘルスチェック (/api/mcp/health)
health_router = APIRouter(prefix="/api/mcp")
health_router.include_router(ops.router)
gateway_router.include_router(health_router)


# 内部専用非公開ルート (/api/v1/mcp/internal/*)
internal_router = APIRouter(prefix="/api/v1/mcp/internal")
internal_router.include_router(internal.router)
gateway_router.include_router(internal_router)

# 外部サービス提供用 v1 API ルート (/api/v1/mcp/*)
v1_router = APIRouter(prefix="/api/v1/mcp")
v1_router.include_router(servers.router)
v1_router.include_router(tools.router)
gateway_router.include_router(v1_router)
