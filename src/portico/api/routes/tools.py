"""
MCP Gateway — ツール統合 & プロキシ実行ルート
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from portico.api.deps import get_request_context, get_scopes
from portico.schemas.context import RequestContext
from portico.schemas.tools import ToolDefinition, ToolExecutionResponse
from portico.services.server_service import (
    check_scope_authorized,
    dispatch_tool_call,
    get_aggregated_tools,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=list[ToolDefinition])
async def list_tools(
    ctx: RequestContext = Depends(get_request_context),
    scopes: list[str] | None = Depends(get_scopes),
):
    """
    標準ツールおよび外部 MCP サーバーの統合ツールマニフェストを取得する。
    X-Scopes が指定されている場合、実行権限のあるツールのみフィルタリングして返却する。
    """
    tools = await get_aggregated_tools(ctx.tenant_id)
    if scopes is not None:
        tools = [t for t in tools if check_scope_authorized(scopes, t.get("scopes", []))]
    return tools


@router.post("/tools/{tool_name}", response_model=ToolExecutionResponse)
async def execute_tool(
    tool_name: str,
    params: dict[str, Any],
    ctx: RequestContext = Depends(get_request_context),
    scopes: list[str] | None = Depends(get_scopes),
):
    """
    ツールの実行（REST API エンドポイント）。
    内部共通ディスパッチャー (dispatch_tool_call) を呼び出し、監査ログを記録する。
    """
    result = await dispatch_tool_call(
        tool_name,
        params,
        tenant_id=ctx.tenant_id,
        scopes=scopes,
        context=ctx,
    )
    return ToolExecutionResponse(tool=tool_name, result=result)

