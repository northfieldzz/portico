"""
MCP Gateway — FastMCP ハブインスタンス管理 (10サービス 50ツール)
"""

from __future__ import annotations

import json
import logging

import mcp.types
from fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx

from portico.schemas.context import RequestContext

logger = logging.getLogger(__name__)

# ── FastMCP Gateway ───────────────────────────────────────────────────
gateway_mcp = FastMCP("IT Context MCP Gateway")


# ── Dynamic Multi-tenant MCP Protocol Handlers (tools/list & tools/call) ────


def get_current_mcp_context() -> tuple[str, list[str] | None, RequestContext]:
    """
    SSE 接続またはリクエストのコンテキストからテナント ID、スコープ、認証コンテキストを解決する。
    HTTP ヘッダー (X-Gateway-Secret / Authorization / X-Tenant-ID / X-Key-ID / X-Scopes 等) に対応。
    """
    from fastapi import HTTPException, status

    from portico.api.deps import verify_gateway_secret
    from portico.core.config import (
        DEFAULT_TENANT_ID,
        GATEWAY_SECRET_HEADER,
        INSECURE_NO_GATEWAY_AUTH,
    )

    tenant_id = DEFAULT_TENANT_ID
    scopes: list[str] | None = None
    key_id: str | None = None
    key_prefix: str | None = None
    service_id: str | None = None

    try:
        ctx = request_ctx.get()
        req = getattr(ctx, "request", None)
        if req is not None:
            # 認証ヘッダーの取得
            gw_secret = req.headers.get("x-gateway-secret") or req.headers.get("authorization")
            h_tenant = req.headers.get("x-tenant-id")
            q_tenant = req.query_params.get("tenant_id")

            # テナントコンフリクトの検証 (Fail-Fast)
            if h_tenant and q_tenant and h_tenant.strip() != q_tenant.strip():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant ID conflict: Header X-Tenant-ID does not match query tenant_id",
                )

            # テナント ID の解決
            if h_tenant:
                tenant_id = h_tenant.strip()
            elif q_tenant:
                tenant_id = q_tenant.strip()

            # Tollgate キー情報
            key_id = req.headers.get("x-key-id")
            key_prefix = req.headers.get("x-key-prefix")
            service_id = req.headers.get("x-service-id")

            # Gateway 共有シークレット検証
            if not INSECURE_NO_GATEWAY_AUTH and not verify_gateway_secret(gw_secret):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Unauthorized: Missing or invalid gateway shared secret ({GATEWAY_SECRET_HEADER})",
                )

            # スコープの解決
            h_scopes = req.headers.get("x-scopes")

            if h_scopes:
                scopes = [s.strip() for s in h_scopes.split(",") if s.strip()]
            else:
                q_scopes = req.query_params.get("scopes")
                if q_scopes:
                    scopes = [s.strip() for s in q_scopes.split(",") if s.strip()]
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("MCP context extraction error: %s", exc)

    context = RequestContext(
        tenant_id=tenant_id,
        key_id=key_id,
        key_prefix=key_prefix,
        service_id=service_id,
        is_proxied=bool(key_id),
    )
    return tenant_id, scopes, context


@gateway_mcp._mcp_server.list_tools()
async def dynamic_list_tools() -> list[mcp.types.Tool]:
    """
    接続中テナントの利用可能な全ツール（ビルトイン + 外部 MCP サーバー）を動的に集約して返却する。
    """
    from portico.services.server_service import (
        check_scope_authorized,
        get_aggregated_tools,
    )

    tenant_id, scopes, _ = get_current_mcp_context()
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

    tenant_id, scopes, req_ctx = get_current_mcp_context()
    try:
        res = await dispatch_tool_call(
            name,
            arguments or {},
            tenant_id=tenant_id,
            scopes=scopes,
            context=req_ctx,
        )
        text = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
        return [mcp.types.TextContent(type="text", text=text)]
    except HTTPException as exc:
        err_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return [mcp.types.TextContent(type="text", text=f"Error: {err_msg}")]
    except Exception as exc:
        logger.exception("dynamic_call_tool error: %s", exc)
        return [mcp.types.TextContent(type="text", text="Internal Server Error")]
