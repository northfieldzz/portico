"""
IT Context Platform — MCP Gateway (Integration Hub)
FastAPI アプリケーション エントリポイント
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from portico.api.router import gateway_router
from portico.core.config import LOG_LEVEL, ROOT_PATH, validate_gateway_auth_config
from portico.core.fastmcp_hub import gateway_mcp
from portico.db.session import close_db_pool, init_mcp_db
from portico.schemas.error import ErrorResponse, HTTPValidationError
from portico.services.crypto import validate_crypto_config

load_dotenv()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """MCP Gateway 起動時のリソース初期化 (mcp スキーマの自己初期化) とクリーンアップ。"""
    logger.info("🚀 Starting IT Context Platform — MCP Gateway")
    validate_crypto_config()
    validate_gateway_auth_config()
    await init_mcp_db()
    yield
    logger.info("🛑 Shutting down MCP Gateway")
    await close_db_pool()



COMMON_RESPONSES = {
    401: {"model": ErrorResponse, "description": "API キーが無効または未指定"},
    403: {"model": ErrorResponse, "description": "アクセス権限不足 (管理者またはテナント権限不足)"},
    404: {
        "model": ErrorResponse,
        "description": "指定されたツールまたはリソースが存在しない、または非公開 API へのアクセス遮断",
    },
    422: {"model": HTTPValidationError, "description": "リクエストパラメータまたはボディのバリデーションエラー"},
    429: {"model": ErrorResponse, "description": "レートリミットまたは実行回数上限到達"},
    500: {"model": ErrorResponse, "description": "サーバー内部エラー"},
    502: {"model": ErrorResponse, "description": "外部 MCP サーバーまたは SaaS への接続エラー"},
    504: {"model": ErrorResponse, "description": "外部 MCP サーバーからの応答タイムアウト"},
}


app = FastAPI(
    title="IT Context Platform — MCP Gateway",
    description="SaaS ツール連携および外部 MCP サーバーの統合ハブ・実行ゲートウェイ。",
    version="0.2.0",
    root_path=ROOT_PATH,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/v1/openapi.json",
    responses=COMMON_RESPONSES,
)


# ── Include REST APIs & Internal Routes ──────────────────────────────
app.include_router(gateway_router)


# ── Mount FastMCP SSE handler under /v1 (SSE at /v1/sse) ──
mcp_asgi = gateway_mcp.http_app(transport="sse")
app.mount("/v1", mcp_asgi)
