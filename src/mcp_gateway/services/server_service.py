"""
MCP Gateway — 外部 MCP サーバー管理 & ツール集約サービス
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status as http_status


from mcp_gateway.core.config import MAX_SERVERS_PER_TENANT
from mcp_gateway.db.session import get_db_pool, get_memory_external_servers
from mcp_gateway.schemas.server import ServerCreateRequest
from mcp_gateway.services.crypto import (
    build_auth_headers,
    decrypt_auth_config,
    encrypt_auth_config,
)

logger = logging.getLogger(__name__)


def to_server_slug(name: str) -> str:
    """サーバー名から名前空間用スラッグ (英数字とアンダースコア) を生成する。"""
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()).strip("_")
    return slug or "ext"


def _parse_scopes(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [str(x) for x in parsed] if isinstance(parsed, list) else []
        except Exception:
            return [s.strip() for s in raw.split(",") if s.strip()]
    return []


async def list_servers_for_tenant(tenant_id: str) -> list[dict[str, Any]]:
    """
    テナントの MCP サーバー一覧 (外部登録) を取得する。
    """
    servers = []

    pool = await get_db_pool()
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute("SELECT set_config('app.current_tenant_id', $1, true);", tenant_id)
                rows = await conn.fetch(
                    """
                    SELECT id, tenant_id, name, url, status, auth_type, encrypted_auth_config, scopes, created_at, updated_at
                    FROM mcp.external_servers
                    WHERE tenant_id = $1
                    ORDER BY created_at ASC;
                    """,
                    tenant_id,
                )
                for r in rows:
                    atype = r["auth_type"] if "auth_type" in r else "none"
                    has_a = bool(r.get("encrypted_auth_config")) or atype != "none"
                    servers.append(
                        {
                            "id": r["id"],
                            "tenant_id": r["tenant_id"],
                            "name": r["name"],
                            "url": r["url"],
                            "status": r["status"],
                            "auth_type": atype,
                            "has_auth": has_a,
                            "scopes": _parse_scopes(r.get("scopes")),
                            "is_builtin": False,
                            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                        }
                    )
                return servers
        except Exception as exc:
            logger.warning("DB query failed in list_servers_for_tenant: %s", exc)

    mem = get_memory_external_servers()
    for s in mem.values():
        if s.get("tenant_id") == tenant_id:
            atype = s.get("auth_type", "none")
            has_a = bool(s.get("encrypted_auth_config")) or atype != "none"
            servers.append(
                {
                    **s,
                    "auth_type": atype,
                    "has_auth": has_a,
                    "scopes": s.get("scopes", []),
                    "is_builtin": False,
                }
            )

    return servers


async def delete_all_servers_for_tenant(tenant_id: str) -> int:
    """
    テナント削除時に呼び出され、該当テナントの全外部 MCP サーバーを完全消去する。
    """
    deleted_count = 0
    pool = await get_db_pool()
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute("SELECT set_config('app.current_tenant_id', $1, true);", tenant_id)
                res = await conn.execute(
                    "DELETE FROM mcp.external_servers WHERE tenant_id = $1;",
                    tenant_id,
                )
                if res.startswith("DELETE "):
                    deleted_count = int(res.split(" ")[1])
        except Exception as exc:
            logger.warning("DB delete failed in delete_all_servers_for_tenant: %s", exc)

    mem = get_memory_external_servers()
    to_delete = [sid for sid, s in mem.items() if s.get("tenant_id") == tenant_id]
    for sid in to_delete:
        del mem[sid]
        deleted_count += 1

    return deleted_count


async def add_external_server(data: ServerCreateRequest, tenant_id: str) -> dict[str, Any]:
    """
    外部 MCP サーバーを登録する。
    インフラ保護のため、テナントあたりの最大登録数 (MAX_SERVERS_PER_TENANT) を検証する。
    """
    if MAX_SERVERS_PER_TENANT > 0:
        current_servers = await list_servers_for_tenant(tenant_id)
        ext_count = sum(1 for s in current_servers if not s.get("is_builtin"))
        if ext_count >= MAX_SERVERS_PER_TENANT:
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Tenant infrastructure limit reached ({ext_count}/{MAX_SERVERS_PER_TENANT} servers). Cannot register more MCP servers.",
            )


    server_id = f"ext-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)


    # 認証ヘッダー構築
    auth_headers = build_auth_headers(
        auth_type=data.auth_type,
        auth_token=data.auth_token,
        auth_header_name=data.auth_header_name,
        custom_headers=data.custom_headers,
    )
    has_auth = bool(auth_headers) or data.auth_type != "none"
    encrypted_auth = (
        encrypt_auth_config(
            {
                "auth_type": data.auth_type,
                "headers": auth_headers,
            }
        )
        if has_auth
        else None
    )

    # 接続確認テスト (MCP JSON-RPC 2.0 tools/list によるプローブ)
    normalized_url = data.url.rstrip("/")
    probe_ok = False
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            rpc_req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            resp = await client.post(normalized_url, headers=auth_headers, json=rpc_req)
            if resp.status_code in (200, 401, 403):
                # 200: 疎通＆プロトコル正常
                # 401/403: サーバー存在＆プロトコル受付 (認証情報設定待ち)
                probe_ok = True
        except Exception:
            probe_ok = False

    status = "active" if probe_ok else "connected"

    pool = await get_db_pool()
    saved = None
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute("SELECT set_config('app.current_tenant_id', $1, true);", tenant_id)
                scopes_json = json.dumps(data.scopes)
                row = await conn.fetchrow(
                    """
                    INSERT INTO mcp.external_servers (id, tenant_id, name, url, status, auth_type, encrypted_auth_config, scopes, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $9)
                    ON CONFLICT (tenant_id, url)
                    DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status, auth_type = EXCLUDED.auth_type,
                                  encrypted_auth_config = EXCLUDED.encrypted_auth_config, scopes = EXCLUDED.scopes, updated_at = EXCLUDED.updated_at
                    RETURNING id, tenant_id, name, url, status, auth_type, scopes, created_at, updated_at;
                    """,
                    server_id,
                    tenant_id,
                    data.name,
                    data.url,
                    status,
                    data.auth_type,
                    encrypted_auth,
                    scopes_json,
                    now,
                )
                if row:
                    saved = {
                        "id": row["id"],
                        "tenant_id": row["tenant_id"],
                        "name": row["name"],
                        "url": row["url"],
                        "status": row["status"],
                        "auth_type": row["auth_type"] if "auth_type" in row else data.auth_type,
                        "has_auth": has_auth,
                        "scopes": _parse_scopes(row["scopes"]) if "scopes" in row else data.scopes,
                        "is_builtin": False,
                        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    }
        except Exception as exc:
            logger.warning("DB insert failed in add_external_server: %s", exc)

    if not saved:
        saved = {
            "id": server_id,
            "tenant_id": tenant_id,
            "name": data.name,
            "url": data.url,
            "status": status,
            "auth_type": data.auth_type,
            "has_auth": has_auth,
            "scopes": data.scopes,
            "encrypted_auth_config": encrypted_auth,
            "is_builtin": False,
            "created_at": now.isoformat(),
        }
        get_memory_external_servers()[server_id] = saved

    return saved


async def remove_external_server(server_id: str, tenant_id: str) -> bool:
    """
    外部 MCP サーバーを削除する。
    """
    deleted = False
    pool = await get_db_pool()
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute("SELECT set_config('app.current_tenant_id', $1, true);", tenant_id)
                res = await conn.execute(
                    "DELETE FROM mcp.external_servers WHERE id = $1 AND tenant_id = $2;",
                    server_id,
                    tenant_id,
                )
                deleted = res != "DELETE 0"
        except Exception as exc:
            logger.warning("DB delete failed in remove_external_server: %s", exc)

    mem = get_memory_external_servers()
    if not deleted and server_id in mem:
        if mem[server_id].get("tenant_id") == tenant_id:
            del mem[server_id]
            deleted = True

    return deleted



async def get_external_servers_with_auth(tenant_id: str) -> list[dict[str, Any]]:
    """
    テナントの全外部 MCP サーバーの URL と復号された認証ヘッダー、スコープ、識別情報のリストを取得する。
    """
    results = []
    pool = await get_db_pool()
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute("SELECT set_config('app.current_tenant_id', $1, true);", tenant_id)
                rows = await conn.fetch(
                    "SELECT id, url, encrypted_auth_config, name, scopes FROM mcp.external_servers WHERE tenant_id = $1;",
                    tenant_id,
                )
                for r in rows:
                    auth_cfg = decrypt_auth_config(r.get("encrypted_auth_config"))
                    headers = auth_cfg.get("headers", {})
                    s_name = r.get("name") or "External"
                    results.append(
                        {
                            "id": r["id"],
                            "url": r["url"],
                            "headers": headers,
                            "name": s_name,
                            "slug": to_server_slug(s_name),
                            "scopes": _parse_scopes(r.get("scopes")),
                        }
                    )
                return results
        except Exception as exc:
            logger.warning("DB fetch failed in get_external_servers_with_auth: %s", exc)

    mem = get_memory_external_servers()
    for s in mem.values():
        if s.get("tenant_id") == tenant_id:
            auth_cfg = decrypt_auth_config(s.get("encrypted_auth_config"))
            headers = auth_cfg.get("headers", {})
            s_name = s.get("name") or "External"
            results.append(
                {
                    "id": s.get("id"),
                    "url": s["url"],
                    "headers": headers,
                    "name": s_name,
                    "slug": to_server_slug(s_name),
                    "scopes": s.get("scopes", []),
                }
            )

    return results


async def get_aggregated_tools(tenant_id: str) -> list[dict[str, Any]]:
    """
    外部 MCP サーバーからクロールした全ツールを統合して返却する。
    外部サーバーのツールには名前空間プレフィックス ({server_slug}__{tool_name}) を自動付与し、
    サーバー間の同名ツールの衝突を防止する。
    """
    all_tools: list[dict[str, Any]] = []
    servers = await get_external_servers_with_auth(tenant_id)

    async with httpx.AsyncClient(timeout=3.0) as client:
        for s in servers:
            normalized = s["url"].rstrip("/")
            headers = s["headers"]
            server_scopes = s.get("scopes", [])
            server_id = s.get("id")
            server_name = s.get("name", "External")
            server_slug = s.get("slug") or to_server_slug(server_name)

            # MCP 公式仕様 (JSON-RPC 2.0 / Streamable HTTP POST tools/list) でツール一覧を取得
            try:
                rpc_req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                rpc_resp = await client.post(normalized, headers=headers, json=rpc_req)
                if rpc_resp.status_code == 200:
                    rdata = rpc_resp.json()
                    tools_list = []
                    if isinstance(rdata, dict):
                        if "result" in rdata and isinstance(rdata["result"], dict):
                            tools_list = rdata["result"].get("tools", [])
                        elif "tools" in rdata:
                            tools_list = rdata["tools"]
                    for item in tools_list:
                        if isinstance(item, dict) and "name" in item:
                            orig_name = item["name"]
                            namespaced_name = f"{server_slug}__{orig_name}"
                            item["original_name"] = orig_name
                            item["name"] = namespaced_name
                            item["server_id"] = server_id
                            item["server_name"] = server_name
                            item["is_builtin"] = False
                            item.setdefault("app", server_name)
                            item.setdefault("scopes", server_scopes)
                            all_tools.append(item)
            except Exception as exc:
                logger.warning("Failed to fetch tools via MCP JSON-RPC from %s (%s): %s", server_name, normalized, exc)

    return all_tools


def check_scope_authorized(client_scopes: list[str] | None, required_scopes: list[str]) -> bool:
    """
    クライアントのスコープが必要スコープを満たしているか判定する。
    - クライアントスコープが未指定 (None) の場合は全許可 (未制限アクセス)
    - ツールが必要スコープを持たない (空リスト) 場合は全許可 (パブリックツール)
    - クライアントが '*' または 'admin' を持つ場合は全許可
    - それ以外は、要求スコープのいずれか (またはプレフィックス 'app:*') を持っていること
    """
    if client_scopes is None:
        return True
    if not required_scopes:
        return True
    if "*" in client_scopes or "admin" in client_scopes:
        return True

    for req in required_scopes:
        if req in client_scopes:
            return True
        # プレフィックス一致 (例: 'notion:*' で 'notion:read' を許可)
        prefix = req.split(":")[0] + ":*" if ":" in req else None
        if prefix and prefix in client_scopes:
            return True
    return False


async def dispatch_tool_call(
    tool_name: str,
    params: dict[str, Any],
    tenant_id: str,
    scopes: list[str] | None = None,
) -> Any:
    """
    ツール呼び出しのディスパッチ（ローカル実行または外部 MCP サーバーへのプロキシ）。
    FastMCP SSE ハンドラーおよび REST API の共通実行コア。
    """
    aggregated = await get_aggregated_tools(tenant_id)
    target_tool = next(
        (t for t in aggregated if t.get("name") == tool_name or t.get("original_name") == tool_name),
        None,
    )
    required_scopes = target_tool.get("scopes", []) if target_tool else []

    if not check_scope_authorized(scopes, required_scopes):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Access forbidden: Insufficient scope for tool '{tool_name}'. Required: {required_scopes}, Provided: {scopes or []}",
        )

    # 外部 MCP サーバーへの転送を試行 (認証ヘッダー & スコープ付きプロキシ)
    servers = await get_external_servers_with_auth(tenant_id)

    target_server = None
    exec_tool_name = tool_name
    if "__" in tool_name:
        prefix, _, orig = tool_name.partition("__")
        for s in servers:
            if s.get("slug") == prefix or s.get("id") == prefix or to_server_slug(s.get("name", "")) == prefix:
                target_server = s
                exec_tool_name = orig
                break

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 2-A. 名前空間付きツール名の場合、対象サーバーにピンポイント送信
        if target_server:
            srv_scopes = target_server.get("scopes", [])
            if not check_scope_authorized(scopes, srv_scopes):
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail=f"Access forbidden: Insufficient scope for server '{target_server.get('name')}'. Required: {srv_scopes}",
                )
            headers = target_server.get("headers", {})
            try:
                rpc_body = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": exec_tool_name, "arguments": params},
                }
                resp = await client.post(target_server["url"].rstrip("/"), headers=headers, json=rpc_body)
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        if "error" in payload:
                            raise HTTPException(
                                status_code=http_status.HTTP_502_BAD_GATEWAY,
                                detail=f"External MCP server returned error: {payload['error']}",
                            )
                        if "result" in payload:
                            return payload["result"]
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("Failed MCP JSON-RPC call to %s: %s", target_server.get("name"), exc)
                raise HTTPException(
                    status_code=http_status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to communicate with external MCP server '{target_server.get('name')}': {exc}",
                ) from exc

        # 2-B. 汎用フォールバック
        for s in servers:
            srv_scopes = s.get("scopes", [])
            if not check_scope_authorized(scopes, srv_scopes):
                continue

            headers = s.get("headers", {})
            try:
                rpc_body = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": exec_tool_name, "arguments": params},
                }
                resp = await client.post(s["url"].rstrip("/"), headers=headers, json=rpc_body)
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, dict) and "result" in payload and "error" not in payload:
                        return payload["result"]
            except Exception:
                continue

    raise HTTPException(
        status_code=http_status.HTTP_404_NOT_FOUND,
        detail=f"Unknown tool: '{tool_name}'. No matching registered tool or external MCP server found.",
    )
