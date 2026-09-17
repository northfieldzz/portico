"""
MCP Gateway — 外部 MCP サーバー連携ルート
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from portico.api.deps import get_tenant_id
from portico.schemas.server import ServerCreateRequest, ServerDeleteResponse, ServerResponse
from portico.services.server_service import (
    add_external_server,
    list_servers_for_tenant,
    remove_external_server,
)

router = APIRouter(tags=["servers"])


@router.get("/servers", response_model=list[ServerResponse])
async def list_servers(tenant_id: str = Depends(get_tenant_id)):
    """テナント別の利用可能 MCP サーバー一覧 (ビルトイン + 外部) を取得する。"""
    return await list_servers_for_tenant(tenant_id)


@router.post("/servers", response_model=ServerResponse, status_code=status.HTTP_201_CREATED)
async def register_server(
    data: ServerCreateRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """外部 MCP サーバーを登録する (SSRF 防御バリデーションは Pydantic スキーマで自動実行)。"""
    return await add_external_server(data, tenant_id)


@router.delete("/servers/{server_id}", response_model=ServerDeleteResponse)
async def delete_server(
    server_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """外部 MCP サーバーを削除する。"""
    deleted = await remove_external_server(server_id, tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="指定された外部 MCP サーバーが見つかりません。")

    return ServerDeleteResponse(status="success", message=f"Server {server_id} removed", id=server_id)
