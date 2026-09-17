"""
MCP Gateway — FastMCP ハブインスタンス管理 (10サービス 50ツール)
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ── FastMCP Gateway ───────────────────────────────────────────────────
gateway_mcp = FastMCP("IT Context MCP Gateway")


# ── Dynamic Multi-tenant MCP Protocol Handlers (tools/list & tools/call) ────
import json
import mcp.types
from mcp.server.lowlevel.server import request_ctx


def get_current_mcp_context() -> tuple[str, list[str] | None]:
    """
    SSE 接続またはリクエストのコンテキストからテナント ID とスコープを解決する。
    HTTP ヘッダー (X-Tenant-ID / X-Scopes) およびクエリパラメータ (?tenant_id=...&scopes=...) の双方に対応。
    """
    tenant_id = "default"
    scopes: list[str] | None = None
    try:
        ctx = request_ctx.get()
        req = getattr(ctx, "request", None)
        if req is not None:
            # テナント ID の解決
            h_tenant = req.headers.get("x-tenant-id")
            if h_tenant:
                tenant_id = h_tenant
            else:
                q_tenant = req.query_params.get("tenant_id")
                if q_tenant:
                    tenant_id = q_tenant

            # スコープの解決
            h_scopes = req.headers.get("x-scopes")
            if h_scopes:
                scopes = [s.strip() for s in h_scopes.split(",") if s.strip()]
            else:
                q_scopes = req.query_params.get("scopes")
                if q_scopes:
                    scopes = [s.strip() for s in q_scopes.split(",") if s.strip()]
    except Exception:
        pass
    return tenant_id, scopes


@gateway_mcp._mcp_server.list_tools()
async def dynamic_list_tools() -> list[mcp.types.Tool]:
    """
    接続中テナントの利用可能な全ツール（ビルトイン + 外部 MCP サーバー）を動的に集約して返却する。
    """
    from portico.services.server_service import (
        check_scope_authorized,
        get_aggregated_tools,
    )

    tenant_id, scopes = get_current_mcp_context()
    tools_dicts = await get_aggregated_tools(tenant_id)
    if scopes is not None:
        tools_dicts = [t for t in tools_dicts if check_scope_authorized(scopes, t.get("scopes", []))]

    mcp_tools = []
    for t in tools_dicts:
        raw_schema = t.get("params_schema") or t.get("parameters") or {}
        if isinstance(raw_schema, dict) and "type" in raw_schema:
            schema = raw_schema
        elif isinstance(raw_schema, dict):
            # デモツールのショートハンド辞書 {'param': 'type'} を正規の JSON Schema に変換
            properties = {}
            for k, v in raw_schema.items():
                if isinstance(v, dict):
                    properties[k] = v
                else:
                    properties[k] = {"type": str(v)}
            schema = {
                "type": "object",
                "properties": properties,
            }
        else:
            schema = {"type": "object", "properties": {}}

        mcp_tools.append(
            mcp.types.Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=schema,
            )
        )
    return mcp_tools


@gateway_mcp._mcp_server.call_tool()
async def dynamic_call_tool(name: str, arguments: dict) -> list[mcp.types.TextContent]:
    """
    MCP プロトコル (tools/call) に基づくツール実行。
    ローカルディスパッチまたは外部 MCP サーバーへの認証ヘッダー付きプロキシ転送を行う。
    """
    from fastapi import HTTPException
    from portico.services.server_service import dispatch_tool_call

    tenant_id, scopes = get_current_mcp_context()
    try:
        res = await dispatch_tool_call(name, arguments or {}, tenant_id=tenant_id, scopes=scopes)
        text = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
        return [mcp.types.TextContent(type="text", text=text)]
    except HTTPException as exc:
        err_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return [mcp.types.TextContent(type="text", text=f"Error: {err_msg}")]
    except Exception as exc:
        logger.exception("dynamic_call_tool error: %s", exc)
        return [mcp.types.TextContent(type="text", text=f"Internal Server Error: {exc}")]

