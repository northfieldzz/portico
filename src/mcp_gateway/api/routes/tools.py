"""
MCP Gateway — ツール統合 & プロキシ実行ルート
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from mcp_gateway.api.deps import get_scopes, get_tenant_id
from mcp_gateway.schemas.tools import ToolDefinition, ToolExecutionResponse
from mcp_gateway.services.server_service import (
    check_scope_authorized,
    dispatch_tool_call,
    get_aggregated_tools,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=list[ToolDefinition])
async def list_tools(
    tenant_id: str = Depends(get_tenant_id),
    scopes: list[str] | None = Depends(get_scopes),
):
    """
    標準ツールおよび外部 MCP サーバーの統合ツールマニフェストを取得する。
    X-Scopes が指定されている場合、実行権限のあるツールのみフィルタリングして返却する。
    """
    tools = await get_aggregated_tools(tenant_id)
    if scopes is not None:
        tools = [t for t in tools if check_scope_authorized(scopes, t.get("scopes", []))]
    return tools


@router.post("/tools/{tool_name}", response_model=ToolExecutionResponse)
async def execute_tool(
    tool_name: str,
    params: dict[str, Any],
    tenant_id: str = Depends(get_tenant_id),
    scopes: list[str] | None = Depends(get_scopes),
):
    """
    ツールの実行（REST API 後方互換性エンドポイント）。
    内部共通ディスパッチャー (dispatch_tool_call) を呼び出す。
    """
    result = await dispatch_tool_call(tool_name, params, tenant_id=tenant_id, scopes=scopes)
    return ToolExecutionResponse(tool=tool_name, result=result)

