"""
MCP Gateway — 運用 & ヘルスチェックルート
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from portico.core.config import MOCK_EXTERNAL_APIS

router = APIRouter(tags=["ops"])


class GatewayHealthResponse(BaseModel):
    status: str = Field("ok", description="サービス稼働ステータス")
    service: str = Field("portico", description="サービス識別子")
    mock: bool = Field(..., description="モック外部 API 有効フラグ")


@router.get("/health", response_model=GatewayHealthResponse)
async def health():
    return GatewayHealthResponse(status="ok", service="portico", mock=MOCK_EXTERNAL_APIS)
